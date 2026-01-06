"""
BTAgent: 统一接入层
支持 step() 和 run() 双模驱动
"""
from typing import Literal, Dict, Any, Optional
from py_trees.common import Status

from btflow.runtime import ReactiveRunner


class BTAgent:
    """
    BTflow 统一接入层。
    
    封装 ReactiveRunner，提供两种运行模式：
    - step(): 步进模式，用于 RL 训练 / 高频仿真
    - run(): 任务模式，用于对话机器人 / 工作流
    
    Example:
        runner = ReactiveRunner(root, state_manager)
        agent = BTAgent(runner)
        
        # RL 场景
        for _ in range(1000):
            action = await agent.step({"observation": obs})
        
        # 对话场景
        result = await agent.run({"user_input": "你好"})
    """
    
    def __init__(self, runner: ReactiveRunner):
        self.runner = runner
        self.state_manager = runner.state_manager
        self._mode: Literal["idle", "step", "run"] = "idle"
    
    async def step(self, obs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        步进模式：强制同步 tick，返回动作快照。
        
        适用于 RL 训练、高频仿真、实时控制。
        每帧：重置动作 → 注入观测 → tick → 返回动作
        
        Args:
            obs: 观测数据，将被 update 到 state
            
        Returns:
            本帧动作快照（ActionField 标记的字段）
            
        Raises:
            RuntimeError: 如果 run() 正在执行
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
            
            # 4. 返回本帧动作
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
            
            # 3. 注入初始数据
            if input_data:
                self.state_manager.update(input_data)
            
            # 4. 清除残留信号
            self.runner.tick_signal.clear()
            
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
