"""
ToolNode Demo - Fixed tool node in a workflow-style tree.
"""
import asyncio
from typing import Optional

from pydantic import BaseModel

from btflow import BTAgent, StateManager, Sequence, Status
from btflow.tools import CalculatorTool
from btflow.tools.node import ToolNode


class ToolState(BaseModel):
    expr: str = ""
    result: Optional[str] = None


async def main():
    print("--- 🧩 ToolNode Demo ---")

    # 1) State
    state_manager = StateManager(schema=ToolState)
    state_manager.initialize({"expr": "2+3"})

    # 2) Tool node (fixed workflow)
    calc_node = ToolNode(
        name="Calc",
        tool=CalculatorTool(),
    )
    # Bind ToolNode ports -> state fields
    calc_node._input_bindings = {"input": "state.expr"}
    calc_node._output_bindings = {"output": "state.result"}

    root = Sequence(name="Main", memory=True, children=[calc_node])

    # 3) Run
    agent = BTAgent(root, state_manager)
    status = await agent.run()

    # 4) Verify
    final_state = state_manager.get()
    print(f"Status: {status}")
    print(f"Expr: {final_state.expr} -> Result: {final_state.result}")
    assert status == Status.SUCCESS
    assert final_state.result == "5"


if __name__ == "__main__":
    asyncio.run(main())
