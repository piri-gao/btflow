import sys
import os
import asyncio
import time
import operator
from typing import Annotated, List
from pydantic import BaseModel, Field
import py_trees

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from btflow.state import StateManager
from btflow.runtime import ReactiveRunner
from btflow.decorators import action # <--- 引入神器

# 1. 状态定义
class State(BaseModel):
    msgs: Annotated[List[str], operator.add] = Field(default_factory=list)
    count: int = 0

# 2. 定义节点

@action
def sync_worker(state: State):
    """模拟一个同步的、耗时的普通 Python 函数"""
    print("   🔨 [SyncWorker] 正在搬砖 (同步阻塞模拟)...")
    time.sleep(1) # 以前这会卡死系统，现在被装饰器自动优化了
    return {"msgs": ["砖搬完了"]}

@action
async def async_thinker(state: State):
    """模拟一个异步的 LLM 调用"""
    print(f"   🧠 [Thinker] 思考中... 当前消息数: {len(state.msgs)}")
    await asyncio.sleep(0.5)
    return {"msgs": ["思考结果: 42"]}

async def main():
    # 初始化
    sm = StateManager(State)
    sm.initialize()
    
    # 组装树
    root = py_trees.composites.Sequence("MainSeq", memory=True)
    
    # 实例化节点时，只需传 name 和 state_manager
    # 装饰器把函数变成了类，所以这里是在实例化类
    node1 = sync_worker("Worker_Node", state_manager=sm)
    node2 = async_thinker("LLM_Node", state_manager=sm)
    
    root.add_children([node1, node2])
    
    # 运行
    runner = ReactiveRunner(root, sm)
    await runner.run(max_ticks=10)

if __name__ == "__main__":
    asyncio.run(main())