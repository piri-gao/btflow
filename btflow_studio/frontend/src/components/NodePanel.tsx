import React, { useEffect, useState } from 'react';
import type { Node } from 'reactflow';

interface NodeMeta {
    id: string;
    label: string;
    description: string;
    config_schema: Record<string, any>;
    inputs?: Array<{ name: string; type?: string; default?: any } | string>;
    outputs?: Array<{ name: string; type?: string; default?: any } | string>;
}

interface ToolMeta {
    id: string;
    name: string;
    label: string;
    description: string;
    available: boolean;
    error?: string | null;
}

interface NodePanelProps {
    selectedNode: Node | null;
    setNodes: React.Dispatch<React.SetStateAction<Node[]>>;
    nodeMetas: NodeMeta[];
    tools: ToolMeta[];
}

export default function NodePanel({ selectedNode, setNodes, nodeMetas, tools }: NodePanelProps) {
    const [drafts, setDrafts] = useState<Record<string, string>>({});
    const [errors, setErrors] = useState<Record<string, string>>({});

    useEffect(() => {
        setDrafts({});
        setErrors({});
    }, [selectedNode?.id]);

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
    const labelMapFor = (schema: any, value: string) => {
        if (!schema || !schema.labelMap) return value;
        return schema.labelMap[value] || value;
    };

    const shouldShowField = (schema: any) => {
        const showWhen = schema?.showWhen;
        if (!showWhen) return true;
        return Object.entries(showWhen).every(([dep, expected]) => {
            const depSchema = meta?.config_schema?.[dep];
            const actual = config[dep] ?? depSchema?.default;
            if (Array.isArray(expected)) {
                return expected.includes(actual);
            }
            return actual === expected;
        });
    };

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

    const normalizePorts = (ports: any[] | undefined) => {
        if (!ports) return [];
        return ports.map((p) => {
            if (typeof p === 'string') return { name: p };
            return p;
        });
    };

    const handleBindingChange = (section: 'input_bindings' | 'output_bindings', portName: string, value: string) => {
        const current = (selectedNode.data as any)[section] || {};
        const next = { ...current };
        if (!value) {
            delete next[portName];
        } else {
            next[portName] = value;
        }
        setNodes((nds) =>
            nds.map((n) => {
                if (n.id === selectedNode.id) {
                    return { ...n, data: { ...n.data, [section]: next } };
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
                        {Object.entries(meta.config_schema).map(([key, schema]: [string, any]) => {
                            if (!shouldShowField(schema)) {
                                return null;
                            }
                            const currentValue = config[key] ?? schema.default ?? (schema.type === 'multiselect' ? [] : '');
                            const toolOptions = schema.source === 'tools' ? tools : [];
                            const label = schema.label || key;
                            const placeholder = schema.placeholder ?? schema.default ?? '';
                            const type = schema.type || 'text';
                            const draftValue = drafts[key];
                            const displayValue = draftValue !== undefined
                                ? draftValue
                                : (typeof currentValue === 'string' ? currentValue : JSON.stringify(currentValue, null, 2));
                            return (
                            <div key={key} className="mb-3">
                                <label className="block text-xs font-medium text-gray-700 mb-1">
                                    {label} {type === 'select' ? '(Select)' : ''}
                                </label>

                                {type === 'select' ? (
                                    <select
                                        className="w-full text-sm p-2 border rounded bg-white"
                                        value={currentValue}
                                        onChange={(e) => handleConfigChange(key, e.target.value)}
                                    >
                                        <option value="">Select...</option>
                                        {(schema.options || (schema.source === 'tools' ? toolOptions : [])).map((opt: any) => {
                                            if (typeof opt === 'string') {
                                                return <option key={opt} value={opt}>{labelMapFor(schema, opt)}</option>;
                                            }
                                            const value = opt.id;
                                            const label = opt.label + (opt.available === false ? ' (missing deps)' : '');
                                            return (
                                                <option key={value} value={value} disabled={opt.available === false}>
                                                    {label}
                                                </option>
                                            );
                                        })}
                                    </select>
                                ) : type === 'multiselect' ? (
                                    <div className="space-y-2">
                                        {(schema.options || toolOptions).map((opt: any) => {
                                            const value = typeof opt === 'string' ? opt : opt.id;
                                            const label = typeof opt === 'string' ? labelMapFor(schema, opt) : opt.label;
                                            const disabled = typeof opt === 'string' ? false : opt.available === false;
                                            const checked = Array.isArray(currentValue) && currentValue.includes(value);
                                            return (
                                                <label key={value} className={`flex items-center gap-2 text-sm ${disabled ? 'text-gray-400' : 'text-gray-700'}`}>
                                                    <input
                                                        type="checkbox"
                                                        disabled={disabled}
                                                        checked={checked}
                                                        onChange={(e) => {
                                                            const next = Array.isArray(currentValue) ? [...currentValue] : [];
                                                            if (e.target.checked) {
                                                                if (!next.includes(value)) next.push(value);
                                                            } else {
                                                                const idx = next.indexOf(value);
                                                                if (idx >= 0) next.splice(idx, 1);
                                                            }
                                                            handleConfigChange(key, next);
                                                        }}
                                                    />
                                                    <span>{label}</span>
                                                </label>
                                            );
                                        })}
                                        {(schema.options || toolOptions).length === 0 && (
                                            <div className="text-xs text-gray-400 italic">No options available.</div>
                                        )}
                                    </div>
                                ) : type === 'boolean' ? (
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            checked={!!currentValue}
                                            onChange={(e) => handleConfigChange(key, e.target.checked)}
                                        />
                                        <span className="text-sm text-gray-600">{label}</span>
                                    </div>
                                ) : type === 'number' ? (
                                    <input
                                        type="number"
                                        step={schema.step ?? 'any'}
                                        className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                                        value={currentValue}
                                        placeholder={placeholder}
                                        onChange={(e) => {
                                            const raw = e.target.value;
                                            handleConfigChange(key, raw === '' ? '' : Number(raw));
                                        }}
                                    />
                                ) : type === 'textarea' || type === 'code' ? (
                                    <textarea
                                        className={`w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none ${type === 'code' ? 'font-mono' : ''}`}
                                        rows={schema.rows ?? 4}
                                        value={currentValue}
                                        placeholder={placeholder}
                                        onChange={(e) => handleConfigChange(key, e.target.value)}
                                    />
                                ) : type === 'list' ? (
                                    <textarea
                                        className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none font-mono"
                                        rows={schema.rows ?? 4}
                                        value={draftValue !== undefined ? draftValue : (Array.isArray(currentValue) ? currentValue.join('\n') : '')}
                                        placeholder={placeholder}
                                        onChange={(e) => {
                                            const raw = e.target.value;
                                            setDrafts((prev) => ({ ...prev, [key]: raw }));
                                            const items = raw.split('\n').map((line) => line.trim()).filter((line) => line.length > 0);
                                            handleConfigChange(key, items);
                                        }}
                                    />
                                ) : type === 'json' || type === 'dict' ? (
                                    <>
                                        <textarea
                                            className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none font-mono"
                                            rows={schema.rows ?? 6}
                                            value={displayValue}
                                            placeholder={placeholder}
                                            onChange={(e) => {
                                                const raw = e.target.value;
                                                setDrafts((prev) => ({ ...prev, [key]: raw }));
                                                if (!raw.trim()) {
                                                    setErrors((prev) => ({ ...prev, [key]: '' }));
                                                    handleConfigChange(key, {});
                                                    return;
                                                }
                                                try {
                                                    const parsed = JSON.parse(raw);
                                                    setErrors((prev) => ({ ...prev, [key]: '' }));
                                                    handleConfigChange(key, parsed);
                                                } catch (err) {
                                                    setErrors((prev) => ({ ...prev, [key]: 'Invalid JSON' }));
                                                }
                                            }}
                                        />
                                        {errors[key] && (
                                            <div className="text-[10px] text-red-500 mt-1">{errors[key]}</div>
                                        )}
                                    </>
                                ) : type === 'secret' ? (
                                    <input
                                        type="password"
                                        className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                                        value={currentValue}
                                        placeholder={placeholder}
                                        onChange={(e) => handleConfigChange(key, e.target.value)}
                                    />
                                ) : (
                                    <input
                                        className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                                        value={currentValue}
                                        placeholder={placeholder}
                                        onChange={(e) => handleConfigChange(key, e.target.value)}
                                    />
                                )}
                                <div className="text-[10px] text-gray-400 mt-1 flex justify-between">
                                    <span>Type: {type}</span>
                                    <button className="text-blue-500 hover:text-blue-700">🔗 Bind</button>
                                </div>
                            </div>
                        )})}
                    </div>
                )}

                {meta && (meta.inputs?.length || meta.outputs?.length) && (
                    <div className="pt-4 border-t">
                        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Bindings</h3>
                        {normalizePorts(meta.inputs).length > 0 && (
                            <div className="mb-4">
                                <div className="text-[10px] text-gray-400 uppercase mb-2">Inputs</div>
                                {normalizePorts(meta.inputs).map((port) => {
                                    const current = (selectedNode.data as any).input_bindings?.[port.name] || '';
                                    return (
                                        <div key={`in-${port.name}`} className="mb-2">
                                            <label className="block text-xs text-gray-700 mb-1">
                                                {port.name}
                                            </label>
                                            <input
                                                className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                                                value={current}
                                                placeholder={`state.${port.name}`}
                                                onChange={(e) => handleBindingChange('input_bindings', port.name, e.target.value)}
                                            />
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                        {normalizePorts(meta.outputs).length > 0 && (
                            <div>
                                <div className="text-[10px] text-gray-400 uppercase mb-2">Outputs</div>
                                {normalizePorts(meta.outputs).map((port) => {
                                    const current = (selectedNode.data as any).output_bindings?.[port.name] || '';
                                    return (
                                        <div key={`out-${port.name}`} className="mb-2">
                                            <label className="block text-xs text-gray-700 mb-1">
                                                {port.name}
                                            </label>
                                            <input
                                                className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                                                value={current}
                                                placeholder={`state.${port.name}`}
                                                onChange={(e) => handleBindingChange('output_bindings', port.name, e.target.value)}
                                            />
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                        <div className="text-[10px] text-gray-400 mt-2">
                            留空表示使用默认字段名。
                        </div>
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
