import unittest
from btflow import Sequence, Selector, Parallel, Status
from btflow_studio.backend.app.workflow_schema import WorkflowDefinition, NodeDefinition, EdgeDefinition, StateDefinition, StateFieldDefinition
from btflow_studio.backend.app.converter import WorkflowConverter
from btflow_studio.backend.app.node_registry import node_registry, NodeMetadata

class TestWorkflowConverter(unittest.TestCase):
    
    def setUp(self):
        pass

    def test_simple_sequence(self):
        """Test converting a simple Sequence with two dummy children."""
        
        # Define Workflow
        workflow = WorkflowDefinition(
            name="Test Sequence",
            nodes=[
                NodeDefinition(id="root", type="Sequence", label="Main Sequence"),
                NodeDefinition(id="child1", type="Parallel", label="Worker 1"),
                NodeDefinition(id="child2", type="Selector", label="Worker 2")
            ],
            edges=[
                EdgeDefinition(id="e1", source="root", target="child1"),
                EdgeDefinition(id="e2", source="root", target="child2")
            ]
        )
        
        converter = WorkflowConverter(workflow)
        root = converter.compile()
        
        # Verify Root
        self.assertIsInstance(root, Sequence)
        self.assertEqual(root.name, "Main Sequence")
        
        # Verify Children
        self.assertEqual(len(root.children), 2)
        child1 = root.children[0]
        child2 = root.children[1]
        
        self.assertIsInstance(child1, Parallel)
        self.assertEqual(child1.name, "Worker 1")
        
        self.assertIsInstance(child2, Selector)
        self.assertEqual(child2.name, "Worker 2")

    def test_state_schema_generation(self):
        """Test if StateManager is created with correct schema."""
        workflow = WorkflowDefinition(
            state=StateDefinition(
                fields=[
                    StateFieldDefinition(name="score", type="int", default=0),
                    StateFieldDefinition(name="tags", type="list", default=[])
                ]
            )
        )
        
        converter = WorkflowConverter(workflow)
        state_manager = converter.state_manager
        
        # Check initial state
        state = state_manager.get()
        self.assertEqual(state.score, 0)
        self.assertEqual(state.tags, [])
        
        # Update state
        state_manager.update({"score": 100, "tags": ["a"]})
        new_state = state_manager.get()
        self.assertEqual(new_state.score, 100)
        self.assertEqual(new_state.tags, ["a"])

if __name__ == '__main__':
    unittest.main()
