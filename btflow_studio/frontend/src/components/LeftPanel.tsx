import { useState } from 'react';
import Sidebar from './Sidebar';
import ToolLibrary from './ToolLibrary';

interface LeftPanelProps {
  nodeMetas: any[];
  tools: any[];
  onApplyWorkflow: (workflow: { nodes: any[]; edges: any[] }) => void;
}

type PanelKey = 'workflow' | 'nodes' | 'tools' | 'settings';

const navItems: Array<{ key: PanelKey; label: string; icon: string }> = [
  { key: 'workflow', label: 'Workflow', icon: '🗂️' },
  { key: 'nodes', label: 'Nodes', icon: '🧩' },
  { key: 'tools', label: 'Tools', icon: '🧰' },
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

Score: [A number from 0 to 10, be honest and critical]

Reflection: [If score < 8, explain what could be improved. If score >= 8, write "The answer is satisfactory."]

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

export default function LeftPanel({ nodeMetas, tools, onApplyWorkflow }: LeftPanelProps) {
  const [active, setActive] = useState<PanelKey>('nodes');

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
        {active === 'nodes' && <Sidebar nodeMetas={nodeMetas} />}
        {active === 'tools' && <ToolLibrary tools={tools} />}
        {active === 'workflow' && (
          <div className="p-4 h-full overflow-y-auto">
            <div className="mb-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Workflow Templates</div>
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
            </div>
          </div>
        )}
        {active === 'settings' && (
          <div className="p-4 text-sm text-gray-500">
            Settings panel coming soon.
          </div>
        )}
      </div>
    </div>
  );
}
