import btflow
from typing import Dict, Any, Type, List
from pydantic import create_model
from btflow.core.state import StateManager
from .workflow_schema import WorkflowDefinition, NodeDefinition
from .node_registry import node_registry
from btflow import Sequence, Selector, Parallel
from btflow import ParallelPolicy
import inspect
from btflow.core.logging import logger
from btflow.tools import Tool, ToolNode
from btflow.nodes.agents.react import ToolExecutor

class WorkflowConverter:
    """
    Compiles a WorkflowDefinition JSON into a runnable py_trees instance.
    """
    
    def __init__(self, workflow: WorkflowDefinition):
        self.workflow = workflow
        self.node_map: Dict[str, btflow.Behaviour] = {}
        self.state_manager = self._create_state_manager()
    
    def compile(self) -> btflow.Behaviour:
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
                 return btflow.Dummy(name="Empty Workflow")
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
            def get_sort_key(node_id: str) -> tuple:
                x = 0
                y = 0
                node_type = ""
                for node_def in self.workflow.nodes:
                    if node_def.id == node_id:
                        if node_def.position:
                            x = node_def.position.x
                            y = node_def.position.y
                        node_type = node_def.type
                        break
                
                # Sort order: 
                # Strictly Left to Right (X), then Top to Bottom (Y).
                # No magic priorities or ID fallbacks.
                key = (x, y)
                return key
            
            # Debug Log: Print keys before sorting
            debug_keys = {cid: get_sort_key(cid) for cid in child_ids}
            logger.info("🔍 [Sort] Parent {}: Candidates: {}", parent_id, debug_keys)
            
            # Sort by X coordinate and node priority
            child_ids_sorted = sorted(child_ids, key=get_sort_key)
            logger.info("✅ [Sort] Result: {}", child_ids_sorted)
            
            children_nodes = []
            
            for child_id in child_ids_sorted:
                if child_id not in self.node_map:
                    continue 
                    
                # Recursively assemble children's children
                self._assemble_children(child_id, children_map)
                child_node = self.node_map[child_id]
                
                # Debug: log node types and capabilities
                logger.info("🔍 [Converter] Processing child {} (type: {}) for parent {} (type: {})", 
                            child_id, type(child_node).__name__, parent_id, type(parent_node).__name__)
                logger.info("🔍 [Converter] Parent has register_tool: {}, Child has tool attr: {}", 
                            hasattr(parent_node, "register_tool"), hasattr(child_node, "tool"))
                
                # Duck Typing: 如果父节点支持 register_tool，且子节点是 ToolNode
                if hasattr(parent_node, "register_tool") and hasattr(child_node, "tool"):
                    logger.info("🔧 [Converter] Injecting tool {} into {} (Duck Typed)", child_node.tool.name, parent_node.name)
                    parent_node.register_tool(child_node.tool)
                    # 注意：我们通常不把工具作为“行为节点”挂载，因为它不 update。
                    # 所以这里不加入 children_nodes。
                else:
                    children_nodes.append(child_node)
                
            if isinstance(parent_node, btflow.Composite):
                parent_node.add_children(children_nodes)
            elif isinstance(parent_node, btflow.Decorator):
                if len(children_nodes) == 1:
                    parent_node.decorate(children_nodes[0])
                else:
                    logger.warning("Decorator {} has {} children. Expected 1.", parent_id, len(children_nodes))
            elif hasattr(parent_node, "decorate") and len(children_nodes) == 1:
                # 特殊处理：像 LoopUntilSuccess 这样不继承 Decorator 但实现 decorate 的节点
                parent_node.decorate(children_nodes[0])
            elif isinstance(parent_node, ToolExecutor):
                # 虽然 ToolExecutor 可能不是复合节点，但如果它有普通子节点，
                # 目前 btflow 逻辑中它不管理子节点执行。
                pass
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
        
        # Create Dynamic Model with extra='allow'
        model_config = {"extra": "allow"}
        
        try:
            DynamicState = create_model(
                self.workflow.state.schema_name or "DynamicState", 
                __config__=model_config,
                **fields
            )
        except Exception:
            DynamicState = create_model(
                "DynamicState", 
                 __config__=model_config,
                **fields
            )
        
        # Create StateManager and initialize with default values
        sm = StateManager(schema=DynamicState)
        
        # Build initial state from field defaults
        initial_state = {}
        logger.info("📋 [Converter] workflow.state.fields has {} items: {}", 
                    len(self.workflow.state.fields), 
                    [(f.name, f.default) for f in self.workflow.state.fields])
        for field in self.workflow.state.fields:
            # 修复：不要跳过空字符串和空列表，只跳过 None
            initial_state[field.name] = field.default
        
        logger.info("📋 [Converter] Initializing state with: {}", initial_state)
        sm.initialize(initial_state)
        logger.info("📋 [Converter] State after init: {}", sm.get().model_dump())
        return sm



        
    def _create_node(self, node_def: NodeDefinition) -> btflow.Behaviour:
        logger.info("🔍 [Converter] Creating node {} (type: {})", node_def.id, node_def.type)
        
        meta = node_registry.get(node_def.type)
        if not meta:
            # Check built-in fallbacks if generic
            logger.warning("❌ [Converter] No metadata found for type {}, returning Dummy", node_def.type)
            return btflow.Dummy(name=node_def.id)
            
        # 1. Handle Built-in Composites
        if node_def.type == "Sequence":
            return Sequence(name=node_def.label or node_def.id, memory=node_def.config.get("memory", True))
        elif node_def.type == "Selector":
            return Selector(name=node_def.label or node_def.id, memory=node_def.config.get("memory", True))
        elif node_def.type == "Parallel":
            policy_str = node_def.config.get("policy", "SuccessOnAll")
            # Get policy instance (not class!)
            policy_class = getattr(ParallelPolicy, policy_str, ParallelPolicy.SuccessOnAll)
            policy = policy_class()  # Instantiate!
            return Parallel(name=node_def.label or node_def.id, policy=policy)
            
        # 2. Handle Custom Nodes (Registered Classes)
        cls = node_registry.get_class(node_def.type)
        logger.info("🔍 [Converter] Got class for {}: {} (callable: {})", node_def.type, cls, callable(cls))
        if not cls:
            logger.warning("❌ [Converter] No class found for type {}, returning Dummy", node_def.type)
            return btflow.Dummy(name=node_def.id)

        # Prepare kwargs
        kwargs = {}
        
        # Check constructor signature
        try:
            init_sig = inspect.signature(cls.__init__)
            
            for param_name, param in init_sig.parameters.items():
                if param_name in ["self", "args", "kwargs"]:
                    continue
                    
                if param_name == "name":
                    kwargs["name"] = node_def.label or node_def.id
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
            logger.error("Error inspecting signature for {}: {}", node_def.type, e)
        
        try:
            instance = cls(**kwargs)
            
            # Debug log for tool detection
            logger.info("🔍 [Converter] Created instance {} (type: {}), has run: {}, has description: {}, is Behaviour: {}", 
                       node_def.id, type(instance).__name__, 
                       hasattr(instance, "run"), hasattr(instance, "description"), isinstance(instance, btflow.Behaviour))
            
            # Special handling for Tools: Wrap in ToolNode
            # Use Duck Typing to avoid import issues
            if hasattr(instance, "run") and hasattr(instance, "description") and not isinstance(instance, btflow.Behaviour):
                logger.info("🔧 [Converter] Wrapping tool {} in ToolNode (Duck Typed)", getattr(instance, "name", "unnamed"))
                # Use label as node name and instance as tool
                return ToolNode(name=node_def.label or f"{getattr(instance, 'name', 'tool')}_node", tool=instance)
                
            return instance
        except Exception as e:
            logger.error("Failed to instantiate {}: {}", node_def.type, e)
            import traceback
            logger.error("Traceback: {}", traceback.format_exc())
            return btflow.Dummy(name=node_def.id)
