
interface LogEntry {
    timestamp: string;
    type: 'log' | 'status' | 'error';
    message: string;
}

interface LogPanelProps {
    logs: LogEntry[];
    onClear: () => void;
}

export default function LogPanel({ logs, onClear }: LogPanelProps) {
    return (
        <div className="h-48 bg-gray-900 border-t border-gray-700 flex flex-col">
            <div className="flex items-center justify-between px-3 py-1 bg-gray-800 border-b border-gray-700">
                <span className="text-xs font-medium text-gray-300">📋 Execution Logs</span>
                <button
                    onClick={onClear}
                    className="text-xs text-gray-400 hover:text-white px-2 py-0.5 rounded hover:bg-gray-700"
                >
                    Clear
                </button>
            </div>
            <div className="flex-1 overflow-y-auto p-2 font-mono text-xs">
                {logs.length === 0 ? (
                    <div className="text-gray-500 italic">No logs yet. Run a workflow to see output.</div>
                ) : (
                    logs.map((log, idx) => (
                        <div
                            key={idx}
                            className={`py-0.5 ${log.type === 'error' ? 'text-red-400' :
                                    log.type === 'status' ? 'text-blue-400' :
                                        'text-green-400'
                                }`}
                        >
                            <span className="text-gray-500">[{log.timestamp}]</span>{' '}
                            {log.type === 'status' ? `⚡ ${log.message}` : log.message}
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}
