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

export default function Sidebar({ nodeMetas }: SidebarProps) {
    return (
        <div className="w-64 bg-white border-r border-gray-200 p-4 shadow-sm z-10 flex flex-col h-full overflow-y-auto">
            <h1 className="text-xl font-bold mb-6 text-blue-600">BTflow Studio</h1>

            <div className="mb-4">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Available Nodes</h3>
                <div className="space-y-2">
                    {nodeMetas.map((node) => (
                        <div
                            key={node.id}
                            className="p-3 bg-gray-50 border border-gray-200 rounded cursor-grab hover:bg-blue-50 hover:border-blue-300 transition-colors flex items-center gap-3"
                            draggable
                            onDragStart={(event) => onDragStart(event, node.id, node.label)}
                        >
                            <span className="text-lg">{node.icon}</span>
                            <div>
                                <div className="text-sm font-medium text-gray-900">{node.label}</div>
                                <div className="text-xs text-gray-500">{node.category}</div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
