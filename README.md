# BTflow 🌊

> **Async-first, State-managed Behavior Tree Framework for LLM Agents.**
>
> A behavior tree framework designed for building complex, interruptible, and long-term memory AI agents (v1.0 Stable).

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.9+-green.svg)
![Status](https://img.shields.io/badge/status-production--ready-orange)

[English](README.md) | [简体中文](README_CN.md)

## 🌟 Key Features

* **🧠 State Management**: Pydantic-based typed blackboard supporting `Reducer` (e.g., append-only messages) to prevent data pollution.
* **⚡ Async-First**: Native `asyncio` support in the kernel, perfectly matching the streaming/async nature of LLM APIs.
* **💾 Persistence & Memory**: Supports "Resumable Execution". System state and execution progress can be perfectly restored from the latest checkpoint after a crash or interruption.
* **🛡️ Idempotency Guard**: Unique mechanism to prevent expensive LLM calls from being re-executed when restoring from a checkpoint.
* **🌳 Visualization**: Built-in tools to export complex agent logic as ASCII trees or PNG flowcharts.

## 📦 Installation

```bash
# Recommended using poetry or pip
pip install -e .

```

## 🚀 Quick Start

### 1. Define State Schema

```python
import operator
from typing import Annotated, List
from pydantic import BaseModel, Field

class AgentState(BaseModel):
    # Automatically append new messages instead of overwriting
    messages: Annotated[List[str], operator.add] = Field(default_factory=list)

```

### 2. Build the Tree

```python
import py_trees
from btflow.state import StateManager
from btflow.nodes.mock import MockLLMAction

# Initialize State
state_manager = StateManager(schema=AgentState)
state_manager.initialize({"messages": []})

# Define Flow: Sequence
root = py_trees.composites.Sequence(name="MainSeq", memory=True)
node1 = MockLLMAction(name="Think", state_manager=state_manager)
node2 = MockLLMAction(name="Reply", state_manager=state_manager)
root.add_children([node1, node2])

```

### 3. Run

```python
import asyncio
from btflow.runtime import ReactiveRunner

async def main():
    runner = ReactiveRunner(root, state_manager)
    # Start runner (supports auto-checkpointing)
    await runner.run(max_ticks=10)

if __name__ == "__main__":
    asyncio.run(main())

```

## 🏗️ Architecture

```text
btflow/
├── core.py         # [Kernel] Async base class for nodes (AsyncBehaviour)
├── state.py        # [Memory] Typed blackboard with Reducers
├── runtime.py      # [Engine] Async runner with recovery & pointer fix
├── persistence.py  # [Storage] JSONL checkpoint system
└── nodes/          # [Actions] Concrete business nodes (LLM, Tool...)

```

## 🧪 Testing & Validation

The project includes complete unit and integration tests.

```bash
# Run unit tests (Core logic)
python -m unittest discover tests

# Run persistence integration tests (Simulate crash & recovery)
python examples/test_persistence.py

# Generate behavior tree visualization
python examples/visualize_tree.py

```

## 🗓️ Roadmap

* [x] **v1.0**: Core Kernel (Core/Runtime/State/Persistence) ✅
* [ ] **v1.1**: Integration with Real OpenAI/DeepSeek APIs
* [ ] **v1.2**: Trace Visualization (Mermaid/Gantt)
* [ ] **v1.3**: Human-in-the-loop (Manual Approval Node)

## 📄 License

MIT © 2025 Piri Gao