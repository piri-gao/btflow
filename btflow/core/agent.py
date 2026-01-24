"""
BTAgent: 统一接入层
支持 step() 和 run() 双模驱动
"""
import asyncio
from typing import Literal, Dict, Any, Optional, Union, TYPE_CHECKING
from py_trees.common import Status
from py_trees.behaviour import Behaviour

from btflow.core.runtime import ReactiveRunner

if TYPE_CHECKING:
    from btflow.core.state import StateManager


class BTAgent:
    """
    BTflow 统一接入层。
    
    封装 ReactiveRunner，提供两种运行模式：
    - step(): 步进模式，用于 RL 训练 / 高频仿真
    - run(): 任务模式，用于对话机器人 / 工作流
    
    Example (推荐用法):
        agent = BTAgent(root, state_manager)
        
        # 对话场景
        result = await agent.run({"user_input": "你好"})
        
        # RL 场景
        action = await agent.step({"observation": obs})
    
    Example (兼容旧 API):
        runner = ReactiveRunner(root, state_manager)
        agent = BTAgent(runner)
    """
    
    def __init__(
        self, 
        root_or_runner: Union[Behaviour, ReactiveRunner],
        state_manager: Optional["StateManager"] = None
    ):
        """
        创建 BTAgent。
        
        Args:
            root_or_runner: 行为树根节点，或者已创建的 ReactiveRunner（兼容旧 API）
            state_manager: 状态管理器（当第一个参数是根节点时必需）
        """
        if isinstance(root_or_runner, ReactiveRunner):
            # 兼容旧 API: BTAgent(runner)
            self.runner = root_or_runner
            self.state_manager = root_or_runner.state_manager
        else:
            # 新 API: BTAgent(root, state_manager)
            if state_manager is None:
                raise ValueError("state_manager is required when passing root node")
            self.runner = ReactiveRunner(root_or_runner, state_manager)
            self.state_manager = state_manager
        
        self._mode: Literal["idle", "step", "run"] = "idle"
    
    async def step(
        self, 
        obs: Optional[Dict[str, Any]] = None,
        yield_to_async: bool = False
    ) -> Dict[str, Any]:
        """
        步进模式：强制同步 tick，返回动作快照。
        
        适用于 RL 训练、高频仿真、实时控制。
        每帧：重置动作 → 注入观测 → tick → 返回动作
        
        Args:
            obs: 观测数据，将被 update 到 state
            yield_to_async: 是否让步给事件循环，让异步任务有机会执行。
                - False: 纯同步场景，性能最优
                - True: 脑肌结合场景，允许异步大脑节点在后台推进
            
        Returns:
            本帧动作快照（ActionField 标记的字段）
            
        Raises:
            RuntimeError: 如果 run() 正在执行
            
        Note:
            脑肌结合场景示例（Parallel 节点包含异步大脑 + 同步肌肉）：
            - 大脑节点：异步 LLM 推理，更新持久化状态（如 target_position）
            - 肌肉节点：同步控制，读取大脑状态，输出 ActionField
            - 设置 yield_to_async=True 确保 LLM 任务能在后台推进
        """
        if self._mode == "run":
            raise RuntimeError("Cannot step() while run() is active")
        
        self._mode = "step"
        self.runner.auto_driving = False  # 确保关闭信号触发
        
        try:
            # 1. 帧开始：重置动作，避免残留
            self.state_manager.reset_actions()
            
            # 2. 注入观测
            if obs:
                self.state_manager.update(obs)
            
            # 3. 同步 tick（不等信号）
            self.runner.tick_once()
            
            # 4. 可选：让步给事件循环，让异步任务推进
            if yield_to_async:
                await asyncio.sleep(0)
            
            # 5. 返回本帧动作
            return self.state_manager.get_actions()
        finally:
            self._mode = "idle"
    
    async def run(
        self, 
        input_data: Optional[Dict[str, Any]] = None,
        reset_tree: bool = True,
        reset_data: bool = False,
        max_ticks: int = None,
        checkpointer = None,
        checkpoint_interval: int = 1,
        thread_id: str = "default_thread"
    ) -> Status:
        """
        任务模式：事件驱动，直到 SUCCESS/FAILURE。
        
        适用于对话机器人、任务规划、离线工作流。
        
        Args:
            input_data: 初始数据，将被 update 到 state
            reset_tree: 是否重置树状态（从根重新决策）
            reset_data: 是否清空黑板（清除历史记忆）
            max_ticks: 最大 tick 数（熔断保护）
            checkpointer: 检查点管理器
            checkpoint_interval: 保存检查点的间隔（每 N 次 tick 保存一次，默认 1）
            thread_id: 会话线程 ID
            
        Returns:
            最终状态 (SUCCESS / FAILURE)
            
        Raises:
            RuntimeError: 如果 step() 正在执行
        """
        if self._mode == "step":
            raise RuntimeError("Cannot run() while step() is active")
        
        self._mode = "run"
        
        try:
            # 1. 可选：逻辑重置
            if reset_tree:
                self.runner.tree.interrupt()
            
            # 2. 可选：数据重置
            if reset_data:
                self.state_manager.initialize()
            
            # 3. 清除残留信号 (在 update 之前，避免误伤 update 产生的新信号)
            self.runner.tick_signal.clear()

            # 4. 注入初始数据
            if input_data:
                self.state_manager.update(input_data)
            
            # 5. 进入事件驱动循环
            return await self.runner.run(
                max_ticks=max_ticks,
                checkpointer=checkpointer,
                checkpoint_interval=checkpoint_interval,
                thread_id=thread_id
            )
        finally:
            self._mode = "idle"
    
    def reset(self, reset_data: bool = True):
        """
        Episode 级重置。
        
        用于 RL 训练的 Episode 切换 或 工作流状态清理。
        
        Args:
            reset_data: 是否清空黑板
                - True: 清空所有状态（RL 训练推荐）
                - False: 仅重置树状态，保留历史（对话推荐）
        """
        # 1. 逻辑重置：打断当前运行，全树 → INVALID
        self.runner.tree.interrupt()
        
        # 2. 可选：数据重置
        if reset_data:
            self.state_manager.initialize()
        
        # 3. 清除信号
        self.runner.tick_signal.clear()
        self.runner.auto_driving = False
        self._mode = "idle"
