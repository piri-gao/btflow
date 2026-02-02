# BTflow 🌊

> **Event-driven, State-managed Behavior Tree Framework for LLM Agents.**
>
> A behavior tree framework designed for building complex, interruptible, and long-term memory AI agents.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-green.svg)]()
[![Status](https://img.shields.io/badge/status-alpha-red)]()

[English](README.md) | [简体中文](README_CN.md)

## 🌟 Key Features

* **⚡ Event-Driven**: Reactive kernel based on `asyncio.Event`. No busy waiting or polling. Ticks are triggered only by state changes or task completion.
* **🧠 Typed State**: Pydantic-based blackboard with automatic validation and change notifications.
* **🔌 Zero Boilerplate**: Auto-injected `state_manager` for all nodes. No more manually passing arguments.
* **🎨 BTflow Studio**: Included visual editor to create, debug, and run workflows directly from your browser.
* **💾 Resumable**: Complete state persistence allows agents to crash and resume exactly where they left off.

## 📦 Installation

```bash
pip install btflow
```

## 🚀 Quick Start (Studio)

The easiest way to get started is using the visual studio:

```bash
# Start the Studio UI
btflow-studio
```

Open your browser at `http://localhost:8000` to create your first agent.

## 💻 Quick Start (Python API)

### 1. Define Agent State

```python
from typing import Annotated, List
from pydantic import BaseModel, Field
import operator

class AgentState(BaseModel):
    # Automatically append new messages instead of overwriting
    messages: Annotated[List[str], operator.add] = Field(default_factory=list)
```

### 2. Build and Run

```python
import asyncio
from btflow import StateManager, BTAgent, Sequence
from btflow.nodes import LLMNode
from btflow.llm import LLMProvider

async def main():
    # 1. Initialize State
    state_manager = StateManager(schema=AgentState)
    state_manager.initialize({"messages": []})

    # 2. Build Tree
    root = Sequence(name="MainSeq", memory=True)
    # Note: StateManager is auto-injected!
    provider = LLMProvider.default(preference=["gemini", "openai"])
    node1 = LLMNode(name="Think", provider=provider, model="gemini-2.5-flash")
    root.add_children([node1])

    # 3. Run Agent
    agent = BTAgent(root, state_manager)
    
    await agent.run(input_data={"messages": ["Hello!"]})

if __name__ == "__main__":
    asyncio.run(main())
```

## 🛠️ Development

If you want to contribute or build from source:

```bash
# 1. Install dependencies
make install

# 2. Run Tests
make test

# 3. Build & Publish (Backend + Frontend)
make publish
```

### Directory Structure
```text
btflow/
├── btflow/          # Core Framework
├── btflow_studio/   # Visual Studio (FastAPI + React)
├── examples/        # Usage Examples
└── tests/           # Unit & Integration Tests
```

## 📄 License

MIT © 2026 Piri Gao
