
import { useMemo, useState } from 'react';

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

interface LogPanelProps {
    logs: LogEntry[];
    traceEvents: TraceEvent[];
    toolEvents: ToolEvent[];
    onClear: () => void;
}

const formatValue = (value: any, max = 140) => {
    if (value === undefined || value === null) return '';
    let text = typeof value === 'string' ? value : JSON.stringify(value);
    if (text.length > max) text = `${text.slice(0, max)}...`;
    return text;
};

const formatTraceDetails = (data: Record<string, any>) => {
    const fields = ['node', 'tool', 'model', 'mode', 'messages', 'ok', 'error', 'duration_ms', 'status'];
    const parts = fields
        .filter((key) => data[key] !== undefined)
        .map((key) => `${key}=${formatValue(data[key])}`);
    return parts.length ? ` ${parts.join(' ')}` : '';
};

export default function LogPanel({ logs, traceEvents, toolEvents, onClear }: LogPanelProps) {
    const [tab, setTab] = useState<'logs' | 'trace' | 'tools'>('logs');

    const filteredLogs = useMemo(() => logs.filter((log) => log.type !== 'trace'), [logs]);
    const filteredTrace = useMemo(() => traceEvents, [traceEvents]);
    const filteredTools = useMemo(() => toolEvents, [toolEvents]);

    return (
        <div className="h-48 bg-white border-t border-gray-300 flex flex-col shadow-sm">
            <div className="flex items-center justify-between px-3 py-2 bg-gray-50 border-b border-gray-200">
                <span className="text-sm font-medium text-gray-700">📋 Runtime</span>
                <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1 bg-white border border-gray-200 rounded p-0.5">
                        <button
                            onClick={() => setTab('logs')}
                            className={`text-xs px-2 py-1 rounded transition-colors ${
                                tab === 'logs'
                                    ? 'bg-gray-200 text-gray-800'
                                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                            }`}
                        >
                            Logs
                        </button>
                        <button
                            onClick={() => setTab('trace')}
                            className={`text-xs px-2 py-1 rounded transition-colors ${
                                tab === 'trace'
                                    ? 'bg-teal-100 text-teal-700'
                                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                            }`}
                        >
                            Trace
                        </button>
                        <button
                            onClick={() => setTab('tools')}
                            className={`text-xs px-2 py-1 rounded transition-colors ${
                                tab === 'tools'
                                    ? 'bg-amber-100 text-amber-700'
                                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                            }`}
                        >
                            Tools
                        </button>
                    </div>
                    <button
                        onClick={onClear}
                        className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100 transition-colors"
                    >
                        Clear
                    </button>
                </div>
            </div>
            <div className="flex-1 overflow-y-auto p-3 font-mono text-xs bg-gray-50">
                {tab === 'logs' && (
                    filteredLogs.length === 0 ? (
                        <div className="text-gray-400 italic">No logs yet. Run a workflow to see output.</div>
                    ) : (
                        filteredLogs.map((log, idx) => (
                            <div
                                key={idx}
                                className={`py-1 ${log.type === 'error' ? 'text-red-600' :
                                    log.type === 'status' ? 'text-blue-600' :
                                    log.type === 'trace' ? 'text-teal-700' :
                                        'text-green-700'
                                    }`}
                            >
                                <span className="text-gray-400">[{log.timestamp}]</span>{' '}
                                {log.type === 'status' ? `⚡ ${log.message}` : log.message}
                            </div>
                        ))
                    )
                )}
                {tab === 'trace' && (
                    filteredTrace.length === 0 ? (
                        <div className="text-gray-400 italic">No trace events yet.</div>
                    ) : (
                        filteredTrace.map((item, idx) => (
                            <div key={idx} className="py-1 text-teal-700">
                                <span className="text-gray-400">[{item.timestamp}]</span>{' '}
                                <span className="font-semibold">{item.event}</span>
                                {formatTraceDetails(item.data)}
                            </div>
                        ))
                    )
                )}
                {tab === 'tools' && (
                    filteredTools.length === 0 ? (
                        <div className="text-gray-400 italic">No tool calls yet.</div>
                    ) : (
                        filteredTools.map((item, idx) => {
                            const data = item.data || {};
                            const tool = data.tool || 'tool';
                            const node = data.node ? ` node=${data.node}` : '';
                            if (item.event === 'tool_call') {
                                const args = data.args ? ` args=${formatValue(data.args)}` : '';
                                return (
                                    <div key={idx} className="py-1 text-amber-700">
                                        <span className="text-gray-400">[{item.timestamp}]</span>{' '}
                                        <span className="font-semibold">call</span> tool={tool}{node}{args}
                                    </div>
                                );
                            }
                            const ok = data.ok !== undefined ? ` ok=${data.ok}` : '';
                            const result = data.result ? ` result=${formatValue(data.result)}` : '';
                            const error = data.error ? ` error=${formatValue(data.error)}` : '';
                            return (
                                <div key={idx} className="py-1 text-amber-700">
                                    <span className="text-gray-400">[{item.timestamp}]</span>{' '}
                                    <span className="font-semibold">result</span> tool={tool}{node}{ok}{result}{error}
                                </div>
                            );
                        })
                    )
                )}
            </div>
        </div>
    );
}
