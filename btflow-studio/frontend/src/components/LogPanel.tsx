
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
        <div className="h-48 bg-white border-t border-gray-300 flex flex-col shadow-sm">
            <div className="flex items-center justify-between px-3 py-2 bg-gray-50 border-b border-gray-200">
                <span className="text-sm font-medium text-gray-700">📋 Execution Logs</span>
                <button
                    onClick={onClear}
                    className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100 transition-colors"
                >
                    Clear
                </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3 font-mono text-xs bg-gray-50">
                {logs.length === 0 ? (
                    <div className="text-gray-400 italic">No logs yet. Run a workflow to see output.</div>
                ) : (
                    logs.map((log, idx) => (
                        <div
                            key={idx}
                            className={`py-1 ${log.type === 'error' ? 'text-red-600' :
                                log.type === 'status' ? 'text-blue-600' :
                                    'text-green-700'
                                }`}
                        >
                            <span className="text-gray-400">[{log.timestamp}]</span>{' '}
                            {log.type === 'status' ? `⚡ ${log.message}` : log.message}
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}
