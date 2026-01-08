import py_trees
from typing import Dict, Any, Type, List
from pydantic import create_model
from btflow.state import StateManager
from btflow.state import StateManager
from .workflow_schema import WorkflowDefinition, NodeDefinition
from .node_registry import node_registry
from py_trees.composites import Sequence, Selector, Parallel
from py_trees.composites import Sequence, Selector, Parallel
from py_trees.common import ParallelPolicy
import inspect

class WorkflowConverter:
    """
    Compiles a WorkflowDefinition JSON into a runnable py_trees instance.
    """
    
    def __init__(self, workflow: WorkflowDefinition):
        self.workflow = workflow
        self.node_map: Dict[str, py_trees.behaviour.Behaviour] = {}
        self.state_manager = self._create_state_manager()
    
    def compile(self) -> py_trees.behaviour.Behaviour:
        """Builds the behavior tree from the workflow definition."""
        
        # 1. Instantiate all nodes
        for node_def in self.workflow.nodes:
            self.node_map[node_def.id] = self._create_node(node_def)
            
        # 2. Build Hierarchy (Connect Edges)
        # We need to find the root. In a tree, the root is the node with no incoming edges.
        # But wait, edges might define parent-child relationships for Composites.
        
        children_map: Dict[str, List[str]] = {} # parent_id -> [child_id, ...]
        has_parent: set = set()
        
        for edge in self.workflow.edges:
            parent_id = edge.source
            child_id = edge.target
            
            if parent_id not in children_map:
                children_map[parent_id] = []
            children_map[parent_id].append(child_id)
            has_parent.add(child_id)
            
        # 3. Assemble Tree
        root_candidates = [n.id for n in self.workflow.nodes if n.id not in has_parent]
        
        if not root_candidates:
            # Fallback: if single node loop or empty, handle gracefully
            if not self.workflow.nodes:
                 return py_trees.behaviours.Dummy(name="Empty Workflow")
            # If ring, pick first? No, error.
            raise ValueError("Cyclic dependency or empty workflow: No root node found.")
            
        if len(root_candidates) > 1:
            # If multiple roots, implicit parallel or sequence? 
            # For now, strictly require single root or wrap in a Sequence
            raise ValueError(f"Multiple root nodes found: {root_candidates}. Please connect them to a single root.")
            
        root_id = root_candidates[0]
        self._assemble_children(root_id, children_map)
        
        return self.node_map[root_id]

    def _assemble_children(self, parent_id: str, children_map: Dict[str, List[str]]):
        parent_node = self.node_map[parent_id]
        
        if parent_id in children_map:
            # Sort children by X position (left to right)
            child_ids = children_map[parent_id]
            
            # Get position info from workflow nodes
            def get_x_position(node_id: str) -> float:
                for node_def in self.workflow.nodes:
                    if node_def.id == node_id:
                        return node_def.position.x if node_def.position else 0
                return 0
            
            # Sort by X coordinate
            child_ids_sorted = sorted(child_ids, key=get_x_position)
            
            children_nodes = []
            for child_id in child_ids_sorted:
                if child_id not in self.node_map:
                    continue # Edge points to non-existent node
                    
                # Recursively assemble children's children
                self._assemble_children(child_id, children_map)
                children_nodes.append(self.node_map[child_id])
                
            if isinstance(parent_node, py_trees.composites.Composite):
                parent_node.add_children(children_nodes)
            elif isinstance(parent_node, py_trees.decorators.Decorator):
                if len(children_nodes) == 1:
                    parent_node.decorate(children_nodes[0])
                else:
                    print(f"Warning: Decorator {parent_id} has {len(children_nodes)} children. Expected 1.")
            else:
                 # Warning: Leaf node has children?
                 pass

    def _create_state_manager(self) -> StateManager:
        """Dynamically creates the Pydantic State Schema from definition."""
        fields = {}
        
        type_map = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
            "tuple": tuple
        }
        
        for field in self.workflow.state.fields:
            py_type = type_map.get(field.type, str)
            # TODO: Handle ActionField annotation if field.is_action is True
            fields[field.name] = (py_type, field.default)
        
        # Create Dynamic Model
        try:
            DynamicState = create_model(self.workflow.state.schema_name or "DynamicState", **fields)
        except Exception:
            DynamicState = create_model("DynamicState", **fields)
            
        return StateManager(schema=DynamicState)
        
    def _create_node(self, node_def: NodeDefinition) -> py_trees.behaviour.Behaviour:
        meta = node_registry.get(node_def.type)
        if not meta:
            # Check built-in fallbacks if generic
             return py_trees.behaviours.Dummy(name=node_def.id)
            
        # 1. Handle Built-in Composites
        if node_def.type == "Sequence":
            return Sequence(name=node_def.id, memory=node_def.config.get("memory", True))
        elif node_def.type == "Selector":
            return Selector(name=node_def.id, memory=node_def.config.get("memory", True))
        elif node_def.type == "Parallel":
            policy_str = node_def.config.get("policy", "SuccessOnAll")
            # Get policy instance (not class!)
            policy_class = getattr(ParallelPolicy, policy_str, ParallelPolicy.SuccessOnAll)
            policy = policy_class()  # Instantiate!
            return Parallel(name=node_def.id, policy=policy)
            
        # 2. Handle Custom Nodes (Registered Classes)
        cls = node_registry.get_class(node_def.type)
        if not cls:
             return py_trees.behaviours.Dummy(name=node_def.id)

        # Prepare kwargs
        kwargs = {}
        
        # Check constructor signature
        try:
            init_sig = inspect.signature(cls.__init__)
            
            for param_name, param in init_sig.parameters.items():
                if param_name in ["self", "args", "kwargs"]:
                    continue
                    
                if param_name == "name":
                    kwargs["name"] = node_def.id
                elif param_name == "state_manager":
                    kwargs["state_manager"] = self.state_manager
                elif param_name in node_def.config:
                    # Inject configuration values
                    val = node_def.config[param_name]
                    # Note: Runtime variable resolution ({{state.x}}) is not handled here yet.
                    # It relies on the Node implementation to support it, 
                    # OR we wrap the value in a helper if the node supports generic config.
                    kwargs[param_name] = val
        except Exception as e:
            print(f"Error inspecting signature for {node_def.type}: {e}")
        
        try:
            return cls(**kwargs)
        except Exception as e:
            print(f"Failed to instantiate {node_def.type}: {e}")
            return py_trees.behaviours.Dummy(name=node_def.id)
