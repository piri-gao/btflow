"""
Memory Agent Demo - Agent with long-term memory.

This demo shows how to create a ReAct agent with persistent memory.
The agent can store and retrieve information across conversations.
"""
import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from btflow.patterns.react import ReActAgent
from btflow.memory import Memory
from btflow.llm import LLMProvider


async def main():
    # 1. Setup LLM Provider
    base_url = os.getenv("BASE_URL")

    try:
        # Prefer Gemini to avoid key mismatch issues
        provider = LLMProvider.default(preference=["gemini", "openai"], base_url=base_url)
    except RuntimeError as e:
        print(str(e))
        return

    # 2. Create persistent memory (saved to file)
    memory = Memory(persist_path=".memory/agent_memory.json")
    print(f"📚 Memory loaded: {len(memory)} items")

    # 3. Create agent with memory (tools auto-injected)
    agent = ReActAgent.create(
        model="gemini-2.0-flash",
        provider=provider,
        memory=memory,
        max_rounds=10,
    )

    print("🤖 Agent with memory ready!")
    print("Commands: 'quit' to exit, 'clear' to clear memory\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        if user_input.lower() == "clear":
            memory.clear()
            print("🗑️ Memory cleared!")
            continue

        # Run agent
        await agent.run(input_data={"task": user_input, "messages": []}, reset_tree=True, reset_data=False)

        # Get result
        state = agent.state_manager.get()
        print(f"\n🤖 Agent: {state.final_answer}\n")
        print(f"(Memory items: {len(memory)})\n")


if __name__ == "__main__":
    asyncio.run(main())
