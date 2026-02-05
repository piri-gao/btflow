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
    'Action': {
        bg: 'bg-blue-50',
        border: 'border-blue-300',
        hover: 'hover:bg-blue-100 hover:border-blue-400'
    },
    'Debug': {
        bg: 'bg-green-50',
        border: 'border-green-300',
        hover: 'hover:bg-green-100 hover:border-green-400'
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

export default function Sidebar({ nodeMetas }: SidebarProps) {
    const [query, setQuery] = useState('');
    const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

    const filteredNodes = useMemo(() => {
        if (!query.trim()) return nodeMetas;
        const q = query.toLowerCase();
        return nodeMetas.filter((n) =>
            n.id.toLowerCase().includes(q) ||
            n.label.toLowerCase().includes(q) ||
            (n.description || '').toLowerCase().includes(q)
        );
    }, [nodeMetas, query]);

    // Group nodes by category
    const groupedNodes = filteredNodes.reduce((acc, node) => {
        const category = node.category || 'Other';
        if (!acc[category]) acc[category] = [];
        acc[category].push(node);
        return acc;
    }, {} as Record<string, NodeMeta[]>);

    // Category order
    const categoryOrder = ['Control Flow', 'Action', 'Tools', 'Debug', 'Agent', 'Other'];

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
                            <span>{category}</span>
                            <span className="text-xs">{collapsed[category] ? '▸' : '▾'}</span>
                        </button>
                        {!collapsed[category] && (
                            <div className="grid grid-cols-2 gap-2">
                                {groupedNodes[category].map((node) => {
                                    const style = categoryStyles[category] || categoryStyles['Action'];
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
