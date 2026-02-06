import { Handle, Position, type NodeProps } from 'reactflow';

// Control Flow Node - Ellipse shape, gradient background, prominent
export function ControlFlowNode({ data, selected }: NodeProps) {
    const getColors = () => {
        switch (data.status) {
            case 'RUNNING':
                return {
                    outer: 'border-yellow-600',
                    bg: 'bg-gradient-to-br from-yellow-50 to-yellow-100',
                    inner: 'shadow-inner shadow-yellow-200'
                };
            case 'SUCCESS':
                return {
                    outer: 'border-green-600',
                    bg: 'bg-gradient-to-br from-green-50 to-green-100',
                    inner: 'shadow-inner shadow-green-200'
                };
            case 'FAILURE':
                return {
                    outer: 'border-red-600',
                    bg: 'bg-gradient-to-br from-red-50 to-red-100',
                    inner: 'shadow-inner shadow-red-200'
                };
            default:
                return {
                    outer: 'border-purple-500',
                    bg: 'bg-gradient-to-br from-purple-50 via-purple-100 to-purple-50',
                    inner: 'shadow-inner shadow-purple-200'
                };
        }
    };

    const colors = getColors();

    return (
        <div className="relative">
            <Handle type="target" position={Position.Top} className="w-3 h-3 z-10" />

            {/* Outer ellipse border */}
            <div className={`
                p-1 rounded-full border-[3px]
                ${colors.outer}
                ${selected ? 'ring-4 ring-blue-400' : ''}
                shadow-lg
                w-40 h-28
            `}>
                {/* Inner ellipse container */}
                <div className={`
                    px-4 py-3 rounded-full
                    ${colors.bg}
                    ${colors.inner}
                    w-full h-full
                    flex items-center justify-center
                    transition-all
                `}>
                    <div className="text-center">
                        <div className="text-2xl mb-1">{data.icon || '⚙️'}</div>
                        <div className="text-xs font-bold text-gray-800 uppercase tracking-wide leading-tight">
                            {data.label}
                        </div>
                        <div className="text-[10px] text-purple-600 font-bold mt-1 px-1.5 py-0.5 bg-purple-200/50 rounded-full inline-block">
                            {data.nodeType}
                        </div>
                    </div>
                </div>
            </div>

            <Handle type="source" position={Position.Bottom} className="w-3 h-3 z-10" />
        </div>
    );
}

// Action Node - Simple, clean design
export function ActionNode({ data, selected }: NodeProps) {
    const getColors = () => {
        switch (data.status) {
            case 'RUNNING': return 'bg-yellow-100 border-yellow-500';
            case 'SUCCESS': return 'bg-green-100 border-green-500';
            case 'FAILURE': return 'bg-red-100 border-red-500';
            default: return 'bg-blue-50 border-blue-400';
        }
    };

    return (
        <div className={`
            px-4 py-3 rounded-lg border-2
            ${getColors()}
            ${selected ? 'ring-2 ring-blue-400' : ''}
            transition-all min-w-[120px] shadow-md
        `}>
            <Handle type="target" position={Position.Top} className="w-3 h-3" />

            <div className="text-center">
                <div className="text-xl mb-1">{data.icon || '▶️'}</div>
                <div className="text-sm font-semibold text-gray-800">{data.label}</div>
                <div className="text-xs text-gray-500 mt-0.5">{data.nodeType}</div>
            </div>

            <Handle type="source" position={Position.Bottom} className="w-3 h-3" />
        </div>
    );
}
