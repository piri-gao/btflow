# BTflow 🌊

> **Event-driven, State-managed Behavior Tree Framework for LLM Agents.**
>
> 专为构建复杂、可中断、长程记忆的 AI Agent 而设计的行为树框架 (v0.1.0 Alpha)。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-green.svg)
![Status](https://img.shields.io/badge/status-alpha-red)

[English](README.md) | [简体中文](README_CN.md)

## 🌟 核心特性 (Key Features)

* **⚡ 事件驱动 (Event-Driven)**: 基于 `asyncio.Event` 的响应式内核。告别死轮询 (Busy Waiting)，仅在状态变更或任务完成时唤醒 Tick，实现零延迟响应与极高资源利用率。
* **🧠 状态管理 (State Management)**: 基于 Pydantic 的强类型黑板，支持 `Reducer` (如增量追加消息) 与变更通知，拒绝数据污染。
* **💾 持久化与记忆 (Persistence)**: 支持“断点续传”。程序崩溃或中断后，可从最近的 Checkpoint 完美恢复状态和执行进度。
* **🛡️ 僵尸防御 (Idempotency Guard)**: 独创的幂等性守卫机制，防止从存档恢复时重复触发已完成的昂贵 LLM 调用。
* **🌳 可视化 (Visualization)**: 内置工具可将复杂的 Agent 逻辑导出为 ASCII 树或 PNG 流程图。

## 📦 安装 (Installation)

```bash
# 推荐使用 poetry 或 pip
pip install -e .

```

## 🚀 快速开始 (Quick Start)

### 1. 定义状态 (Schema)

```python
import operator
from typing import Annotated, List
from pydantic import BaseModel, Field

class AgentState(BaseModel):
    # 自动追加新消息，而不是覆盖
    messages: Annotated[List[str], operator.add] = Field(default_factory=list)

```

### 2. 构建行为树 (Tree)

```python
import py_trees
from btflow.state import StateManager
from btflow.nodes.mock import MockLLMAction

# 初始化状态
state_manager = StateManager(schema=AgentState)
state_manager.initialize({"messages": []})

# 定义流程：顺序执行
root = py_trees.composites.Sequence(name="MainSeq", memory=True)
node1 = MockLLMAction(name="Think", state_manager=state_manager)
node2 = MockLLMAction(name="Reply", state_manager=state_manager)
root.add_children([node1, node2])

```

### 3. 运行 (Run)

```python
import asyncio
from btflow.runtime import ReactiveRunner

async def main():
    runner = ReactiveRunner(root, state_manager)
    # 启动运行器 (事件驱动模式，自动休眠与唤醒)
    await runner.run(max_ticks=10)

if __name__ == "__main__":
    asyncio.run(main())

```

## 🏗️ 架构概览 (Architecture)

```text
btflow/
├── core.py         # [Kernel] 事件驱动的异步节点基类 (AsyncBehaviour)
├── state.py        # [Memory] 支持观察者模式的类型化黑板
├── runtime.py      # [Engine] 基于 Signal 的响应式运行器
├── persistence.py  # [Storage] JSONL 存档系统
└── nodes/          # [Actions] 具体业务节点 (LLM, Tool...)

```

## 🧪 测试与验证

项目包含完整的单元测试和集成测试。

```bash
# 运行单元测试 (核心逻辑)
python -m unittest discover tests

# 运行持久化集成测试 (模拟崩溃恢复)
python tests/test_persistence.py

# 生成行为树结构图
python tests/visualize_tree.py

```

## 🗓️ Roadmap

* [x] **v0.1**: 事件驱动内核 (Event-Driven Kernel) ✅
* [ ] **v0.2**: 真实能力接入 (OpenAI/DeepSeek Node, Tools, Human-in-loop)
* [ ] **v0.3**: 工程化 (Redis Persistence, FastAPI Service, Docker)
* [ ] **v1.0**: 生产环境发布 (Production Ready)

## 📄 License

MIT © 2025 Piri Gao

