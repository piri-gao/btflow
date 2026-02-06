import axios from 'axios';
import type { Edge, Node } from 'reactflow';

const devHost = typeof window !== 'undefined' && window.location.hostname
    ? window.location.hostname
    : 'localhost';
const devApiBase = `http://${devHost}:8000/api`;
const API_Base = import.meta.env.VITE_API_BASE || (typeof window !== 'undefined' && window.location.port === '5173'
    ? devApiBase
    : '/api');

export const fetchNodes = async () => {
    const res = await axios.get(`${API_Base}/nodes`);
    return res.data;
};

export const fetchTools = async () => {
    const res = await axios.get(`${API_Base}/tools`);
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
            config: n.data?.config || {},
            input_bindings: (n.data as any)?.input_bindings || {},
            output_bindings: (n.data as any)?.output_bindings || {}
        })),
        edges: workflow.edges.map(e => ({
            id: e.id,
            source: e.source,
            target: e.target
        })),
        // Include state for workflows
        state: workflow.state || {
            schema_name: "AutoState",
            fields: []
        }
    };
    await axios.put(`${API_Base}/workflows/${id}`, payload);
};

export const runWorkflow = async (id: string, initialState?: Record<string, any>) => {
    const payload = initialState ? { initial_state: initialState } : undefined;
    await axios.post(`${API_Base}/workflows/${id}/run`, payload);
};

export const stopWorkflow = async (id: string) => {
    await axios.post(`${API_Base}/workflows/${id}/stop`);
};

export const fetchSettings = async () => {
    const res = await axios.get(`${API_Base}/settings`);
    return res.data;
};

export const saveSettings = async (payload: {
    language: string;
    memory_enabled: boolean;
    api_key: string;
    base_url: string;
    model: string;
}) => {
    const res = await axios.post(`${API_Base}/settings`, payload);
    return res.data;
};

export const ingestMemory = async (payload: {
    workflowId: string;
    memoryId: string;
    chunkSize: number;
    overlap: number;
    files: File[];
}) => {
    const form = new FormData();
    form.append('workflow_id', payload.workflowId);
    form.append('memory_id', payload.memoryId);
    form.append('chunk_size', String(payload.chunkSize));
    form.append('overlap', String(payload.overlap));
    payload.files.forEach((file) => {
        form.append('files', file);
    });
    const res = await axios.post(`${API_Base}/memory/ingest`, form, {
        headers: { 'Content-Type': 'multipart/form-data' }
    });
    return res.data;
};
