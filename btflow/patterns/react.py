"""
BTflow Patterns: ReAct Agent Implementation.

ReAct (Reasoning + Acting) 是一种 LLM Agent 模式，交替进行推理和工具调用。

Tree Structure:
    Root (Sequence)
    ├── ReActLLMNode     → 调用 LLM，输出 Thought/Action/Final Answer
    ├── ToolExecutor     → 检测并执行 Action（无则跳过）
    └── CheckFinalAnswer → 提取 final_answer，触发下一轮
"""
import re
import operator
from typing import Annotated, List, Dict, Optional, Type
from pydantic import BaseModel, Field
from py_trees.common import Status
from py_trees.composites import Sequence

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
    # 最终答案（用于触发 wake signal 和终止判断）
    final_answer: Optional[str] = None
    # 当前轮数
    round: int = 0


# ============ ReAct Nodes ============

class ReActLLMNode(AsyncBehaviour):
    """
    ReAct 推理节点：调用 LLM 进行思考。
    
    输出格式（ReAct 标准格式）：
        Thought: [思考过程]
        Action: [工具名]
        Input: [工具参数]
    
    或者：
        Thought: [思考过程]
        Final Answer: [最终答案]
    """
    
    def __init__(
        self, 
        name: str = "ReActLLM",
        llm_node: Optional[AsyncBehaviour] = None,
        system_prompt: Optional[str] = None
    ):
        """
        Args:
            name: 节点名称
            llm_node: 底层 LLM 节点（如 GeminiNode）。如果提供，将代理调用。
            system_prompt: 如果不提供 llm_node，需要子类实现 _call_llm
        """
        super().__init__(name)
        self.llm_node = llm_node
        self.system_prompt = system_prompt or self._get_default_prompt()
    
    def _get_default_prompt(self) -> str:
        return """You are a helpful assistant that can use tools to answer questions.

You must follow this EXACT format:

Thought: [your reasoning about what to do next]
Action: [tool name]
Input: [tool input]

OR when you have the final answer:

Thought: [your final reasoning]
Final Answer: [your answer to the user]

Available tools will be provided in the conversation.
Always think step by step."""
    
    async def update_async(self) -> Status:
        """调用 LLM 进行推理"""
        try:
            state = self.state_manager.get()
            
            # 构建 prompt
            prompt = self._build_prompt(state.messages)
            
            # 调用 LLM
            response = await self._call_llm(prompt)
            
            if not response:
                logger.warning("⚠️ [{}] LLM 返回空响应", self.name)
                return Status.FAILURE
            
            # 写入消息历史
            self.state_manager.update({"messages": [response]})
            
            logger.debug("💭 [{}] LLM 响应: {}...", self.name, response[:100])
            return Status.SUCCESS
            
        except Exception as e:
            logger.error("🔥 [{}] LLM 调用失败: {}", self.name, e)
            return Status.FAILURE
    
    def _build_prompt(self, messages: List[str]) -> str:
        """构建 LLM prompt"""
        return "\n".join(messages)
    
    async def _call_llm(self, prompt: str) -> str:
        """
        调用 LLM。子类可以重写此方法。
        
        如果提供了 llm_node，将代理调用。
        """
        if self.llm_node:
            # 代理到底层 LLM 节点
            # 注意：这里简化处理，实际实现可能需要更复杂的协调
            raise NotImplementedError(
                "代理 LLM 节点暂未实现。请子类化 ReActLLMNode 并重写 _call_llm 方法，"
                "或使用 ReActGeminiNode。"
            )
        raise NotImplementedError("子类必须实现 _call_llm 方法")


class ReActGeminiNode(AsyncBehaviour):
    """
    专门用于 ReAct 的 Gemini 节点。
    
    相比普通 GeminiNode 的改进：
    1. 只在需要时调用 LLM（最后一条消息是 Question 或 Observation）
    2. 写入原始 LLM 输出，不加 "Gemini:" 前缀
    3. 集成 ReAct 专用的 system prompt
    """
    
    def __init__(
        self,
        name: str = "ReActGemini",
        model: str = "gemini-2.5-flash",
        system_prompt: Optional[str] = None,
        tools_description: str = ""
    ):
        """
        Args:
            name: 节点名称
            model: Gemini 模型名称
            system_prompt: 系统提示词（如不提供则使用默认 ReAct prompt）
            tools_description: 可用工具的描述
        """
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
    
    def _should_call_llm(self, messages: List[str]) -> bool:
        """
        判断是否需要调用 LLM。
        
        只有在以下情况才需要调用：
        - 消息列表为空
        - 最后一条消息是 Question（用户输入）
        - 最后一条消息是 Observation（工具输出）
        
        不需要调用的情况：
        - 最后一条消息包含 Thought/Action（LLM 刚刚输出）
        - 最后一条消息包含 Final Answer
        """
        if not messages:
            return True
        
        last_msg = messages[-1].strip()
        
        # 如果最后消息是 Observation，需要调用 LLM 继续思考
        if last_msg.startswith("Observation:"):
            return True
        
        # 如果最后消息是 Question，需要调用 LLM 开始思考
        if last_msg.startswith("Question:"):
            return True
        
        # 如果最后消息包含 Thought 或 Action 或 Final Answer，说明 LLM 刚输出过
        if "Thought:" in last_msg or "Action:" in last_msg or "Final Answer:" in last_msg:
            logger.debug("📭 [{}] 跳过 LLM 调用（已有 LLM 输出）", self.name)
            return False
        
        # 其他情况，调用 LLM
        return True
    
    def initialise(self) -> None:
        """
        重写 initialise() 方法，在创建任务前判断是否需要执行。
        """
        # 检查是否需要执行
        self._skip_execution = False
        
        if self.state_manager is not None:
            state = self.state_manager.get()
            if not self._should_call_llm(state.messages):
                self._skip_execution = True
                logger.debug("📭 [{}] 跳过 LLM 初始化（不需要调用）", self.name)
                return
        
        # 需要执行，调用父类的 initialise()
        super().initialise()
    
    def update(self) -> Status:
        """
        重写 update() 方法，配合 initialise() 的跳过逻辑。
        """
        if self._skip_execution:
            return Status.SUCCESS
        
        return super().update()
    
    async def update_async(self) -> Status:
        """调用 Gemini 进行 ReAct 推理"""
        import asyncio
        from google.genai import types
        
        try:
            state = self.state_manager.get()
            
            # 检查是否需要调用 LLM
            if not self._should_call_llm(state.messages):
                return Status.SUCCESS
            
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
                timeout=60.0  # ReAct 可能需要更长的思考时间
            )
            
            content = response.text.strip()
            
            if not content:
                logger.warning("⚠️ [{}] LLM 返回空响应", self.name)
                return Status.FAILURE
            
            # 写入原始 LLM 输出（不加前缀）
            self.state_manager.update({"messages": [content]})
            
            logger.debug("💭 [{}] LLM 响应:\n{}", self.name, content[:200])
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
    
    无论是否检测到 Action，都返回 SUCCESS（不阻塞 Sequence）。
    """
    
    # ReAct 格式正则
    ACTION_PATTERN = re.compile(
        r"Action:\s*(.+?)\s*\n\s*Input:\s*(.+)",
        re.IGNORECASE | re.DOTALL
    )
    
    def __init__(self, name: str = "ToolExecutor", tools: Optional[List[Tool]] = None):
        """
        Args:
            name: 节点名称
            tools: 可用工具列表
        """
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
    
    def _should_execute_tool(self, messages: List[str]) -> bool:
        """判断是否需要执行工具"""
        if not messages:
            return False
        
        last_msg = messages[-1].strip()
        
        # 如果最后消息是 Observation，不需要执行
        if last_msg.startswith("Observation:"):
            return False
        
        # 检查是否有 Action
        match = self.ACTION_PATTERN.search(last_msg)
        return match is not None
    
    def initialise(self) -> None:
        """
        重写 initialise() 方法，在创建任务前判断是否需要执行。
        """
        self._skip_execution = False
        
        if self.state_manager is not None:
            state = self.state_manager.get()
            if not self._should_execute_tool(state.messages):
                self._skip_execution = True
                logger.debug("📭 [{}] 跳过工具初始化（不需要执行）", self.name)
                return
        
        super().initialise()
    
    def update(self) -> Status:
        """
        重写 update() 方法，配合 initialise() 的跳过逻辑。
        """
        if self._skip_execution:
            return Status.SUCCESS
        
        return super().update()
    
    async def update_async(self) -> Status:
        """检测并执行 Action"""
        state = self.state_manager.get()
        
        if not state.messages:
            return Status.SUCCESS  # 无消息，跳过
        
        last_msg = state.messages[-1]
        
        # 如果最后一条消息已经是 Observation，说明工具已执行，跳过
        if last_msg.strip().startswith("Observation:"):
            logger.debug("📭 [{}] 最后消息是 Observation，跳过", self.name)
            return Status.SUCCESS
        
        # 尝试解析 Action
        match = self.ACTION_PATTERN.search(last_msg)
        
        if not match:
            # 没有检测到 Action（可能是 Final Answer），跳过
            logger.debug("📭 [{}] 未检测到 Action，跳过", self.name)
            return Status.SUCCESS
        
        tool_name = match.group(1).strip().lower()
        tool_input = match.group(2).strip()
        
        logger.info("⚙️ [{}] 检测到 Action: {} Input: {}", self.name, tool_name, tool_input)
        
        # 查找工具
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


class CheckFinalAnswer(AsyncBehaviour):
    """
    终止检测节点：检查是否有 Final Answer。
    
    - 有 Final Answer → SUCCESS（任务完成）
    - 无 Final Answer → 更新状态触发下一轮 → RUNNING
    - 超过 max_rounds → FAILURE（防止死循环）
    """
    
    FINAL_ANSWER_PATTERN = re.compile(
        r"Final Answer:\s*(.+)",
        re.IGNORECASE | re.DOTALL
    )
    
    def __init__(self, name: str = "CheckFinalAnswer", max_rounds: int = 10):
        """
        Args:
            name: 节点名称
            max_rounds: 最大推理轮数（防止死循环）
        """
        super().__init__(name)
        self.max_rounds = max_rounds
    
    async def update_async(self) -> Status:
        """检查并提取 Final Answer"""
        state = self.state_manager.get()
        current_round = state.round
        
        logger.debug("🔍 [{}] 检查中... Round={}, Messages={}", 
                   self.name, current_round, len(state.messages))
        
        # 尝试提取 Final Answer
        final_answer = self._extract_final_answer(state.messages)
        
        # 总是更新状态（触发 wake signal）
        self.state_manager.update({
            "final_answer": final_answer,
            "round": current_round + 1
        })
        
        if final_answer:
            logger.info("✅ [{}] 检测到 Final Answer: {}...", 
                       self.name, final_answer[:50] if len(final_answer) > 50 else final_answer)
            return Status.SUCCESS
        
        # 检查是否超限
        if current_round + 1 >= self.max_rounds:
            logger.warning("⚠️ [{}] 达到最大轮数 ({}), 强制停止", self.name, self.max_rounds)
            return Status.FAILURE
        
        logger.debug("🔄 [{}] 继续下一轮 (Round {}/{})", 
                    self.name, current_round + 1, self.max_rounds)
        return Status.RUNNING
    
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
    
    提供便捷方法创建完整的 ReAct Agent。
    
    Example:
        from btflow.patterns import ReActAgent, Tool
        from btflow.nodes.llm import GeminiNode
        
        # 定义工具
        class MyTool(Tool):
            name = "search"
            description = "Search the web"
            def run(self, input: str) -> str:
                return "search result"
        
        # 创建 Agent
        agent = ReActAgent.create(
            llm_class=GeminiNode,
            llm_kwargs={"model": "gemini-2.5-flash"},
            tools=[MyTool()],
            max_rounds=10
        )
        
        # 运行
        result = await agent.run({"messages": ["Question: What is 2+2?"]})
    """
    
    @staticmethod
    def create(
        llm_class: Type[AsyncBehaviour],
        llm_kwargs: Optional[Dict] = None,
        tools: Optional[List[Tool]] = None,
        max_rounds: int = 10,
        state_schema: Type[BaseModel] = ReActState
    ) -> BTAgent:
        """
        创建 ReAct Agent。
        
        Args:
            llm_class: LLM 节点类（如 GeminiNode）
            llm_kwargs: 传递给 LLM 节点的参数
            tools: 可用工具列表
            max_rounds: 最大推理轮数
            state_schema: 状态 Schema（默认 ReActState）
        
        Returns:
            配置好的 BTAgent 实例
        """
        llm_kwargs = llm_kwargs or {}
        tools = tools or []
        
        # 构建工具描述
        tool_executor = ToolExecutor(name="ToolExecutor", tools=tools)
        tools_desc = tool_executor.get_tools_description()
        
        # 构建系统 prompt
        react_prompt = f"""You are a helpful assistant that can use tools to answer questions.

You must follow this EXACT format:

Thought: [your reasoning about what to do next]
Action: [tool name]
Input: [tool input]

OR when you have the final answer:

Thought: [your final reasoning]
Final Answer: [your answer to the user]

Available tools:
{tools_desc}

Always think step by step. After receiving an Observation, continue with another Thought."""
        
        # 创建 LLM 节点
        if "system_prompt" not in llm_kwargs:
            llm_kwargs["system_prompt"] = react_prompt
        
        llm_node = llm_class(name="ReActLLM", **llm_kwargs)
        
        # 构建行为树
        # 使用 memory=False，每次 tick 从头开始评估
        # ToolExecutor 会自动跳过已处理的 Action（通过检查 Observation）
        root = Sequence(name="ReAct", memory=False, children=[
            llm_node,
            tool_executor,
            CheckFinalAnswer(name="CheckAnswer", max_rounds=max_rounds)
        ])
        
        # 创建状态管理器
        state_manager = StateManager(schema=state_schema)
        state_manager.initialize({})
        
        # 创建 Agent
        return BTAgent(root, state_manager)
    
    @staticmethod
    def get_initial_message(question: str, tools_desc: str = "") -> str:
        """生成初始消息"""
        msg = f"Question: {question}"
        if tools_desc:
            msg = f"Available tools:\n{tools_desc}\n\n{msg}"
        return msg
    
    @staticmethod
    def create_with_gemini(
        tools: Optional[List[Tool]] = None,
        model: str = "gemini-2.5-flash",
        max_rounds: int = 10,
        state_schema: Type[BaseModel] = ReActState
    ) -> BTAgent:
        """
        使用 Gemini 创建 ReAct Agent（推荐方式）。
        
        使用专门的 ReActGeminiNode，正确处理 ReAct 格式：
        - 只在需要时调用 LLM（避免重复调用）
        - 输出原始格式（无 "Gemini:" 前缀）
        
        Args:
            tools: 可用工具列表
            model: Gemini 模型名称
            max_rounds: 最大推理轮数
            state_schema: 状态 Schema（默认 ReActState）
        
        Returns:
            配置好的 BTAgent 实例
            
        Example:
            agent = ReActAgent.create_with_gemini(
                tools=[CalculatorTool(), SearchTool()],
                model="gemini-2.5-flash",
                max_rounds=10
            )
            result = await agent.run({"messages": ["Question: What is 2+2?"]})
        """
        tools = tools or []
        
        # 构建工具描述
        tool_executor = ToolExecutor(name="ToolExecutor", tools=tools)
        tools_desc = tool_executor.get_tools_description()
        
        # 创建 ReAct 专用的 Gemini 节点
        llm_node = ReActGeminiNode(
            name="ReActLLM",
            model=model,
            tools_description=tools_desc
        )
        
        # 构建行为树
        # 使用 memory=False，每次 tick 从头开始评估
        # ReActGeminiNode 会自动跳过不需要的 LLM 调用
        # ToolExecutor 会自动跳过已处理的 Action
        root = Sequence(name="ReAct", memory=False, children=[
            llm_node,
            tool_executor,
            CheckFinalAnswer(name="CheckAnswer", max_rounds=max_rounds)
        ])
        
        # 创建状态管理器
        state_manager = StateManager(schema=state_schema)
        state_manager.initialize({})
        
        # 创建 Agent
        return BTAgent(root, state_manager)

