import asyncio
import random
from typing import List
from py_trees.common import Status
from btflow.core import AsyncBehaviour
from btflow.state import StateManager

class MockLLMAction(AsyncBehaviour):
    """
    模拟一个 LLM 调用节点。
    它会从 State 读取 messages，模拟网络延迟，然后追加一条回复。
    """
    def __init__(self, name: str, state_manager: StateManager):
        super().__init__(name)
        self.state = state_manager

    async def update_async(self) -> Status:
        # 1. 读取状态 (Read State)
        current_state = self.state.get()
        messages = current_state.messages or []
        
        # 简单打印一下上下文，方便调试
        print(f"   🤖 [{self.name}] 看到上下文: {len(messages)} 条消息")
        last_msg = messages[-1] if messages else "Nothing"

        # 2. 模拟 LLM 思考 (Simulate Latency)
        # 关键：这里 await，会让出 CPU 给 Runner，Runner 可以去处理其他任务
        think_time = random.uniform(0.5, 1.5)
        print(f"   ⏳ [{self.name}] 正在思考... (预计 {think_time:.2f}s)")
        await asyncio.sleep(think_time)

        # 3. 生成回复 (Mock Generation)
        response_text = f"AI回复: 我收到了你说 '{last_msg}'"
        
        # 4. 写入状态 (Write State - Append)
        # 注意：我们在 StateManager 里配置了 messages 是 append 模式
        self.state.update({
            "messages": [response_text], 
            "step_count": 1 # 自动累加
        })
        
        print(f"   ✅ [{self.name}] 回复生成完毕: {response_text}")
        return Status.SUCCESS