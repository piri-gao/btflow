# BTflow 🌊

> **面向 LLM Agent 的事件驱动、状态管理行为树框架。**
>
> 一个专为构建复杂、可中断且具备长期记忆的 AI Agent 而设计的行为树框架。

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-green.svg)]()
[![Status](https://img.shields.io/badge/status-alpha-red)]()

[English](README.md) | [简体中文](README_CN.md)

## 🌟 核心特性

* **⚡ 事件驱动**: 基于 `asyncio.Event` 的响应式内核。告别忙等待和轮询。只有当状态发生变化或任务完成时才会触发 Tick，确保零延迟和高效率。
* **🧠 类型化状态**: 基于 Pydantic 的黑板（Blackboard），支持自动数据验证和变更通知。
* **🔌 零样板代码**: 自动为所有节点注入 `state_manager`。不再需要手动传递参数。
* **🎨 BTflow Studio**: 内置可视化编辑器，直接在浏览器中创建、调试和运行工作流。
* **💾 可恢复性**: 完整的状态持久化支持，允许 Agent 在崩溃或中断后从上一个 Checkpoint 完美恢复。

## 📦 安装

```bash
pip install btflow
```

## 🚀 快速开始 (Studio)

最简单的上手方式是使用可视化 Studio：

```bash
# 启动 Studio UI
btflow-studio
```

浏览器将自动打开 `http://localhost:8000`，你可以立即开始创建你的第一个 Agent。

## 💻 快速开始 (Python API)

### 1. 定义 Agent 状态

```python
from typing import Annotated, List
from pydantic import BaseModel, Field
import operator

class AgentState(BaseModel):
    # 自动追加新消息，而不是覆盖
    messages: Annotated[List[str], operator.add] = Field(default_factory=list)
```

### 2. 构建并运行

```python
import asyncio
from btflow import StateManager, ReactiveRunner, BTAgent, Sequence
from btflow.nodes.llm import GeminiNode

async def main():
    # 1. 初始化状态
    state_manager = StateManager(schema=AgentState)
    state_manager.initialize({"messages": []})

    # 2. 构建行为树
    root = Sequence(name="MainSeq", memory=True)
    # 注意: StateManager 会被自动注入，无需手动传递！
    node1 = GeminiNode(name="Think", model="gemini-1.5-flash")
    root.add_children([node1])

    # 3. 运行 Agent
    runner = ReactiveRunner(root, state_manager)
    agent = BTAgent(runner)
    
    await agent.run(input_data={"messages": ["Hello!"]})

if __name__ == "__main__":
    asyncio.run(main())
```

## 🛠️ 开发指南

如果你想参与贡献或从源码构建：

```bash
# 1. 安装开发依赖
make install

# 2. 运行测试
make test

# 3. 构建发布包 (包含后端和前端资源)
make publish
```

### 目录结构
```text
btflow/
├── btflow/          # 核心框架代码
├── btflow_studio/   # 可视化 Studio (FastAPI + React)
├── examples/        # 使用示例
└── tests/           # 单元测试与集成测试
```

## 📄 License

MIT © 2026 Piri Gao
