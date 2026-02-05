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
import { ControlFlowNode, ActionNode, DebugNode } from './components/CustomNodes';
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

interface StateField {
  name: string;
  type: string;
  default: any;
}

const initialNodes: Node[] = [];
const initialEdges: Edge[] = [];

// Define once outside component to avoid re-creation
const nodeTypes: NodeTypes = {
  controlFlow: ControlFlowNode,
  action: ActionNode,
  debug: DebugNode,
};
const edgeTypes = {};

// Helper to determine node visual type from nodeType
const getNodeVisualType = (nodeType: string): string => {
  const controlFlowTypes = ['Sequence', 'Selector', 'Parallel'];
  const debugTypes = ['Log'];

  if (controlFlowTypes.includes(nodeType)) return 'controlFlow';
  if (debugTypes.includes(nodeType)) return 'debug';
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
  const [rightPanelTab, setRightPanelTab] = useState<'properties' | 'chat'>('properties');
  const [showInitialState, setShowInitialState] = useState(false);
  const [initialStateValues, setInitialStateValues] = useState<Record<string, any>>({});
  const [initialStateError, setInitialStateError] = useState<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Derive selectedNode from nodes to keep it in sync
  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null;
    return nodes.find(n => n.id === selectedNodeId) || null;
  }, [nodes, selectedNodeId]);

  const inferredStateFields = useMemo(
    () => inferStateFields(nodes, nodeMetas),
    [nodes, nodeMetas]
  );

  useEffect(() => {
    setInitialStateValues((prev) => {
      const next = { ...prev };
      inferredStateFields.forEach((field) => {
        if (next[field.name] !== undefined) return;
        if (field.type === 'list' || field.type === 'dict' || field.type === 'tuple') {
          next[field.name] = JSON.stringify(field.default ?? (field.type === 'dict' ? {} : []), null, 2);
        } else {
          next[field.name] = field.default ?? '';
        }
      });
      return next;
    });
  }, [inferredStateFields]);


  useEffect(() => {
    fetchNodes().then(setNodeMetas).catch(err => console.error("Failed to fetch nodes", err));
    fetchTools().then(setTools).catch(err => console.error("Failed to fetch tools", err));
    // Auto-create a session workflow for now
    createWorkflow("Untitled Session").then(wf => {
      setWorkflowId(wf.id);
      console.log("Created session:", wf.id);
    });
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
          }
        }
        else if (msg.type === 'log') {
          const timestamp = new Date().toLocaleTimeString();
          setLogs(prev => [...prev, { timestamp, type: 'log', message: msg.message }]);
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
          if (msg.event !== 'llm_token') {
            setLogs(prev => [...prev, { timestamp, type: 'trace', message: `trace:${msg.event}${details}` }]);
          }
        }
      } catch (e) {
        console.error("WS Parse error", e);
      }
    };

    ws.onerror = (error) => console.error("WS Error:", error);
    ws.onclose = () => console.log("WS Disconnected");

    return () => ws.close();
  }, [workflowId, setNodes]);

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
    for (const field of inferredStateFields) {
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
          } catch {
            state[field.name] = [{ role: 'user', content: raw }];
          }
          continue;
        }
        if (typeof raw === 'string') {
          try {
            const parsed = JSON.parse(raw);
            state[field.name] = parsed;
          } catch {
            return { error: `Field '${field.name}' expects JSON` };
          }
        } else {
          state[field.name] = raw;
        }
        continue;
      }
      if (raw === '' || raw === null || raw === undefined) continue;
      state[field.name] = raw;
    }
    return { state };
  }, [initialStateValues, inferredStateFields]);

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

  return (
    <div className="flex flex-col h-screen w-screen bg-gray-50">
      {/* Top Area: Sidebar + Canvas + NodePanel */}
      <div className="flex flex-1 overflow-hidden">
        <ReactFlowProvider>
          {/* Sidebar */}
          <LeftPanel nodeMetas={nodeMetas} tools={tools} onApplyWorkflow={applyWorkflow} />

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
                  <div className="absolute right-0 top-full mt-2 w-72 bg-white border border-gray-200 rounded shadow-lg p-3 text-xs z-10">
                    <div className="font-semibold text-gray-700 mb-2">Initial State</div>
                    <div className="max-h-64 overflow-auto pr-1">
                      {inferredStateFields.map((field) => (
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
