import { useEffect, useState } from 'react';
import Sidebar from './Sidebar';
import ToolLibrary from './ToolLibrary';
import { fetchSettings, saveSettings, ingestMemory } from '../api/client';

interface LeftPanelProps {
  nodeMetas: any[];
  tools: any[];
  onApplyWorkflow: (workflow: { nodes: any[]; edges: any[] }) => void;
  currentWorkflow: { nodes: any[]; edges: any[] };
  workflowId?: string | null;
}

type PanelKey = 'workflow' | 'nodes' | 'tools' | 'knowledge' | 'settings';

const navItems: Array<{ key: PanelKey; label: string; icon: string }> = [
  { key: 'workflow', label: 'Workflow', icon: '🗂️' },
  { key: 'nodes', label: 'Nodes', icon: '🧩' },
  { key: 'tools', label: 'Tools', icon: '🧰' },
  { key: 'knowledge', label: 'Knowledge Base', icon: '📚' },
  { key: 'settings', label: 'Settings', icon: '⚙️' },
];

const REFLEXION_PROMPT = `You are a helpful assistant that iteratively improves answers.

You will receive the user's task and may also see your previous responses in the conversation history.
Each previous response uses this exact format:

Answer: ...
Score: ...
Reflection: ...

On each turn, produce a new response in the EXACT format below. If there is a previous answer,
improve it using the reflection feedback.

Answer: [Your complete answer here]

Score: [A number from 0 to 10, be honest and critical. Use only a number, e.g. 8.5]

Reflection: [If score < 8, explain what could be improved. If score >= 8, write "The answer is satisfactory."]

If Score >= 8, append one extra line:
Final Answer: [Repeat the Answer exactly]

IMPORTANT:
- Use EXACT labels: Answer, Score, Reflection, Final Answer
- Do NOT use other labels like "评分" or "最终答案"
- Do NOT wrap the response in code blocks

Scoring guidelines:
- 0-3: Incorrect or very incomplete
- 4-5: Partially correct but major issues
- 6-7: Mostly correct but could be improved
- 8-9: Good answer with minor issues
- 10: Perfect answer

Be critical and honest in your self-evaluation. Don't give yourself a high score unless the answer is truly excellent.`;

const buildReactTemplate = () => {
  const nodes = [
    {
      id: 'react_root',
      type: 'LoopUntilSuccess',
      label: 'ReActAgent',
      position: { x: 80, y: 40 },
      config: { max_iterations: 10 },
    },
    {
      id: 'react_seq',
      type: 'Sequence',
      label: 'ReActLoop',
      position: { x: 80, y: 160 },
      config: { memory: true },
    },
    {
      id: 'react_llm',
      type: 'AgentLLMNode',
      label: 'AgentLLM',
      position: { x: 20, y: 300 },
      config: { model: 'gemini-2.5-flash', system_prompt: '', memory_id: 'default', memory_top_k: 5 },
    },
    {
      id: 'react_tools',
      type: 'ToolExecutor',
      label: 'ToolExecutor',
      position: { x: 220, y: 300 },
      config: { tools: [], memory_id: 'default' },
    },
    {
      id: 'react_check',
      type: 'ConditionNode',
      label: 'HasFinalAnswer',
      position: { x: 420, y: 300 },
      config: { preset: 'has_final_answer' },
    },
  ];
  const edges = [
    { id: 'e_react_root', source: 'react_root', target: 'react_seq' },
    { id: 'e_react_1', source: 'react_seq', target: 'react_llm' },
    { id: 'e_react_2', source: 'react_seq', target: 'react_tools' },
    { id: 'e_react_3', source: 'react_seq', target: 'react_check' },
  ];
  return { nodes, edges };
};

const buildReflexionTemplate = () => {
  const nodes = [
    {
      id: 'reflex_root',
      type: 'LoopUntilSuccess',
      label: 'ReflexionAgent',
      position: { x: 80, y: 40 },
      config: { max_iterations: 10 },
    },
    {
      id: 'reflex_seq',
      type: 'Sequence',
      label: 'ReflexionLoop',
      position: { x: 80, y: 160 },
      config: { memory: true },
    },
    {
      id: 'reflex_llm',
      type: 'AgentLLMNode',
      label: 'AgentLLM',
      position: { x: 20, y: 300 },
      config: { model: 'gemini-2.5-flash', system_prompt: REFLEXION_PROMPT, memory_id: 'default', memory_top_k: 5 },
    },
    {
      id: 'reflex_eval',
      type: 'ParserNode',
      label: 'Parser',
      position: { x: 220, y: 300 },
      config: { preset: 'score' },
    },
    {
      id: 'reflex_check',
      type: 'ConditionNode',
      label: 'IsGoodEnough',
      position: { x: 420, y: 300 },
      config: { preset: 'score_gte', threshold: 8.0 },
    },
  ];
  const edges = [
    { id: 'e_reflex_root', source: 'reflex_root', target: 'reflex_seq' },
    { id: 'e_reflex_1', source: 'reflex_seq', target: 'reflex_llm' },
    { id: 'e_reflex_2', source: 'reflex_seq', target: 'reflex_eval' },
    { id: 'e_reflex_3', source: 'reflex_seq', target: 'reflex_check' },
  ];
  return { nodes, edges };
};

const buildRagTemplate = () => {
  const nodes = [
    {
      id: 'rag_root',
      type: 'LoopUntilSuccess',
      label: 'RAGAgent',
      position: { x: 80, y: 40 },
      config: { max_iterations: 8 },
    },
    {
      id: 'rag_seq',
      type: 'Sequence',
      label: 'RAGLoop',
      position: { x: 80, y: 160 },
      config: { memory: true },
    },
    {
      id: 'rag_llm',
      type: 'AgentLLMNode',
      label: 'AgentLLM',
      position: { x: 20, y: 300 },
      config: { model: 'gemini-2.5-flash', system_prompt: '', memory_id: 'default', memory_top_k: 5 },
    },
    {
      id: 'rag_tools',
      type: 'ToolExecutor',
      label: 'MemoryTools',
      position: { x: 220, y: 300 },
      config: { tools: ['MemorySearchTool', 'MemoryAddTool'], memory_id: 'default' },
    },
    {
      id: 'rag_check',
      type: 'ConditionNode',
      label: 'HasFinalAnswer',
      position: { x: 420, y: 300 },
      config: { preset: 'has_final_answer' },
    },
  ];
  const edges = [
    { id: 'e_rag_root', source: 'rag_root', target: 'rag_seq' },
    { id: 'e_rag_1', source: 'rag_seq', target: 'rag_llm' },
    { id: 'e_rag_2', source: 'rag_seq', target: 'rag_tools' },
    { id: 'e_rag_3', source: 'rag_seq', target: 'rag_check' },
  ];
  return { nodes, edges };
};

const TEMPLATE_STORAGE_KEY = 'btflow.studio.templates';

export default function LeftPanel({ nodeMetas, tools, onApplyWorkflow, currentWorkflow, workflowId }: LeftPanelProps) {
  const [active, setActive] = useState<PanelKey>('nodes');
  const [settings, setSettings] = useState({
    language: 'zh',
    memory_enabled: true,
    api_key: '',
    base_url: '',
    model: '',
  });
  const [settingsStatus, setSettingsStatus] = useState<string>('');
  const [loadingSettings, setLoadingSettings] = useState<boolean>(false);
  const [customTemplates, setCustomTemplates] = useState<Array<{ id: string; name: string; workflow: { nodes: any[]; edges: any[] } }>>([]);
  const [ingestFiles, setIngestFiles] = useState<File[]>([]);
  const [ingestChunkSize, setIngestChunkSize] = useState<number>(500);
  const [ingestOverlap, setIngestOverlap] = useState<number>(50);
  const [ingestMemoryId, setIngestMemoryId] = useState<string>('default');
  const [ingestStatus, setIngestStatus] = useState<string>('');
  const [ingestLoading, setIngestLoading] = useState<boolean>(false);
  const [ingestResults, setIngestResults] = useState<Array<{ file: string; ok: boolean; chunks: number; error?: string }>>([]);

  useEffect(() => {
    let mounted = true;
    setLoadingSettings(true);
    fetchSettings()
      .then((data) => {
        if (!mounted) return;
        setSettings({
          language: data.language || 'zh',
          memory_enabled: data.memory_enabled ?? true,
          api_key: data.api_key || '',
          base_url: data.base_url || '',
          model: data.model || '',
        });
      })
      .catch(() => {
        if (!mounted) return;
        setSettingsStatus('⚠️ Failed to load settings');
      })
      .finally(() => {
        if (!mounted) return;
        setLoadingSettings(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    const stored = localStorage.getItem(TEMPLATE_STORAGE_KEY);
    if (!stored) return;
    try {
      const parsed = JSON.parse(stored);
      if (Array.isArray(parsed)) {
        setCustomTemplates(parsed);
      }
    } catch {
      localStorage.removeItem(TEMPLATE_STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(TEMPLATE_STORAGE_KEY, JSON.stringify(customTemplates));
  }, [customTemplates]);

  const handleSaveTemplate = () => {
    if (!currentWorkflow?.nodes?.length) {
      setSettingsStatus('⚠️ 当前画布为空，无法保存模板');
      return;
    }
    const name = prompt('Template name', 'My Template');
    if (!name) return;
    const id = `tpl-${Date.now()}`;
    setCustomTemplates((prev) => [
      { id, name: name.trim(), workflow: currentWorkflow },
      ...prev
    ]);
  };

  const handleDeleteTemplate = (id: string) => {
    setCustomTemplates((prev) => prev.filter((t) => t.id !== id));
  };

  const handleSaveSettings = async () => {
    setSettingsStatus('');
    try {
      const data = await saveSettings(settings);
      setSettings({
        language: data.language || 'zh',
        memory_enabled: data.memory_enabled ?? true,
        api_key: data.api_key || '',
        base_url: data.base_url || '',
        model: data.model || '',
      });
      setSettingsStatus('✅ Saved to .env');
    } catch (e: any) {
      setSettingsStatus(`❌ Save failed: ${e?.message || 'unknown error'}`);
    }
  };

  const handleIngest = async () => {
    if (!settings.memory_enabled) {
      setIngestStatus('⚠️ Memory is disabled');
      return;
    }
    if (!ingestFiles.length) {
      setIngestStatus('⚠️ Please choose files to ingest');
      return;
    }
    if (!currentWorkflow?.nodes?.length || !workflowId) {
      setIngestStatus('⚠️ Please create a workflow first');
      return;
    }
    try {
      setIngestLoading(true);
      setIngestStatus('');
      const data = await ingestMemory({
        workflowId: workflowId || 'workflow',
        memoryId: ingestMemoryId || 'default',
        chunkSize: ingestChunkSize,
        overlap: ingestOverlap,
        files: ingestFiles
      });
      const okCount = (data.results || []).filter((r: any) => r.ok).length;
      setIngestStatus(`✅ Ingested ${okCount}/${(data.results || []).length} files. Records: ${data.records}`);
      setIngestResults(data.results || []);
      setIngestFiles([]);
    } catch (e: any) {
      setIngestStatus(`❌ Ingest failed: ${e?.response?.data?.detail || e.message}`);
      setIngestResults([]);
    } finally {
      setIngestLoading(false);
    }
  };

  return (
    <div className="flex h-full border-r border-gray-200 bg-white">
      <div className="w-16 border-r border-gray-200 bg-gray-50 flex flex-col items-center py-4 gap-3">
        <div className="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center font-bold text-sm shadow-sm">
          BT
        </div>
        <div className="flex flex-col gap-2 w-full px-2">
          {navItems.map((item) => (
            <button
              key={item.key}
              onClick={() => setActive(item.key)}
              className={`w-full flex flex-col items-center justify-center gap-1 py-2 rounded-lg text-[10px] transition-colors ${
                active === item.key
                  ? 'bg-blue-100 text-blue-700'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
              }`}
              title={item.label}
            >
              <span className="text-lg">{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="w-64 bg-white h-full overflow-hidden">
        {active === 'nodes' && <Sidebar nodeMetas={nodeMetas} language={settings.language} />}
        {active === 'tools' && <ToolLibrary tools={tools} language={settings.language} />}
        {active === 'knowledge' && (
          <div className="p-4 h-full overflow-y-auto">
            <div className="mb-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Knowledge Base</div>
            <div className="space-y-2">
              <div className="text-[11px] text-gray-500">
                Supported: .txt .md .pdf .docx (PDF/DOCX require pypdf / python-docx)
              </div>
              <label className="block text-xs text-gray-600">Files</label>
              <input
                type="file"
                multiple
                accept=".txt,.md,.pdf,.docx"
                onChange={(e) => setIngestFiles(Array.from(e.target.files || []))}
                className="w-full text-xs"
              />
              <label className="block text-xs text-gray-600">Chunk Size</label>
              <input
                type="number"
                className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                placeholder="chunk_size"
                value={ingestChunkSize}
                onChange={(e) => setIngestChunkSize(Number(e.target.value || 0))}
              />
              <label className="block text-xs text-gray-600">Overlap</label>
              <input
                type="number"
                className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                placeholder="overlap"
                value={ingestOverlap}
                onChange={(e) => setIngestOverlap(Number(e.target.value || 0))}
              />
              <label className="block text-xs text-gray-600">Knowledge Base ID (memory_id)</label>
              <input
                className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                placeholder="memory_id (default)"
                value={ingestMemoryId}
                onChange={(e) => setIngestMemoryId(e.target.value)}
              />
              <div className="text-[11px] text-gray-500">
                ToolExecutor / AgentLLM 的 memory_id 需要与这里一致。
              </div>
              <div className="text-[11px] text-gray-400">
                当前 workflow_id: <span className="font-mono">{workflowId || 'unknown'}</span>
              </div>
              <button
                onClick={handleIngest}
                disabled={ingestLoading}
                className="w-full text-sm px-3 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:bg-gray-300"
              >
                {ingestLoading ? 'Ingesting...' : 'Ingest Files'}
              </button>
              {ingestStatus && (
                <div className="text-xs text-gray-500">{ingestStatus}</div>
              )}
              {ingestResults.length > 0 && (
                <div className="mt-2 space-y-1">
                  {ingestResults.map((r, idx) => (
                    <div
                      key={`${r.file}-${idx}`}
                      className={`text-xs ${r.ok ? 'text-green-700' : 'text-red-600'}`}
                    >
                      {r.ok ? '✅' : '❌'} {r.file} {r.ok ? `(${r.chunks} chunks)` : (r.error ? `- ${r.error}` : '')}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
        {active === 'workflow' && (
          <div className="p-4 h-full overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Workflow Templates</div>
              <button
                onClick={handleSaveTemplate}
                className="text-xs px-2 py-1 rounded bg-gray-100 text-gray-700 hover:bg-gray-200"
              >
                Save
              </button>
            </div>
            <div className="space-y-3">
              <div className="border rounded p-3 bg-white">
                <div className="text-sm font-medium text-gray-900">ReAct Agent</div>
                <div className="text-xs text-gray-500 mt-1">LoopUntilSuccess + AgentLLM + ToolExecutor + Condition</div>
                <button
                  onClick={() => onApplyWorkflow(buildReactTemplate())}
                  className="mt-3 text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700"
                >
                  Use Template
                </button>
              </div>
              <div className="border rounded p-3 bg-white">
                <div className="text-sm font-medium text-gray-900">Reflexion Agent</div>
                <div className="text-xs text-gray-500 mt-1">LoopUntilSuccess + AgentLLM + Parser + Condition</div>
                <button
                  onClick={() => onApplyWorkflow(buildReflexionTemplate())}
                  className="mt-3 text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700"
                >
                  Use Template
                </button>
              </div>
              <div className="border rounded p-3 bg-white">
                <div className="text-sm font-medium text-gray-900">RAG (Memory)</div>
                <div className="text-xs text-gray-500 mt-1">LoopUntilSuccess + AgentLLM + Memory Tools + Condition</div>
                <button
                  onClick={() => onApplyWorkflow(buildRagTemplate())}
                  className="mt-3 text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700"
                >
                  Use Template
                </button>
              </div>
              {customTemplates.length > 0 && (
                <div className="pt-2 border-t">
                  <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Custom Templates</div>
                  <div className="space-y-2">
                    {customTemplates.map((tpl) => (
                      <div key={tpl.id} className="border rounded p-3 bg-white flex items-start justify-between gap-2">
                        <div>
                          <div className="text-sm font-medium text-gray-900">{tpl.name}</div>
                          <div className="text-xs text-gray-400 mt-1">Saved Template</div>
                          <button
                            onClick={() => onApplyWorkflow(tpl.workflow)}
                            className="mt-3 text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700"
                          >
                            Use Template
                          </button>
                        </div>
                        <button
                          onClick={() => handleDeleteTemplate(tpl.id)}
                          className="text-xs px-2 py-1 rounded text-red-600 hover:bg-red-50"
                          title="Delete template"
                        >
                          Delete
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
        {active === 'settings' && (
          <div className="p-4 h-full overflow-y-auto">
            <div className="mb-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Settings</div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs text-gray-600 mb-1">Language</label>
                <select
                  className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                  value={settings.language}
                  onChange={(e) => setSettings({ ...settings, language: e.target.value })}
                >
                  <option value="zh">中文</option>
                  <option value="en">English</option>
                </select>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs text-gray-600">Memory</div>
                  <div className="text-[11px] text-gray-400">Enable/disable Memory tools & stores</div>
                </div>
                <button
                  className={`w-11 h-6 rounded-full transition-colors ${settings.memory_enabled ? 'bg-blue-600' : 'bg-gray-300'}`}
                  onClick={() => setSettings({ ...settings, memory_enabled: !settings.memory_enabled })}
                >
                  <div className={`h-5 w-5 bg-white rounded-full shadow transform transition-transform ${settings.memory_enabled ? 'translate-x-5' : 'translate-x-1'}`} />
                </button>
              </div>

              <div>
                <label className="block text-xs text-gray-600 mb-1">API Key</label>
                <input
                  type="password"
                  className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                  placeholder="API_KEY"
                  value={settings.api_key}
                  onChange={(e) => setSettings({ ...settings, api_key: e.target.value })}
                />
              </div>

              <div>
                <label className="block text-xs text-gray-600 mb-1">Base URL</label>
                <input
                  className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                  placeholder="https://..."
                  value={settings.base_url}
                  onChange={(e) => setSettings({ ...settings, base_url: e.target.value })}
                />
              </div>

              <div>
                <label className="block text-xs text-gray-600 mb-1">Model</label>
                <input
                  className="w-full text-sm p-2 border rounded focus:ring-2 focus:ring-blue-500 outline-none"
                  placeholder="gemini-2.5-flash"
                  value={settings.model}
                  onChange={(e) => setSettings({ ...settings, model: e.target.value })}
                />
              </div>

              <button
                onClick={handleSaveSettings}
                disabled={loadingSettings}
                className="w-full mt-2 text-sm px-3 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:bg-gray-300"
              >
                {loadingSettings ? 'Loading...' : 'Save to .env'}
              </button>

              {settingsStatus && (
                <div className="text-xs text-gray-500">{settingsStatus}</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
