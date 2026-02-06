import React, { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  ReactFlowProvider,
  useNodesState,
  useEdgesState,
  addEdge,
  Panel,
  type Connection,
  type Edge,
  type ReactFlowInstance,
  type Node,
  type NodeTypes,
  type OnSelectionChangeParams
} from 'reactflow';
import 'reactflow/dist/style.css';
import LeftPanel from './components/LeftPanel';
import NodePanel from './components/NodePanel';
import LogPanel from './components/LogPanel';
import ChatPanel from './components/ChatPanel';
import { ControlFlowNode, ActionNode } from './components/CustomNodes';
import { fetchNodes, fetchTools, saveWorkflow, runWorkflow, stopWorkflow, createWorkflow } from './api/client';

interface LogEntry {
  timestamp: string;
  type: 'log' | 'status' | 'error' | 'trace';
  message: string;
}

interface TraceEvent {
  timestamp: string;
  event: string;
  data: Record<string, any>;
}

interface ToolEvent {
  timestamp: string;
  event: 'tool_call' | 'tool_result';
  data: Record<string, any>;
}

interface ChatMessage {
  role: 'user' | 'model';
  content: string;
}

interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  generatedWorkflow?: { nodes: any[]; edges: any[] } | null;
}

interface StateField {
  name: string;
  type: string;
  default: any;
}

const HIDDEN_INIT_FIELDS = new Set([
  'tools_desc',
  'tools_schema',
  'round',
  'final_answer',
  'streaming_output',
  'score',
  'rounds',
  'score_history',
]);

const initialNodes: Node[] = [];
const initialEdges: Edge[] = [];
const STORAGE_KEYS = {
  nodes: 'btflow.studio.nodes',
  edges: 'btflow.studio.edges',
  workflowId: 'btflow.studio.workflowId',
  chatSessions: 'btflow.studio.chatSessions',
  activeChatSessionId: 'btflow.studio.activeChatSessionId',
  lastRunMessages: 'btflow.studio.lastRunMessages',
  reuseMessages: 'btflow.studio.reuseMessages',
};

// Define once outside component to avoid re-creation
const nodeTypes: NodeTypes = {
  controlFlow: ControlFlowNode,
  action: ActionNode,
};
const edgeTypes = {};

// Helper to determine node visual type from nodeType
const getNodeVisualType = (nodeType: string): string => {
  const controlFlowTypes = ['Sequence', 'Selector', 'Parallel'];

  if (controlFlowTypes.includes(nodeType)) return 'controlFlow';
  return 'action';
};

const normalizeBinding = (value: any, fallback: string): string => {
  if (!value) return fallback;
  if (typeof value === 'string' && value.startsWith('state.')) {
    return value.slice('state.'.length);
  }
  return String(value).trim();
};

const normalizePorts = (ports: any[]): { name: string; type: string; default: any }[] => {
  if (!ports) return [];
  return ports.map((p) => {
    if (typeof p === 'string') {
      return { name: p, type: 'str', default: '' };
    }
    return {
      name: p.name,
      type: p.type || 'str',
      default: p.default ?? '',
    };
  });
};

const inferStateFields = (nodes: Node[], nodeMetas: any[]): StateField[] => {
  const fields: Record<string, StateField> = {};

  nodes.forEach((node) => {
    const meta = nodeMetas.find((m) => m.id === (node.data as any)?.nodeType || m.id === node.type);
    if (!meta) return;

    const inputBindings = (node.data as any)?.input_bindings || {};
    const outputBindings = (node.data as any)?.output_bindings || {};

    normalizePorts(meta.inputs || []).forEach((port) => {
      const target = normalizeBinding(inputBindings[port.name], port.name);
      if (!fields[target]) {
        fields[target] = { name: target, type: port.type, default: port.default };
      }
    });

    normalizePorts(meta.outputs || []).forEach((port) => {
      const target = normalizeBinding(outputBindings[port.name], port.name);
      if (!fields[target]) {
        fields[target] = { name: target, type: port.type, default: port.default };
      }
    });
  });

  if (Object.keys(fields).length === 0) {
    fields['messages'] = { name: 'messages', type: 'list', default: [] };
    fields['task'] = { name: 'task', type: 'str', default: '' };
    fields['round'] = { name: 'round', type: 'int', default: 0 };
  }

  return Object.values(fields);
};

const inferInputFields = (nodes: Node[], nodeMetas: any[]): StateField[] => {
  const fields: Record<string, StateField> = {};

  nodes.forEach((node) => {
    const meta = nodeMetas.find((m) => m.id === (node.data as any)?.nodeType || m.id === node.type);
    if (!meta) return;
    const inputBindings = (node.data as any)?.input_bindings || {};

    normalizePorts(meta.inputs || []).forEach((port) => {
      const target = normalizeBinding(inputBindings[port.name], port.name);
      if (HIDDEN_INIT_FIELDS.has(target)) return;
      if (!fields[target]) {
        fields[target] = { name: target, type: port.type, default: port.default };
      }
    });
  });

  if (Object.keys(fields).length === 0) {
    fields['messages'] = { name: 'messages', type: 'list', default: [] };
    fields['task'] = { name: 'task', type: 'str', default: '' };
  }

  return Object.values(fields);
};

function Flow() {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [nodeMetas, setNodeMetas] = useState<any[]>([]);
  const [tools, setTools] = useState<any[]>([]);

  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [traceEvents, setTraceEvents] = useState<TraceEvent[]>([]);
  const [toolEvents, setToolEvents] = useState<ToolEvent[]>([]);
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([]);
  const [activeChatSessionId, setActiveChatSessionId] = useState<string>('');
  const [hasHydrated, setHasHydrated] = useState(false);
  const [rightPanelTab, setRightPanelTab] = useState<'properties' | 'chat'>('properties');
  const [showInitialState, setShowInitialState] = useState(false);
  const [initialStateValues, setInitialStateValues] = useState<Record<string, any>>({});
  const [initialStateError, setInitialStateError] = useState<string>('');
  const [lastMessagesByWorkflow, setLastMessagesByWorkflow] = useState<Record<string, any[]>>({});
  const [reuseMessagesByWorkflow, setReuseMessagesByWorkflow] = useState<Record<string, boolean>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);
  const initPanelRef = useRef<HTMLDivElement>(null);

  // Derive selectedNode from nodes to keep it in sync
  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null;
    return nodes.find(n => n.id === selectedNodeId) || null;
  }, [nodes, selectedNodeId]);

  useEffect(() => {
    if (!hasHydrated) return;
    localStorage.setItem(STORAGE_KEYS.nodes, JSON.stringify(nodes));
  }, [nodes, hasHydrated]);

  useEffect(() => {
    if (!hasHydrated) return;
    localStorage.setItem(STORAGE_KEYS.edges, JSON.stringify(edges));
  }, [edges, hasHydrated]);

  useEffect(() => {
    if (!hasHydrated || !workflowId) return;
    localStorage.setItem(STORAGE_KEYS.workflowId, workflowId);
  }, [workflowId, hasHydrated]);

  useEffect(() => {
    if (!hasHydrated) return;
    localStorage.setItem(STORAGE_KEYS.chatSessions, JSON.stringify(chatSessions));
  }, [chatSessions, hasHydrated]);

  useEffect(() => {
    if (!hasHydrated || !activeChatSessionId) return;
    localStorage.setItem(STORAGE_KEYS.activeChatSessionId, activeChatSessionId);
  }, [activeChatSessionId, hasHydrated]);

  useEffect(() => {
    if (!hasHydrated) return;
    localStorage.setItem(STORAGE_KEYS.lastRunMessages, JSON.stringify(lastMessagesByWorkflow));
  }, [lastMessagesByWorkflow, hasHydrated]);

  useEffect(() => {
    if (!hasHydrated) return;
    localStorage.setItem(STORAGE_KEYS.reuseMessages, JSON.stringify(reuseMessagesByWorkflow));
  }, [reuseMessagesByWorkflow, hasHydrated]);

  const inferredStateFields = useMemo(
    () => inferStateFields(nodes, nodeMetas),
    [nodes, nodeMetas]
  );

  const inferredInputFields = useMemo(
    () => inferInputFields(nodes, nodeMetas),
    [nodes, nodeMetas]
  );

  useEffect(() => {
    if (!hasHydrated) return;
    if (!chatSessions.length) {
      const fallbackId = 'session-1';
      setChatSessions([{ id: fallbackId, title: 'Session 1', messages: [], generatedWorkflow: null }]);
      setActiveChatSessionId(fallbackId);
      return;
    }
    if (!activeChatSessionId || !chatSessions.find(s => s.id === activeChatSessionId)) {
      setActiveChatSessionId(chatSessions[0].id);
    }
  }, [chatSessions, activeChatSessionId, hasHydrated]);

  useEffect(() => {
    setInitialStateValues((prev) => {
      const next = { ...prev };
      inferredInputFields.forEach((field) => {
        if (next[field.name] !== undefined) return;
        if (field.type === 'list' || field.type === 'dict' || field.type === 'tuple') {
          next[field.name] = JSON.stringify(field.default ?? (field.type === 'dict' ? {} : []), null, 2);
        } else {
          next[field.name] = field.default ?? '';
        }
      });
      return next;
    });
  }, [inferredInputFields]);


  useEffect(() => {
    fetchNodes().then(setNodeMetas).catch(err => console.error("Failed to fetch nodes", err));
    fetchTools().then(setTools).catch(err => console.error("Failed to fetch tools", err));
    const storedNodes = localStorage.getItem(STORAGE_KEYS.nodes);
    const storedEdges = localStorage.getItem(STORAGE_KEYS.edges);
    const storedWorkflowId = localStorage.getItem(STORAGE_KEYS.workflowId);
    const storedSessions = localStorage.getItem(STORAGE_KEYS.chatSessions);
    const storedActiveSession = localStorage.getItem(STORAGE_KEYS.activeChatSessionId);
    const storedLastRunMessages = localStorage.getItem(STORAGE_KEYS.lastRunMessages);
    const storedReuseMessages = localStorage.getItem(STORAGE_KEYS.reuseMessages);

    if (storedNodes) {
      try {
        const parsed = JSON.parse(storedNodes);
        setNodes(parsed);
      } catch {
        localStorage.removeItem(STORAGE_KEYS.nodes);
      }
    }
    if (storedEdges) {
      try {
        const parsed = JSON.parse(storedEdges);
        setEdges(parsed);
      } catch {
        localStorage.removeItem(STORAGE_KEYS.edges);
      }
    }
    if (storedSessions) {
      try {
        const parsed = JSON.parse(storedSessions);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setChatSessions(parsed);
        }
      } catch {
        localStorage.removeItem(STORAGE_KEYS.chatSessions);
      }
    }
    if (storedActiveSession) {
      setActiveChatSessionId(storedActiveSession);
    }
    if (storedLastRunMessages) {
      try {
        setLastMessagesByWorkflow(JSON.parse(storedLastRunMessages));
      } catch {
        localStorage.removeItem(STORAGE_KEYS.lastRunMessages);
      }
    }
    if (storedReuseMessages) {
      try {
        setReuseMessagesByWorkflow(JSON.parse(storedReuseMessages));
      } catch {
        localStorage.removeItem(STORAGE_KEYS.reuseMessages);
      }
    }

    if (storedWorkflowId) {
      setWorkflowId(storedWorkflowId);
    } else {
      // Auto-create a session workflow for now
      createWorkflow("Untitled Session").then(wf => {
        setWorkflowId(wf.id);
        localStorage.setItem(STORAGE_KEYS.workflowId, wf.id);
        console.log("Created session:", wf.id);
      });
    }
    setTimeout(() => setHasHydrated(true), 0);
  }, []);

  // WebSocket Connection
  useEffect(() => {
    if (!workflowId) return;

    const ws = new WebSocket(`ws://localhost:8000/ws/${workflowId}`);

    ws.onopen = () => console.log("Connected to WS");

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'node_update') {
          // data is { nodeId: "SUCCESS" | "RUNNING" | "FAILURE" }
          setNodes((nds) => nds.map(n => {
            if (msg.data[n.id]) {
              return {
                ...n,
                data: {
                  ...n.data,
                  status: msg.data[n.id]
                }
              };
            }
            return n;
          }));
        }
        else if (msg.type === 'status') {
          console.log("Workflow Status:", msg.status);
          const timestamp = new Date().toLocaleTimeString();
          setLogs(prev => [...prev, { timestamp, type: 'status', message: `Workflow ${msg.status}` }]);
          if (msg.status === 'running') {
            setIsRunning(true);
            setNodes(nds => nds.map(n => ({ ...n, style: { ...n.style, backgroundColor: '#fff' } })));
          } else if (['completed', 'stopped', 'idle', 'error'].includes(msg.status)) {
            setIsRunning(false);
            setNodes(nds => nds.map(n => ({
              ...n,
              data: { ...n.data, status: undefined }
            })));
          }
        }
        else if (msg.type === 'log') {
          const timestamp = new Date().toLocaleTimeString();
          setLogs(prev => [...prev, { timestamp, type: 'log', message: msg.message }]);
        }
        else if (msg.type === 'state_update') {
          const state = msg.data || {};
          if (workflowId && Array.isArray(state.messages)) {
            setLastMessagesByWorkflow(prev => ({
              ...prev,
              [workflowId]: state.messages
            }));
          }
        }
        else if (msg.type === 'trace') {
          const timestamp = new Date().toLocaleTimeString();
          const data = msg.data || {};
          if (msg.event !== 'llm_token') {
            setTraceEvents(prev => [...prev, { timestamp, event: msg.event, data }]);
          }
          if (msg.event === 'tool_call' || msg.event === 'tool_result') {
            setToolEvents(prev => [...prev, { timestamp, event: msg.event, data }]);
          }
          const parts: string[] = [];
          if (data.node) parts.push(`node=${data.node}`);
          if (data.tool) parts.push(`tool=${data.tool}`);
          if (data.model) parts.push(`model=${data.model}`);
          if (typeof data.ok === 'boolean') parts.push(`ok=${data.ok}`);
          if (data.error) parts.push(`error=${data.error}`);
          const details = parts.length ? ` ${parts.join(' ')}` : '';
          // Trace events are displayed in the Trace tab only.
        }
      } catch (e) {
        console.error("WS Parse error", e);
      }
    };

    ws.onerror = (error) => console.error("WS Error:", error);
    ws.onclose = () => console.log("WS Disconnected");

    return () => ws.close();
  }, [workflowId, setNodes]);

  useEffect(() => {
    if (!showInitialState) return;
    const handleClick = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (!target) return;
      if (initPanelRef.current && initPanelRef.current.contains(target)) return;
      setShowInitialState(false);
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowInitialState(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleKey);
    };
  }, [showInitialState]);

  const onSelectionChange = useCallback(({ nodes }: OnSelectionChangeParams) => {
    if (nodes.length > 0) {
      setSelectedNodeId(nodes[0].id);
    } else {
      setSelectedNodeId(null);
    }
  }, []);

  const onConnect = useCallback(
    (params: Connection | Edge) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();

      const type = event.dataTransfer.getData('application/reactflow/type');
      const label = event.dataTransfer.getData('application/reactflow/label');

      if (typeof type === 'undefined' || !type) {
        return;
      }

      let position = { x: 0, y: 0 };
      if (reactFlowInstance) {
        position = reactFlowInstance.screenToFlowPosition({
          x: event.clientX,
          y: event.clientY,
        });
      }

      const newNode: Node = {
        id: `${type}_${Date.now()}`,
        type: getNodeVisualType(type),
        position,
        data: {
          label: label,
          nodeType: type,
          config: {},
          input_bindings: {},
          output_bindings: {},
          icon: nodeMetas.find(n => n.id === type)?.icon || '📦'
        },
      };

      setNodes((nds) => nds.concat(newNode));
    },
    [reactFlowInstance, setNodes]
  );

  const onSave = useCallback(async () => {
    if (!reactFlowInstance || !workflowId) return;

    try {
      await saveWorkflow(workflowId, {
        nodes,
        edges,
        state: {
          schema_name: 'AutoState',
          fields: inferredStateFields
        }
      });
    } catch (error: any) {
      // If workflow not found (404), create a new one
      if (error?.response?.status === 404) {
        console.log("Workflow not found, creating new one...");
        const newWf = await createWorkflow("Recovered Workflow");
        setWorkflowId(newWf.id);
        await saveWorkflow(newWf.id, {
          nodes,
          edges,
          state: {
            schema_name: 'AutoState',
            fields: inferredStateFields
          }
        });
      } else {
        console.error("Save failed:", error);
      }
    }
  }, [reactFlowInstance, nodes, edges, workflowId, inferredStateFields]);

  const buildInitialState = useCallback((): { state?: Record<string, any>; error?: string } => {
    const state: Record<string, any> = {};
    let messagesProvided = false;
    const hasMessagesField = inferredInputFields.some((field) => field.name === 'messages');
    for (const field of inferredInputFields) {
      const raw = initialStateValues[field.name];
      if (field.type === 'bool') {
        if (typeof raw === 'boolean') {
          state[field.name] = raw;
        }
        continue;
      }
      if (field.type === 'int' || field.type === 'float') {
        if (raw === '' || raw === null || raw === undefined) continue;
        const num = Number(raw);
        if (Number.isNaN(num)) {
          return { error: `Field '${field.name}' expects a number` };
        }
        state[field.name] = num;
        continue;
      }
      if (field.type === 'list' || field.type === 'dict' || field.type === 'tuple') {
        if (raw === '' || raw === null || raw === undefined) continue;
        if (field.name === 'messages' && typeof raw === 'string') {
          try {
            const parsed = JSON.parse(raw);
            state[field.name] = parsed;
            messagesProvided = true;
          } catch {
            state[field.name] = [{ role: 'user', content: raw }];
            messagesProvided = true;
          }
          continue;
        }
        if (typeof raw === 'string') {
          try {
            const parsed = JSON.parse(raw);
            state[field.name] = parsed;
            if (field.name === 'messages') messagesProvided = true;
          } catch {
            return { error: `Field '${field.name}' expects JSON` };
          }
        } else {
          state[field.name] = raw;
          if (field.name === 'messages') messagesProvided = true;
        }
        continue;
      }
      if (raw === '' || raw === null || raw === undefined) continue;
      state[field.name] = raw;
      if (field.name === 'messages') messagesProvided = true;
    }
    if (!messagesProvided && hasMessagesField && workflowId) {
      const reuse = !!reuseMessagesByWorkflow[workflowId];
      const lastMessages = lastMessagesByWorkflow[workflowId];
      if (reuse && Array.isArray(lastMessages) && lastMessages.length > 0) {
        state.messages = lastMessages;
      }
    }
    return { state };
  }, [initialStateValues, inferredInputFields, lastMessagesByWorkflow, reuseMessagesByWorkflow, workflowId]);

  const onRun = useCallback(async () => {
    if (!workflowId) return;
    const result = buildInitialState();
    if (result.error) {
      setInitialStateError(result.error || 'Invalid initial state');
      return;
    }
    setInitialStateError('');
    await onSave();
    await runWorkflow(workflowId, result.state);
    setShowInitialState(false);
  }, [workflowId, onSave, buildInitialState]);

  const onStop = useCallback(async () => {
    if (!workflowId) return;
    await stopWorkflow(workflowId);
  }, [workflowId]);

  const applyWorkflow = useCallback((workflow: { nodes: any[], edges: any[] }) => {
    // Convert workflow JSON to React Flow format
    const newNodes: Node[] = workflow.nodes.map(n => ({
      id: n.id,
      type: getNodeVisualType(n.type),
      position: n.position || { x: 0, y: 0 },
      data: {
        label: n.label || n.type,
        nodeType: n.type,
        config: n.config || {},
        input_bindings: n.input_bindings || {},
        output_bindings: n.output_bindings || {},
        icon: n.icon || (nodeMetas.find(m => m.id === n.type)?.icon) || '📦'
      }
    }));

    const newEdges: Edge[] = workflow.edges.map(e => ({
      id: e.id,
      source: e.source,
      target: e.target
    }));

    setNodes(newNodes);
    setEdges(newEdges);
  }, [setNodes, setEdges, nodeMetas]);

  const createChatSession = useCallback(() => {
    const id = `session-${Date.now()}`;
    setChatSessions((prev) => [
      { id, title: `Session ${prev.length + 1}`, messages: [], generatedWorkflow: null },
      ...prev
    ]);
    setActiveChatSessionId(id);
  }, []);

  const updateChatSession = useCallback((id: string, updater: (session: ChatSession) => ChatSession) => {
    setChatSessions((prev) => prev.map((s) => (s.id === id ? updater(s) : s)));
  }, []);

  const deleteChatSession = useCallback((id: string) => {
    setChatSessions((prev) => {
      const next = prev.filter((s) => s.id !== id);
      if (next.length === 0) {
        const fallbackId = `session-${Date.now()}`;
        setActiveChatSessionId(fallbackId);
        return [{ id: fallbackId, title: 'Session 1', messages: [], generatedWorkflow: null }];
      }
      if (activeChatSessionId === id) {
        setActiveChatSessionId(next[0].id);
      }
      return next;
    });
  }, [activeChatSessionId]);

  const onClearCanvas = useCallback(() => {
    setNodes([]);
    setEdges([]);
    setSelectedNodeId(null);
  }, [setNodes, setEdges]);

  const onSaveLocal = useCallback(async () => {
    if (!workflowId) return;
    await onSave();
    const payload = {
      version: '1.0',
      id: workflowId,
      name: 'Local Workflow',
      nodes: nodes.map(n => ({
        id: n.id,
        type: n.data?.nodeType || n.type || 'Sequence',
        label: n.data?.label || n.data?.nodeType || n.id,
        position: n.position,
        config: n.data?.config || {},
        input_bindings: (n.data as any)?.input_bindings || {},
        output_bindings: (n.data as any)?.output_bindings || {}
      })),
      edges: edges.map(e => ({
        id: e.id,
        source: e.source,
        target: e.target
      })),
      state: {
        schema_name: 'AutoState',
        fields: inferredStateFields
      }
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `btflow-workflow-${workflowId.slice(0, 6)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [workflowId, nodes, edges, onSave, inferredStateFields]);

  const onLoadLocal = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const onFileSelected = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(reader.result as string);
        if (!parsed.nodes || !parsed.edges) {
          throw new Error('Invalid workflow file');
        }
        applyWorkflow({ nodes: parsed.nodes, edges: parsed.edges });
      } catch (err) {
        console.error('Failed to load workflow:', err);
      }
    };
    reader.readAsText(file);
    event.target.value = '';
  }, [applyWorkflow]);

  useEffect(() => {
    if (!showInitialState) return;
    const handler = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      if (initPanelRef.current && target && !initPanelRef.current.contains(target)) {
        setShowInitialState(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showInitialState]);

  return (
    <div className="flex flex-col h-screen w-screen bg-gray-50">
      {/* Top Area: Sidebar + Canvas + NodePanel */}
      <div className="flex flex-1 overflow-hidden">
        <ReactFlowProvider>
          {/* Sidebar */}
          <LeftPanel
            nodeMetas={nodeMetas}
            tools={tools}
            onApplyWorkflow={applyWorkflow}
            workflowId={workflowId}
            currentWorkflow={{
              nodes: nodes.map(n => ({
                id: n.id,
                type: n.data?.nodeType || n.type || 'Sequence',
                label: n.data?.label || n.data?.nodeType || n.id,
                position: n.position,
                config: n.data?.config || {},
                input_bindings: (n.data as any)?.input_bindings || {},
                output_bindings: (n.data as any)?.output_bindings || {}
              })),
              edges: edges.map(e => ({
                id: e.id,
                source: e.source,
                target: e.target
              }))
            }}
          />

          {/* Main Canvas */}
          <div className="flex-1 h-full relative" ref={reactFlowWrapper}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onInit={setReactFlowInstance}
              onDrop={onDrop}
              onDragOver={onDragOver}
              onSelectionChange={onSelectionChange}
              fitView
            >
              <Background />
              <Controls />
              <MiniMap />
              <Panel position="top-right" className="bg-white p-2 rounded shadow-md flex gap-2 border border-gray-200 relative">
                <button onClick={onSaveLocal} disabled={isRunning} className={`px-3 py-1 rounded text-sm font-medium border border-gray-300 ${isRunning ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : 'bg-white hover:bg-gray-50'}`}>
                  💾 Save
                </button>
                <button onClick={onLoadLocal} disabled={isRunning} className={`px-3 py-1 rounded text-sm font-medium border border-gray-300 ${isRunning ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : 'bg-white hover:bg-gray-50'}`}>
                  📂 Load
                </button>
                <button onClick={onClearCanvas} disabled={isRunning} className={`px-3 py-1 rounded text-sm font-medium border border-gray-300 ${isRunning ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : 'bg-white hover:bg-gray-50'}`}>
                  🧹 Clear
                </button>

                <button
                  onClick={() => setShowInitialState((prev) => !prev)}
                  disabled={isRunning}
                  className={`px-3 py-1 rounded text-sm font-medium border border-gray-300 ${isRunning ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : 'bg-white hover:bg-gray-50'}`}
                >
                  ⚙️ Init
                </button>

                {!isRunning ? (
                  <button onClick={onRun} className="px-3 py-1 bg-green-600 hover:bg-green-700 text-white rounded text-sm font-medium flex items-center gap-1 shadow-sm">
                    ▶️ Run
                  </button>
                ) : (
                  <button onClick={onStop} className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white rounded text-sm font-medium flex items-center gap-1 shadow-sm">
                    ⏹️ Stop
                  </button>
                )}

                {workflowId && <span className="text-xs text-gray-400 self-center border-l pl-2 ml-1">ID: {workflowId.slice(0, 6)}...</span>}

                {showInitialState && (
                  <div ref={initPanelRef} className="absolute right-0 top-full mt-2 w-72 bg-white border border-gray-200 rounded shadow-lg p-3 text-xs z-10">
                    <div className="font-semibold text-gray-700 mb-2">Initial State</div>
                    <div className="max-h-64 overflow-auto pr-1">
                      {inferredInputFields.map((field) => (
                        <div key={field.name} className="mb-2">
                          <label className="block text-[10px] text-gray-500 mb-1">
                            {field.name} <span className="text-gray-400">({field.type})</span>
                          </label>
                          {field.type === 'bool' ? (
                            <input
                              type="checkbox"
                              checked={!!initialStateValues[field.name]}
                              onChange={(e) =>
                                setInitialStateValues((prev) => ({ ...prev, [field.name]: e.target.checked }))
                              }
                            />
                          ) : field.type === 'int' || field.type === 'float' ? (
                            <input
                              type="number"
                              className="w-full text-xs p-1 border rounded"
                              value={initialStateValues[field.name] ?? ''}
                              onChange={(e) =>
                                setInitialStateValues((prev) => ({ ...prev, [field.name]: e.target.value }))
                              }
                            />
                          ) : field.type === 'list' || field.type === 'dict' || field.type === 'tuple' ? (
                            <textarea
                              className="w-full text-xs p-1 border rounded font-mono"
                              rows={3}
                              placeholder={field.name === 'messages' ? '输入一段话，或 JSON 数组' : 'JSON'}
                              value={initialStateValues[field.name] ?? ''}
                              onChange={(e) =>
                                setInitialStateValues((prev) => ({ ...prev, [field.name]: e.target.value }))
                              }
                            />
                          ) : (
                            <input
                              className="w-full text-xs p-1 border rounded"
                              value={initialStateValues[field.name] ?? ''}
                              onChange={(e) =>
                                setInitialStateValues((prev) => ({ ...prev, [field.name]: e.target.value }))
                              }
                              placeholder={field.name === 'task' ? '例如：用一句话介绍你自己' : ''}
                            />
                          )}
                        </div>
                      ))}
                    </div>
                    {workflowId && inferredInputFields.some((field) => field.name === 'messages') && (
                      <label className="flex items-center gap-2 text-[10px] text-gray-500 mt-2">
                        <input
                          type="checkbox"
                          checked={!!reuseMessagesByWorkflow[workflowId]}
                          onChange={(e) =>
                            setReuseMessagesByWorkflow((prev) => ({
                              ...prev,
                              [workflowId]: e.target.checked
                            }))
                          }
                        />
                        复用上次对话消息（未填写 messages 时生效）
                      </label>
                    )}
                    {initialStateError && (
                      <div className="text-[10px] text-red-500 mt-2">{initialStateError}</div>
                    )}
                    <div className="text-[10px] text-gray-400 mt-2">
                      留空表示使用默认值。
                    </div>
                  </div>
                )}
              </Panel>
            </ReactFlow>
          </div>

          {/* Right Panel - Tabbed Interface */}
          <div className="w-80 border-l border-gray-200 bg-white flex flex-col">
            {/* Tab Headers */}
            <div className="flex border-b border-gray-200">
              <button
                onClick={() => setRightPanelTab('properties')}
                className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${rightPanelTab === 'properties'
                  ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                  : 'text-gray-600 hover:text-gray-800 hover:bg-gray-50'
                  }`}
              >
                Properties
              </button>
              <button
                onClick={() => setRightPanelTab('chat')}
                className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${rightPanelTab === 'chat'
                  ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                  : 'text-gray-600 hover:text-gray-800 hover:bg-gray-50'
                  }`}
              >
                🤖 AI Assistant
              </button>
            </div>

            {/* Tab Content */}
            <div className="flex-1 overflow-hidden">
              {rightPanelTab === 'properties' ? (
                <NodePanel
                  selectedNode={selectedNode}
                  setNodes={setNodes}
                  nodeMetas={nodeMetas}
                  tools={tools}
                />
              ) : (
                <ChatPanel
                  currentWorkflow={{ nodes, edges }}
                  onApplyWorkflow={applyWorkflow}
                  availableNodes={nodeMetas}
                  availableTools={tools}
                  sessions={chatSessions}
                  activeSessionId={activeChatSessionId}
                  onSelectSession={setActiveChatSessionId}
                  onNewSession={createChatSession}
                  onUpdateSession={updateChatSession}
                  onDeleteSession={deleteChatSession}
                />
              )}
            </div>
          </div>
        </ReactFlowProvider>
      </div>

      {/* Bottom Log Panel */}
      <LogPanel
        logs={logs}
        traceEvents={traceEvents}
        toolEvents={toolEvents}
        onClear={() => {
          setLogs([]);
          setTraceEvents([]);
          setToolEvents([]);
        }}
      />
      <input
        ref={fileInputRef}
        type="file"
        accept="application/json"
        className="hidden"
        onChange={onFileSelected}
      />
    </div>
  );
}

export default function App() {
  return <Flow />;
}
