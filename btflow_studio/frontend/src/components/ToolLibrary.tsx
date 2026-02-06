import { useMemo, useState } from 'react';

interface ToolMeta {
  id: string;
  name: string;
  label: string;
  description: string;
  available: boolean;
  error?: string | null;
}

interface ToolLibraryProps {
  tools: ToolMeta[];
  language?: string;
}

const TOOL_LABEL_ZH: Record<string, string> = {
  CalculatorTool: '计算器',
  PythonREPLTool: 'Python REPL',
  FileReadTool: '读取文件',
  FileWriteTool: '写入文件',
  HTTPTool: 'HTTP 请求',
  DuckDuckGoSearchTool: 'DuckDuckGo 搜索',
  MemorySearchTool: '记忆检索',
  MemoryAddTool: '记忆写入',
};

const TOOL_DESC_ZH: Record<string, string> = {
  CalculatorTool: '计算数学表达式。',
  PythonREPLTool: '执行 Python 代码。',
  FileReadTool: '读取本地文件内容。',
  FileWriteTool: '写入或创建本地文件。',
  HTTPTool: '发起 HTTP 请求。',
  DuckDuckGoSearchTool: '使用 DuckDuckGo 搜索网页。',
  MemorySearchTool: '在记忆库中检索相关信息。',
  MemoryAddTool: '把信息写入记忆库。',
};

const translateTool = (tool: ToolMeta, language?: string): ToolMeta => {
  if (language !== 'zh') return tool;
  const id = tool.id;
  return {
    ...tool,
    label: TOOL_LABEL_ZH[id] || tool.label,
    description: TOOL_DESC_ZH[id] || tool.description,
  };
};

export default function ToolLibrary({ tools, language }: ToolLibraryProps) {
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const translated = tools.map(t => translateTool(t, language));
    if (!query.trim()) return translated;
    const q = query.toLowerCase();
    return translated.filter(t =>
      t.id.toLowerCase().includes(q) ||
      t.name.toLowerCase().includes(q) ||
      t.label.toLowerCase().includes(q) ||
      (t.description || '').toLowerCase().includes(q)
    );
  }, [tools, query, language]);

  return (
    <div className="p-4 h-full overflow-y-auto">
      <div className="flex items-center gap-2 mb-3">
        <input
          className="flex-1 text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
          placeholder="Search tools..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <div className="space-y-2">
        {filtered.map(tool => (
          <div
            key={tool.id}
            className={`border rounded p-3 text-sm ${tool.available ? 'border-gray-200 bg-white' : 'border-yellow-300 bg-yellow-50'}`}
          >
            <div className="flex items-center justify-between">
              <div className="font-medium text-gray-900">{tool.label}</div>
              {!tool.available && (
                <span className="text-xs text-yellow-700">missing deps</span>
              )}
            </div>
            <div className="text-xs text-gray-500 mt-1">{tool.name}</div>
            {tool.description && (
              <div className="text-xs text-gray-600 mt-2">{tool.description}</div>
            )}
            {!tool.available && tool.error && (
              <div className="text-xs text-yellow-800 mt-2">⚠ {tool.error}</div>
            )}
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="text-sm text-gray-400 italic">No tools found.</div>
        )}
      </div>
    </div>
  );
}
