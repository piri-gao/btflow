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
import Sidebar from './components/Sidebar';
import NodePanel from './components/NodePanel';
import LogPanel from './components/LogPanel';
import { fetchNodes, saveWorkflow, runWorkflow, stopWorkflow, createWorkflow } from './api/client';

interface LogEntry {
  timestamp: string;
  type: 'log' | 'status' | 'error';
  message: string;
}

const initialNodes: Node[] = [];
const initialEdges: Edge[] = [];

const nodeTypes: NodeTypes = {};

function Flow() {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [nodeMetas, setNodeMetas] = useState<any[]>([]);

  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);

  // Derive selectedNode from nodes to keep it in sync
  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null;
    return nodes.find(n => n.id === selectedNodeId) || null;
  }, [nodes, selectedNodeId]);


  useEffect(() => {
    fetchNodes().then(setNodeMetas).catch(err => console.error("Failed to fetch nodes", err));
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
              const status = msg.data[n.id];
              let color = '#fff'; // default
              if (status === 'RUNNING') color = '#fbbf24'; // yellow-400
              if (status === 'SUCCESS') color = '#86efac'; // green-300
              if (status === 'FAILURE') color = '#fca5a5'; // red-300

              return {
                ...n,
                style: { ...n.style, backgroundColor: color, transition: 'background-color 0.2s' }
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
        type: 'default',
        position,
        data: {
          label: label,
          nodeType: type,
          config: {} // Init config
        },
      };

      setNodes((nds) => nds.concat(newNode));
    },
    [reactFlowInstance, setNodes]
  );

  const onSave = useCallback(async () => {
    if (!reactFlowInstance || !workflowId) return;

    try {
      await saveWorkflow(workflowId, { nodes, edges });
    } catch (error: any) {
      // If workflow not found (404), create a new one
      if (error?.response?.status === 404) {
        console.log("Workflow not found, creating new one...");
        const newWf = await createWorkflow("Recovered Workflow");
        setWorkflowId(newWf.id);
        await saveWorkflow(newWf.id, { nodes, edges });
      } else {
        console.error("Save failed:", error);
      }
    }
  }, [reactFlowInstance, nodes, edges, workflowId]);

  const onRun = useCallback(async () => {
    if (!workflowId) return;
    await onSave();
    await runWorkflow(workflowId);
  }, [workflowId, onSave]);

  const onStop = useCallback(async () => {
    if (!workflowId) return;
    await stopWorkflow(workflowId);
  }, [workflowId]);

  return (
    <div className="flex flex-col h-screen w-screen bg-gray-50">
      {/* Top Area: Sidebar + Canvas + NodePanel */}
      <div className="flex flex-1 overflow-hidden">
        <ReactFlowProvider>
          {/* Sidebar */}
          <Sidebar nodeMetas={nodeMetas} />

          {/* Main Canvas */}
          <div className="flex-1 h-full relative" ref={reactFlowWrapper}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
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
              <Panel position="top-right" className="bg-white p-2 rounded shadow-md flex gap-2 border border-gray-200">
                <button onClick={onSave} disabled={isRunning} className={`px-3 py-1 rounded text-sm font-medium border border-gray-300 ${isRunning ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : 'bg-white hover:bg-gray-50'}`}>
                  💾 Save
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
              </Panel>
            </ReactFlow>
          </div>

          {/* Right Panel */}
          <NodePanel
            selectedNode={selectedNode}
            setNodes={setNodes}
            nodeMetas={nodeMetas}
          />
        </ReactFlowProvider>
      </div>

      {/* Bottom Log Panel */}
      <LogPanel
        logs={logs}
        onClear={() => setLogs([])}
      />
    </div>
  );
}

export default function App() {
  return <Flow />;
}
