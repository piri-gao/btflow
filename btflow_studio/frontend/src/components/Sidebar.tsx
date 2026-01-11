import React from 'react';

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
};

export default function Sidebar({ nodeMetas }: SidebarProps) {
    // Group nodes by category
    const groupedNodes = nodeMetas.reduce((acc, node) => {
        const category = node.category || 'Other';
        if (!acc[category]) acc[category] = [];
        acc[category].push(node);
        return acc;
    }, {} as Record<string, NodeMeta[]>);

    // Category order
    const categoryOrder = ['Control Flow', 'Action', 'Debug', 'Other'];
    const sortedCategories = categoryOrder.filter(cat => groupedNodes[cat]);

    return (
        <div className="w-64 bg-white border-r border-gray-200 p-4 shadow-sm z-10 flex flex-col h-full overflow-y-auto">
            <h1 className="text-xl font-bold mb-6 text-blue-600">BTflow Studio</h1>

            <div className="space-y-6">
                {sortedCategories.map((category) => (
                    <div key={category}>
                        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                            {category}
                        </h3>
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
                    </div>
                ))}
            </div>
        </div>
    );
}
