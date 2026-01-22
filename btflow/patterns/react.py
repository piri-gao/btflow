"""
BTflow Patterns: ReAct Agent Implementation.

ReAct (Reasoning + Acting) 是一种 LLM Agent 模式，交替进行推理和工具调用。

Tree Structure (使用 btflow.LoopUntilSuccess):
    Root (LoopUntilSuccess)
    └── Sequence (memory=True)
        ├── ReActGeminiNode    → 调用 LLM，输出 Thought/Action/Final Answer
        ├── ToolExecutor       → 检测并执行 Action（无则跳过）
        └── IsFinalAnswer      → 条件：有 Final Answer → SUCCESS，否则 FAILURE

循环逻辑：
    - Sequence 成功（IsFinalAnswer 返回 SUCCESS）→ LoopUntilSuccess 结束
    - Sequence 失败（IsFinalAnswer 返回 FAILURE）→ 返回 RUNNING，触发下一轮
"""
import re
import operator
from typing import Annotated, List, Dict, Optional, Type
from pydantic import BaseModel, Field
from py_trees.common import Status
from py_trees.composites import Sequence
from py_trees.behaviour import Behaviour

from btflow.core.composites import LoopUntilSuccess
from btflow.core.behaviour import AsyncBehaviour
from btflow.core.state import StateManager
from btflow.core.agent import BTAgent
from btflow.core.logging import logger
from btflow.patterns.tools import Tool


# ============ State Schema ============

class ReActState(BaseModel):
    """ReAct Agent 的状态定义"""
    # 消息历史，使用 Reducer 自动追加
    messages: Annotated[List[str], operator.add] = Field(default_factory=list)
    # 最终答案
    final_answer: Optional[str] = None
    # 当前轮数
    round: int = 0


# ============ ReAct Nodes ============

class ReActGeminiNode(AsyncBehaviour):
    """
    ReAct 推理节点：调用 Gemini 进行思考。
    
    每次 tick 都会调用 LLM，由 Repeat 控制循环。
    """
    
    def __init__(
        self,
        name: str = "ReActGemini",
        model: str = "gemini-2.5-flash",
        system_prompt: Optional[str] = None,
        tools_description: str = ""
    ):
        super().__init__(name)
        self.model = model
        self.tools_description = tools_description
        self.system_prompt = system_prompt or self._get_default_prompt()
        
        # 延迟导入避免循环依赖
        import os
        from google import genai
        
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("⚠️ [{}] GOOGLE_API_KEY not found!", self.name)
        
        self.client = genai.Client(api_key=api_key)
    
    def _get_default_prompt(self) -> str:
        tools_section = f"\nAvailable tools:\n{self.tools_description}" if self.tools_description else ""
        
        return f"""You are a helpful assistant that can use tools to answer questions.

You must follow this EXACT format:

Thought: [your reasoning about what to do next]
Action: [tool name]
Input: [tool input]

OR when you have the final answer:

Thought: [your final reasoning]
Final Answer: [your answer to the user]
{tools_section}

IMPORTANT RULES:
1. Always start with "Thought:" to explain your reasoning
2. Use EXACT tool names as shown above (lowercase)
3. After seeing an Observation, continue with another "Thought:"
4. Only use "Final Answer:" when you have the complete answer

Always think step by step."""
    
    async def update_async(self) -> Status:
        """调用 Gemini 进行 ReAct 推理"""
        import asyncio
        from google.genai import types
        
        try:
            state = self.state_manager.get()
            
            # 构建 prompt
            prompt_content = "\n".join(state.messages)
            
            logger.debug("🤖 [{}] 调用 Gemini ({})...", self.name, self.model)
            
            # 调用 API
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.model,
                    contents=prompt_content,
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_prompt,
                        temperature=0.7
                    )
                ),
                timeout=60.0
            )
            
            content = response.text.strip()
            
            if not content:
                logger.warning("⚠️ [{}] LLM 返回空响应", self.name)
                return Status.FAILURE
            
            # 写入原始 LLM 输出
            self.state_manager.update({
                "messages": [content],
                "round": state.round + 1
            })
            
            logger.info("💭 [{}] Round {} 响应:\n{}", self.name, state.round + 1, content[:200])
            return Status.SUCCESS
            
        except asyncio.TimeoutError:
            logger.warning("⏰ [{}] 请求超时", self.name)
            return Status.FAILURE
        except Exception as e:
            logger.error("🔥 [{}] Gemini 调用失败: {}", self.name, e)
            return Status.FAILURE


class ToolExecutor(AsyncBehaviour):
    """
    工具执行节点：检测并执行 Action。
    
    解析最后一条消息中的 Action/Input，执行对应工具，
    将结果作为 Observation 写入消息历史。
    
    无论是否有 Action，都返回 SUCCESS（不阻塞 Sequence）。
    """
    
    # ReAct 格式正则
    ACTION_PATTERN = re.compile(
        r"Action:\s*(.+?)\s*\n\s*Input:\s*(.+)",
        re.IGNORECASE | re.DOTALL
    )
    
    def __init__(self, name: str = "ToolExecutor", tools: Optional[List[Tool]] = None):
        super().__init__(name)
        self.tools: Dict[str, Tool] = {}
        if tools:
            for tool in tools:
                self.register_tool(tool)
    
    def register_tool(self, tool: Tool):
        """注册工具"""
        self.tools[tool.name.lower()] = tool
        logger.debug("🔧 [{}] 注册工具: {}", self.name, tool.name)
    
    def get_tools_description(self) -> str:
        """获取所有工具的描述（用于 LLM prompt）"""
        if not self.tools:
            return "No tools available."
        
        descriptions = []
        for name, tool in self.tools.items():
            descriptions.append(f"- {name}: {tool.description}")
        return "\n".join(descriptions)
    
    async def update_async(self) -> Status:
        """检测并执行 Action"""
        state = self.state_manager.get()
        
        if not state.messages:
            return Status.SUCCESS
        
        last_msg = state.messages[-1]
        
        # 尝试解析 Action
        match = self.ACTION_PATTERN.search(last_msg)
        
        if not match:
            # 没有 Action（可能是 Final Answer），直接跳过
            logger.debug("📭 [{}] 未检测到 Action，跳过", self.name)
            return Status.SUCCESS
        
        tool_name = match.group(1).strip().lower()
        tool_input = match.group(2).strip()
        
        logger.info("⚙️ [{}] 执行 Action: {} Input: {}", self.name, tool_name, tool_input)
        
        # 查找并执行工具
        tool = self.tools.get(tool_name)
        
        if tool:
            try:
                result = tool.run(tool_input)
                observation = f"Observation: {result}"
            except Exception as e:
                observation = f"Observation: Error executing {tool_name}: {e}"
                logger.warning("⚠️ [{}] 工具执行失败: {}", self.name, e)
        else:
            observation = f"Observation: Tool '{tool_name}' not found. Available tools: {list(self.tools.keys())}"
            logger.warning("⚠️ [{}] 未知工具: {}", self.name, tool_name)
        
        # 写入 Observation
        self.state_manager.update({"messages": [observation]})
        
        return Status.SUCCESS


class IsFinalAnswer(Behaviour):
    """
    条件节点：检查是否有 Final Answer。
    
    这是一个同步节点（非 AsyncBehaviour），因为只需检查状态。
    
    - 有 Final Answer → SUCCESS（Sequence 成功，Repeat 结束）
    - 无 Final Answer → FAILURE（Sequence 失败，Repeat 重试）
    """
    
    FINAL_ANSWER_PATTERN = re.compile(
        r"Final Answer:\s*(.+)",
        re.IGNORECASE | re.DOTALL
    )
    
    def __init__(self, name: str = "IsFinalAnswer", max_rounds: int = 10):
        super().__init__(name)
        self.max_rounds = max_rounds
        self.state_manager: Optional[StateManager] = None
    
    def update(self) -> Status:
        """检查是否有 Final Answer"""
        if self.state_manager is None:
            logger.error("❌ [{}] state_manager 未注入", self.name)
            return Status.FAILURE
        
        state = self.state_manager.get()
        
        # 检查是否超过最大轮数
        if state.round >= self.max_rounds:
            logger.warning("⚠️ [{}] 达到最大轮数 ({}), 强制停止", self.name, self.max_rounds)
            # 更新状态，标记超时
            self.state_manager.update({"final_answer": "[MAX_ROUNDS_EXCEEDED]"})
            return Status.SUCCESS  # 返回 SUCCESS 以终止循环
        
        # 尝试提取 Final Answer
        final_answer = self._extract_final_answer(state.messages)
        
        if final_answer:
            logger.info("✅ [{}] 检测到 Final Answer: {}...", 
                       self.name, final_answer[:50] if len(final_answer) > 50 else final_answer)
            self.state_manager.update({"final_answer": final_answer})
            return Status.SUCCESS  # 成功 → Repeat 结束
        
        logger.debug("🔄 [{}] 未检测到 Final Answer，继续下一轮 (Round {}/{})", 
                    self.name, state.round, self.max_rounds)
        # 触发 tick_signal，确保 event-driven 模式下 Repeat 能继续执行
        self.state_manager.update({})
        return Status.FAILURE  # 失败 → Repeat 重试
    
    def _extract_final_answer(self, messages: List[str]) -> Optional[str]:
        """从消息中提取 Final Answer"""
        if not messages:
            return None
        
        last_msg = messages[-1]
        match = self.FINAL_ANSWER_PATTERN.search(last_msg)
        
        if match:
            return match.group(1).strip()
        return None


# ============ ReAct Agent Factory ============

class ReActAgent:
    """
    ReAct Agent 工厂类。
    
    Example:
        from btflow.patterns import ReActAgent
        from btflow.patterns.tools import Tool
        
        class Calculator(Tool):
            name = "calculator"
            description = "Perform calculations"
            def run(self, input: str) -> str:
                return str(eval(input))
        
        agent = ReActAgent.create_with_gemini(
            tools=[Calculator()],
            max_rounds=10
        )
        
        result = await agent.run({"messages": ["Question: What is 2+2?"]})
        print(result.final_answer)
    """
    
    @staticmethod
    def create_with_gemini(
        tools: Optional[List[Tool]] = None,
        model: str = "gemini-2.5-flash",
        max_rounds: int = 10,
        state_schema: Type[BaseModel] = ReActState
    ) -> BTAgent:
        """
        使用 Gemini 创建 ReAct Agent。
        
        Args:
            tools: 可用工具列表
            model: Gemini 模型名称
            max_rounds: 最大推理轮数
            state_schema: 状态 Schema（默认 ReActState）
        
        Returns:
            配置好的 BTAgent 实例
        """
        tools = tools or []
        
        # 构建工具描述
        tool_executor = ToolExecutor(name="ToolExecutor", tools=tools)
        tools_desc = tool_executor.get_tools_description()
        
        # 创建 LLM 节点
        llm_node = ReActGeminiNode(
            name="ReActLLM",
            model=model,
            tools_description=tools_desc
        )
        
        # 构建循环体 Sequence (memory=True 保持执行进度)
        # 注意：memory=True 确保 async 节点完成后才继续下一个
        loop_body = Sequence(name="ReActLoop", memory=True, children=[
            llm_node,
            tool_executor,
            IsFinalAnswer(name="CheckAnswer", max_rounds=max_rounds)
        ])
        
        # 使用 LoopUntilSuccess 控制循环
        # 子节点成功 → 结束，子节点失败 → 返回 RUNNING 继续
        root = LoopUntilSuccess(name="ReActAgent", max_iterations=max_rounds, child=loop_body)
        
        # 创建状态管理器
        state_manager = StateManager(schema=state_schema)
        state_manager.initialize({})
        
        # 创建 Agent
        return BTAgent(root, state_manager)
