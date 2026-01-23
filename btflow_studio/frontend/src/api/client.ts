import axios from 'axios';
import type { Edge, Node } from 'reactflow';

const API_Base = 'http://localhost:8000/api';

export const fetchNodes = async () => {
    const res = await axios.get(`${API_Base}/nodes`);
    return res.data;
};

export const createWorkflow = async (name: string) => {
    const res = await axios.post(`${API_Base}/workflows`, { name });
    return res.data;
};

export const saveWorkflow = async (id: string, workflow: { nodes: Node[], edges: Edge[], state?: any }) => {
    // Convert React Flow types to backend JSON format
    const payload = {
        nodes: workflow.nodes.map(n => ({
            id: n.id,
            type: n.data?.nodeType || n.type || 'Sequence', // Use specific type if available
            label: n.data?.label || n.data?.nodeType || n.id,
            position: n.position,
            config: n.data?.config || {}
        })),
        edges: workflow.edges.map(e => ({
            id: e.id,
            source: e.source,
            target: e.target
        })),
        // Include state for ReAct workflows
        state: workflow.state || {
            schema_name: "ReActState",
            fields: [
                { name: "messages", type: "list", default: [] },
                { name: "final_answer", type: "str", default: "" },
                { name: "round", type: "int", default: 0 },
                { name: "task", type: "str", default: "" }
            ]
        }
    };
    await axios.put(`${API_Base}/workflows/${id}`, payload);
};

export const runWorkflow = async (id: string) => {
    await axios.post(`${API_Base}/workflows/${id}/run`);
};

export const stopWorkflow = async (id: string) => {
    await axios.post(`${API_Base}/workflows/${id}/stop`);
};
