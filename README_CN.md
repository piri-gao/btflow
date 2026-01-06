# BTflow 🌊

> **Event-driven, State-managed Behavior Tree Framework for LLM Agents.**
>
> 专为构建复杂、可中断、长程记忆的 AI Agent 而设计的行为树框架 (v0.2.0 Alpha)。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-green.svg)
![Status](https://img.shields.io/badge/status-alpha-red)

[English](README.md) | [简体中文](README_CN.md)

## 🌟 核心特性

* **⚡ 事件驱动**: 基于 `asyncio.Event` 的响应式内核，仅在状态变更或任务完成时唤醒 Tick。
* **🎮 双模驱动**: `BTAgent` 支持 `step()` 模式（RL 训练）和 `run()` 模式（对话机器人）。
* **🧠 状态管理**: Pydantic 强类型黑板，支持 `Reducer`（增量追加）和 `ActionField`（每帧重置）。
* **💾 持久化**: 支持断点续传，可配置检查点间隔，避免高频场景磁盘压力。
* **🌳 可视化**: 导出 ASCII 树或 PNG 流程图。

## 📦 安装

```bash
pip install -e .
```

## 🚀 快速开始

### 1. 定义状态

```python
import operator
from typing import Annotated, List
from pydantic import BaseModel, Field

class AgentState(BaseModel):
    messages: Annotated[List[str], operator.add] = Field(default_factory=list)
```

### 2. 构建行为树

```python
import py_trees
from btflow.state import StateManager
from btflow.runtime import ReactiveRunner
from btflow.agent import BTAgent
from btflow.nodes.mock import MockLLMAction

# 初始化
state_manager = StateManager(schema=AgentState)
state_manager.initialize({"messages": []})

# 构建树
root = py_trees.composites.Sequence(name="MainSeq", memory=True)
node1 = MockLLMAction(name="Think", state_manager=state_manager)
node2 = MockLLMAction(name="Reply", state_manager=state_manager)
root.add_children([node1, node2])

# 创建 BTAgent
runner = ReactiveRunner(root, state_manager)
agent = BTAgent(runner)
```

### 3. 运行

```python
import asyncio

async def main():
    # 对话模式
    await agent.run(
        input_data={"messages": ["User: 你好！"]},
        max_ticks=10
    )

if __name__ == "__main__":
    asyncio.run(main())
```

### 4. RL 训练模式

```python
from btflow.state import ActionField

class RLState(BaseModel):
    observation: dict = {}
    speed: Annotated[float, ActionField()] = 0.0  # 每帧自动重置

# 训练循环
for episode in range(1000):
    obs = env.reset()
    agent.reset(reset_data=True)
    
    while not done:
        action = await agent.step(obs)
        obs, reward, done, _ = env.step(action)
```

## 🏗️ 架构概览

```text
btflow/
├── agent.py        # [Gate] 双模驱动统一入口 (BTAgent)
├── core.py         # [Kernel] 异步节点基类 (AsyncBehaviour)
├── state.py        # [Memory] 类型化黑板 (StateManager, ActionField)
├── runtime.py      # [Engine] 响应式运行器 (ReactiveRunner)
├── persistence.py  # [Storage] JSONL 存档
└── nodes/          # [Actions] 业务节点
```

## 🧪 测试

```bash
# 运行所有测试
python -m unittest discover tests

# 运行 examples
cd examples && python mock_demo.py
cd examples && python rl_step_demo.py
```

## 📄 License

MIT © 2025 Piri Gao
