"""
Trace Demo - subscribe to btflow trace events.
"""
import asyncio
from typing import Optional

from pydantic import BaseModel

from btflow import BTAgent, StateManager, Sequence, Status, trace_subscribe
from btflow.tools import CalculatorTool
from btflow.tools.ext.node import ToolNode


class TraceState(BaseModel):
    expr: str = ""
    result: Optional[str] = None


async def main():
    print("--- 📡 Trace Demo ---")

    # 1) Subscribe to trace events
    def on_event(event: str, data: dict):
        print(f"[TRACE] {event}: {data}")

    trace_subscribe(on_event)

    # 2) Build a simple tool workflow
    state_manager = StateManager(schema=TraceState)
    state_manager.initialize({"expr": "6*7"})

    calc_node = ToolNode(
        name="Calc",
        tool=CalculatorTool(),
        input_map={"input": "expr"},
        output_key="result",
    )
    root = Sequence(name="Main", memory=True, children=[calc_node])

    # 3) Run
    agent = BTAgent(root, state_manager)
    status = await agent.run()

    final_state = state_manager.get()
    print(f"Status: {status} Result: {final_state.result}")
    assert status == Status.SUCCESS
    assert final_state.result == "42"


if __name__ == "__main__":
    asyncio.run(main())
