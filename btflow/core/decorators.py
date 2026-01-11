import inspect
import asyncio
from typing import Callable, Any, Dict, Type
from py_trees.common import Status
from btflow.core.behaviour import AsyncBehaviour
from btflow.core.state import StateManager
from btflow.core.logging import logger

def action(func: Callable):
    """
    [语法糖] 将普通函数转换为 btflow 节点。
    
    函数签名要求: 
      def my_func(state: MyState) -> dict: ...
    
    支持:
      - 同步函数 (自动放入线程池运行，不会卡死 Loop)
      - 异步函数 (async def)
    """
    
    # 动态创建一个子类
    class FunctionNode(AsyncBehaviour):
        def __init__(self, name: str, state_manager: StateManager):
            super().__init__(name)
            self.state_manager = state_manager
            
            # 自动绑定函数名作为节点名（如果未指定）
            if name == func.__name__:
                self.name = name

        async def update_async(self) -> Status:
            try:
                # 1. 自动读取状态
                current_state = self.state_manager.get()
                
                # 2. 调用用户函数
                # 判断用户写的是不是 async def
                if inspect.iscoroutinefunction(func):
                    updates = await func(current_state)
                else:
                    # 关键优化：如果是同步函数，自动丢到线程池跑
                    # 这样用户随便写 time.sleep() 也不会卡死整个 Agent
                    updates = await asyncio.to_thread(func, current_state)
                
                # 3. 自动更新状态
                if isinstance(updates, dict):
                    self.state_manager.update(updates)
                    # 只有返回了数据才打印，避免刷屏
                    logger.debug("   ⚡ [{}] Action finished. Updates: {}", self.name, list(updates.keys()))
                elif updates is None:
                    # 允许函数不返回任何东西（只做副作用）
                    pass
                else:
                    raise ValueError(f"Action must return a dict or None, got {type(updates)}")

                return Status.SUCCESS

            except Exception as e:
                logger.error("   🔥 [{}] Action failed: {}", self.name, e)
                import traceback
                traceback.print_exc()
                self.feedback_message = str(e)
                return Status.FAILURE

    # 修改类名，方便调试时看
    FunctionNode.__name__ = f"Action_{func.__name__}"
    return FunctionNode