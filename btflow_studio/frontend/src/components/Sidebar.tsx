import React, { useMemo, useState } from 'react';

interface NodeMeta {
    id: string;
    label: string;
    category: string;
    icon: string;
    description: string;
}

interface SidebarProps {
    nodeMetas: NodeMeta[];
    language?: string;
}

const onDragStart = (event: React.DragEvent, nodeType: string, label: string) => {
    event.dataTransfer.setData('application/reactflow/type', nodeType);
    event.dataTransfer.setData('application/reactflow/label', label);
    event.dataTransfer.effectAllowed = 'move';
};

// Category styling
const categoryStyles: Record<string, { bg: string, border: string, hover: string }> = {
    'Control Flow': {
        bg: 'bg-purple-50',
        border: 'border-purple-300',
        hover: 'hover:bg-purple-100 hover:border-purple-400'
    },
    'Utilities': {
        bg: 'bg-blue-50',
        border: 'border-blue-300',
        hover: 'hover:bg-blue-100 hover:border-blue-400'
    },
    'Tools': {
        bg: 'bg-yellow-50',
        border: 'border-yellow-300',
        hover: 'hover:bg-yellow-100 hover:border-yellow-400'
    },
    'Agent': {
        bg: 'bg-orange-50',
        border: 'border-orange-300',
        hover: 'hover:bg-orange-100 hover:border-orange-400'
    },
};

const CATEGORY_LABEL_ZH: Record<string, string> = {
    'Control Flow': '控制流',
    'Utilities': '实用',
    'Tools': '工具',
    'Agent': '智能体',
    'Other': '其他',
};

const NODE_LABEL_ZH: Record<string, string> = {
    Sequence: '顺序',
    Selector: '选择',
    Parallel: '并行',
    LoopUntilSuccess: '循环直到成功',
    Log: '日志',
    Wait: '等待',
    AgentLLMNode: '智能体 LLM',
    ToolExecutor: '工具执行器',
    ParserNode: '解析器',
    ConditionNode: '条件判断',
    ToolNode: '工具节点',
};

const NODE_DESC_ZH: Record<string, string> = {
    Sequence: '按顺序执行子节点，任意失败则停止。',
    Selector: '按优先级选择，直到有一个成功。',
    Parallel: '并行执行多个子节点。',
    LoopUntilSuccess: '循环执行直到成功或达到最大次数。',
    Log: '输出一条日志。',
    Wait: '等待指定时长。',
    AgentLLMNode: '调用 LLM 生成下一步内容。',
    ToolExecutor: '解析并执行工具调用。',
    ParserNode: '从消息中解析结构化信息。',
    ConditionNode: '根据条件判断是否继续。',
    ToolNode: '确定性执行一个工具。',
};

const translateNodeMeta = (node: NodeMeta, language?: string): NodeMeta => {
    if (language !== 'zh') return node;
    const id = node.id;
    return {
        ...node,
        label: NODE_LABEL_ZH[id] || node.label,
        description: NODE_DESC_ZH[id] || node.description,
    };
};

const translateCategory = (category: string, language?: string) => {
    if (language !== 'zh') return category;
    return CATEGORY_LABEL_ZH[category] || category;
};

export default function Sidebar({ nodeMetas, language }: SidebarProps) {
    const [query, setQuery] = useState('');
    const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

    const filteredNodes = useMemo(() => {
        const translated = nodeMetas.map(n => translateNodeMeta(n, language));
        if (!query.trim()) return translated;
        const q = query.toLowerCase();
        return translated.filter((n) =>
            n.id.toLowerCase().includes(q) ||
            n.label.toLowerCase().includes(q) ||
            (n.description || '').toLowerCase().includes(q)
        );
    }, [nodeMetas, query, language]);

    // Group nodes by category
    const groupedNodes = filteredNodes.reduce((acc, node) => {
        const category = node.category || 'Other';
        if (!acc[category]) acc[category] = [];
        acc[category].push(node);
        return acc;
    }, {} as Record<string, NodeMeta[]>);

    // Category order
    const categoryOrder = ['Control Flow', 'Utilities', 'Tools', 'Agent', 'Other'];

    // Sort all categories: predefined first, then others alphabetically
    const allCategories = Object.keys(groupedNodes);
    const sortedCategories = [
        ...categoryOrder.filter(cat => groupedNodes[cat]),
        ...allCategories.filter(cat => !categoryOrder.includes(cat)).sort()
    ];

    return (
        <div className="w-64 bg-white p-4 z-10 flex flex-col h-full overflow-y-auto border-r border-gray-200">
            <div className="mb-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Nodes</div>

            <div className="mb-4">
                <input
                    className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                    placeholder="Search nodes..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                />
            </div>

            <div className="space-y-6">
                {sortedCategories.map((category) => (
                    <div key={category}>
                        <button
                            className="w-full flex items-center justify-between text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3"
                            onClick={() => setCollapsed(prev => ({ ...prev, [category]: !prev[category] }))}
                        >
                            <span>{translateCategory(category, language)}</span>
                            <span className="text-xs">{collapsed[category] ? '▸' : '▾'}</span>
                        </button>
                        {!collapsed[category] && (
                            <div className="grid grid-cols-2 gap-2">
                                {groupedNodes[category].map((node) => {
                                    const style = categoryStyles[category] || categoryStyles['Utilities'];
                                    return (
                                        <div
                                            key={node.id}
                                            className={`p-2 ${style.bg} border ${style.border} rounded cursor-grab ${style.hover} transition-colors flex flex-col items-center text-center`}
                                            draggable
                                            onDragStart={(event) => onDragStart(event, node.id, node.label)}
                                            title={node.description}
                                        >
                                            <span className="text-2xl mb-1">{node.icon}</span>
                                            <div className="text-xs font-medium text-gray-900">{node.label}</div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
