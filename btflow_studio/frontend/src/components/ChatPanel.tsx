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

interface ChatPanelProps {
    currentWorkflow: { nodes: any[], edges: any[] } | null;
    onApplyWorkflow: (workflow: GeneratedWorkflow) => void;
    availableNodes: any[];
}

export default function ChatPanel({ currentWorkflow, onApplyWorkflow, availableNodes }: ChatPanelProps) {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [generatedWorkflow, setGeneratedWorkflow] = useState<GeneratedWorkflow | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(scrollToBottom, [messages]);

    const sendMessage = async () => {
        if (!input.trim() || loading) return;

        const userMessage = input.trim();
        setInput('');
        setLoading(true);

        // Add user message to chat
        const newMessages: Message[] = [...messages, { role: 'user', content: userMessage }];
        setMessages(newMessages);

        try {
            // Call LLM API
            const response = await axios.post('http://localhost:8000/api/chat/generate-workflow', {
                message: userMessage,
                conversation_history: messages,
                current_workflow: currentWorkflow,
                available_nodes: availableNodes
            });

            const { reply, workflow } = response.data;

            // Add assistant response
            setMessages([...newMessages, { role: 'model', content: reply }]);

            // Store generated workflow
            if (workflow) {
                setGeneratedWorkflow(workflow);
            }

        } catch (error: any) {
            console.error('Chat error:', error);
            setMessages([...newMessages, {
                role: 'model',
                content: `❌ Error: ${error.response?.data?.detail || error.message}`
            }]);
        } finally {
            setLoading(false);
        }
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    const handleApply = () => {
        if (generatedWorkflow) {
            onApplyWorkflow(generatedWorkflow);
            setGeneratedWorkflow(null); // Clear after applying
        }
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
                    Press Enter to send, Shift+Enter for new line
                </div>
            </div>
        </div>
    );
}
