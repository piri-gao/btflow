import unittest
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'btflow-studio'))

from fastapi.testclient import TestClient
from backend.app.server import app

class TestStudioAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_list_nodes(self):
        response = self.client.get("/api/nodes")
        self.assertEqual(response.status_code, 200)
        nodes = response.json()
        self.assertIsInstance(nodes, list)
        # Check for built-in nodes
        ids = [n['id'] for n in nodes]
        self.assertIn("Sequence", ids)
        self.assertIn("Selector", ids)

    def test_workflow_crud(self):
        # 1. Create
        wf_data = {"name": "Test Flow", "description": "A test workflow"}
        response = self.client.post("/api/workflows", json=wf_data)
        self.assertEqual(response.status_code, 200)
        wf = response.json()
        wf_id = wf["id"]
        self.assertEqual(wf["name"], "Test Flow")
        
        # 2. List
        response = self.client.get("/api/workflows")
        self.assertEqual(response.status_code, 200)
        wfs = response.json()
        self.assertGreaterEqual(len(wfs), 1)
        
        # 3. Get Detail
        response = self.client.get(f"/api/workflows/{wf_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], wf_id)
        
        # 4. Update
        wf["name"] = "Updated Flow"
        response = self.client.put(f"/api/workflows/{wf_id}", json=wf)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Updated Flow")
        
        # 5. Delete
        response = self.client.delete(f"/api/workflows/{wf_id}")
        self.assertEqual(response.status_code, 200)
        
        # Verify Deletion
        response = self.client.get(f"/api/workflows/{wf_id}")
        self.assertEqual(response.status_code, 404)

if __name__ == '__main__':
    unittest.main()
