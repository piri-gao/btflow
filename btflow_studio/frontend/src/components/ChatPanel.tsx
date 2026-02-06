import { useState, useRef, useEffect } from 'react';
import axios from 'axios';

interface Message {
    role: 'user' | 'model';
    content: string;
}

interface GeneratedWorkflow {
    nodes: any[];
    edges: any[];
}

interface ChatSession {
    id: string;
    title: string;
    messages: Message[];
    generatedWorkflow?: GeneratedWorkflow | null;
}

interface ChatPanelProps {
    currentWorkflow: { nodes: any[], edges: any[] } | null;
    onApplyWorkflow: (workflow: GeneratedWorkflow) => void;
    availableNodes: any[];
    availableTools: any[];
    sessions: ChatSession[];
    activeSessionId: string;
    onSelectSession: (id: string) => void;
    onNewSession: () => void;
    onUpdateSession: (id: string, updater: (session: ChatSession) => ChatSession) => void;
    onDeleteSession: (id: string) => void;
}

const titleFromMessage = (message: string) => {
    const trimmed = message.trim();
    if (!trimmed) return 'New Session';
    return trimmed.length > 24 ? `${trimmed.slice(0, 24)}...` : trimmed;
};

const normalizeTitle = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return '';
    return trimmed.length > 24 ? `${trimmed.slice(0, 24)}...` : trimmed;
};

export default function ChatPanel({
    currentWorkflow,
    onApplyWorkflow,
    availableNodes,
    availableTools,
    sessions,
    activeSessionId,
    onSelectSession,
    onNewSession,
    onUpdateSession,
    onDeleteSession
}: ChatPanelProps) {
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [showSessions, setShowSessions] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const activeSession = sessions.find(s => s.id === activeSessionId) || sessions[0];
    const messages = activeSession?.messages || [];
    const generatedWorkflow = activeSession?.generatedWorkflow || null;

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(scrollToBottom, [messages]);

    const sendMessage = async () => {
        if (!activeSession || !input.trim() || loading) return;

        const userMessage = input.trim();
        setInput('');
        setLoading(true);

        // Add user message to chat
        const newMessages: Message[] = [...messages, { role: 'user', content: userMessage }];
        onUpdateSession(activeSession.id, (session) => ({
            ...session,
            title: session.messages.length === 0 ? titleFromMessage(userMessage) : session.title,
            messages: newMessages
        }));

        try {
            // Call LLM API
            const response = await axios.post('http://localhost:8000/api/chat/generate-workflow', {
                message: userMessage,
                conversation_history: messages,
                current_workflow: currentWorkflow,
                available_nodes: availableNodes,
                available_tools: availableTools
            });

            const { reply, workflow } = response.data;

            // Add assistant response
            onUpdateSession(activeSession.id, (session) => ({
                ...session,
                messages: [...newMessages, { role: 'model', content: reply }],
                generatedWorkflow: workflow || session.generatedWorkflow || null
            }));

        } catch (error: any) {
            console.error('Chat error:', error);
            onUpdateSession(activeSession.id, (session) => ({
                ...session,
                messages: [...newMessages, {
                    role: 'model',
                    content: `❌ Error: ${error.response?.data?.detail || error.message}`
                }]
            }));
        } finally {
            setLoading(false);
        }
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    const handleApply = () => {
        if (!activeSession || !generatedWorkflow) return;
        onApplyWorkflow(generatedWorkflow);
        onUpdateSession(activeSession.id, (session) => ({
            ...session,
            generatedWorkflow: null
        }));
    };

    return (
        <div className="flex flex-col h-full bg-white">
            {/* Header */}
            <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
                <h3 className="font-semibold text-gray-700 flex items-center gap-2">
                    <span>🤖</span>
                    <span>Workflow Assistant</span>
                </h3>
                <p className="text-xs text-gray-500 mt-1">
                    Describe your workflow and I'll generate it for you
                </p>
            </div>

            {/* Sessions */}
            <div className="px-4 py-2 border-b border-gray-200 bg-white">
                <div className="flex items-center justify-between">
                    <button
                        onClick={() => setShowSessions((prev) => !prev)}
                        className="text-xs text-gray-600 hover:text-gray-800 flex items-center gap-1"
                    >
                        <span>{showSessions ? '▾' : '▸'}</span>
                        <span>Sessions</span>
                    </button>
                    <button
                        onClick={onNewSession}
                        className="text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700"
                    >
                        New
                    </button>
                </div>
                {showSessions && (
                    <div className="mt-2 max-h-24 overflow-y-auto space-y-1">
                        {sessions.map((s) => (
                            <div
                                key={s.id}
                                className={`flex items-center justify-between text-left text-xs px-2 py-1 rounded border ${s.id === activeSessionId
                                    ? 'border-blue-500 bg-blue-50 text-blue-700'
                                    : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                                    }`}
                            >
                                <button
                                    onClick={() => onSelectSession(s.id)}
                                    className="flex-1 text-left"
                                >
                                    {s.title || s.id}
                                </button>
                                <div className="ml-2 flex items-center gap-1">
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            const nextTitle = normalizeTitle(prompt('Rename session', s.title || '') || '');
                                            if (nextTitle) {
                                                onUpdateSession(s.id, (session) => ({
                                                    ...session,
                                                    title: nextTitle
                                                }));
                                            }
                                        }}
                                        className="text-[10px] px-1 rounded text-gray-500 hover:text-blue-600"
                                        title="Rename session"
                                    >
                                        ✎
                                    </button>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            if (sessions.length > 1) onDeleteSession(s.id);
                                        }}
                                        className={`text-[10px] px-1 rounded ${sessions.length > 1 ? 'text-gray-500 hover:text-red-600' : 'text-gray-300 cursor-not-allowed'}`}
                                        title={sessions.length > 1 ? 'Delete session' : 'At least one session required'}
                                    >
                                        ✕
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-50">
                {messages.length === 0 && (
                    <div className="text-center text-gray-400 mt-8">
                        <div className="text-4xl mb-2">💬</div>
                        <div className="text-sm">Start a conversation...</div>
                        <div className="text-xs mt-2">
                            Try: "Create a workflow that waits 3 seconds, then prints Hello"
                        </div>
                    </div>
                )}

                {messages.map((msg, idx) => (
                    <div
                        key={idx}
                        className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                        <div
                            className={`max-w-[80%] rounded-lg px-4 py-2 ${msg.role === 'user'
                                ? 'bg-blue-500 text-white'
                                : 'bg-white border border-gray-200 text-gray-800'
                                }`}
                        >
                            <div className="text-sm whitespace-pre-wrap">{msg.content}</div>
                        </div>
                    </div>
                ))}

                {loading && (
                    <div className="flex justify-start">
                        <div className="bg-white border border-gray-200 rounded-lg px-4 py-2">
                            <div className="flex items-center gap-2 text-gray-500 text-sm">
                                <div className="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full"></div>
                                <span>Generating...</span>
                            </div>
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Apply Button */}
            {generatedWorkflow && (
                <div className="px-4 py-2 bg-green-50 border-t border-green-200">
                    <button
                        onClick={handleApply}
                        className="w-full bg-green-600 hover:bg-green-700 text-white py-2 rounded-lg font-medium text-sm transition-colors flex items-center justify-center gap-2"
                    >
                        <span>✨</span>
                        <span>Apply Workflow to Canvas</span>
                    </button>
                </div>
            )}

            {/* Input */}
            <div className="p-4 border-t border-gray-200 bg-white">
                <div className="flex gap-2">
                    <textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyPress}
                        placeholder="Describe your workflow..."
                        className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                        rows={2}
                        disabled={loading}
                    />
                    <button
                        onClick={sendMessage}
                        disabled={!input.trim() || loading}
                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white rounded-lg font-medium text-sm transition-colors"
                    >
                        Send
                    </button>
                </div>
                <div className="text-xs text-gray-400 mt-2">
                    Press Enter for new line, Shift+Enter to send
                </div>
            </div>
        </div>
    );
}
