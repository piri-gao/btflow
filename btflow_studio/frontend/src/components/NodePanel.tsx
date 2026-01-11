import React from 'react';
import type { Node } from 'reactflow';

interface NodeMeta {
    id: string;
    label: string;
    description: string;
    config_schema: Record<string, any>;
}

interface NodePanelProps {
    selectedNode: Node | null;
    setNodes: React.Dispatch<React.SetStateAction<Node[]>>;
    nodeMetas: NodeMeta[];
}

export default function NodePanel({ selectedNode, setNodes, nodeMetas }: NodePanelProps) {
    if (!selectedNode) {
        return (
            <div className="w-72 bg-white border-l border-gray-200 p-4 shadow-sm z-10 hidden lg:block h-full overflow-y-auto">
                <h2 className="font-semibold mb-2">Properties</h2>
                <div className="text-sm text-gray-500">Select a node to edit its properties.</div>
            </div>
        );
    }

    const nodeType = selectedNode.data.nodeType;
    const meta = nodeMetas.find(m => m.id === nodeType);
    const config = selectedNode.data.config || {};

    const handleLabelChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const label = e.target.value;
        setNodes((nds) =>
            nds.map((n) => {
                if (n.id === selectedNode.id) {
                    return { ...n, data: { ...n.data, label } };
                }
                return n;
            })
        );
    };

    const handleConfigChange = (key: string, value: any) => {
        setNodes((nds) =>
            nds.map((n) => {
                if (n.id === selectedNode.id) {
                    const newConfig = { ...(n.data.config || {}), [key]: value };
                    return { ...n, data: { ...n.data, config: newConfig } };
                }
                return n;
            })
        );
    };

    return (
        <div className="w-72 bg-white border-l border-gray-200 p-4 shadow-sm z-10 hidden lg:block h-full overflow-y-auto">
            <h2 className="font-semibold mb-4 text-center border-b pb-2">
                {meta?.label || selectedNode.data.label}
            </h2>

            <div className="space-y-4">
                {/* Basic Info */}
                <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Node ID</label>
                    <input
                        className="w-full text-xs p-2 border rounded bg-gray-100 text-gray-500"
                        value={selectedNode.id}
                        readOnly
                    />
                </div>

                <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Label</label>
                    <input
                        className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                        value={selectedNode.data.label}
                        onChange={handleLabelChange}
                    />
                </div>

                {/* Dynamic Configuration */}
                {meta && meta.config_schema && (
                    <div className="pt-4 border-t">
                        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Configuration</h3>
                        {Object.entries(meta.config_schema).map(([key, schema]: [string, any]) => (
                            <div key={key} className="mb-3">
                                <label className="block text-xs font-medium text-gray-700 mb-1">
                                    {key} {schema.type === 'select' ? '(Select)' : ''}
                                </label>

                                {schema.type === 'select' ? (
                                    <select
                                        className="w-full text-sm p-2 border rounded bg-white"
                                        value={config[key] || schema.default || ''}
                                        onChange={(e) => handleConfigChange(key, e.target.value)}
                                    >
                                        <option value="">Select...</option>
                                        {schema.options?.map((opt: string) => (
                                            <option key={opt} value={opt}>{opt}</option>
                                        ))}
                                    </select>
                                ) : schema.type === 'boolean' ? (
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            checked={config[key] || false}
                                            onChange={(e) => handleConfigChange(key, e.target.checked)}
                                        />
                                        <span className="text-sm text-gray-600">{key}</span>
                                    </div>
                                ) : (
                                    <input
                                        className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                                        value={config[key] || ''}
                                        placeholder={schema.default}
                                        onChange={(e) => handleConfigChange(key, e.target.value)}
                                    />
                                )}
                                <div className="text-[10px] text-gray-400 mt-1 flex justify-between">
                                    <span>Type: {schema.type}</span>
                                    <button className="text-blue-500 hover:text-blue-700">🔗 Bind</button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {(!meta) && (
                    <div className="text-xs text-gray-400 italic">
                        No configuration schema found for type '{nodeType}'.
                    </div>
                )}
            </div>
        </div>
    );
}
