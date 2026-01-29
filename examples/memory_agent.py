"""
Memory Agent Demo - Agent with long-term memory.

This demo shows how to create a ReAct agent with persistent memory.
The agent can store and retrieve information across conversations.
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from btflow.patterns.react import ReActAgent
from btflow.llm.providers.openai import OpenAIProvider
from btflow.memory import VectorMemory, create_memory_tools


async def main():
    # 1. Setup LLM Provider
    api_key = os.getenv("API_KEY")
    base_url = os.getenv("BASE_URL")
    if not api_key:
        print("Please set API_KEY in .env")
        return
    
    provider = OpenAIProvider(api_key=api_key, base_url=base_url)
    
    # 2. Create persistent memory (saved to file)
    memory = VectorMemory(persist_path=".memory/agent_memory.json")
    print(f"📚 Memory loaded: {len(memory)} items")
    
    # 3. Create memory tools
    memory_tools = create_memory_tools(memory)
    
    # 4. Create agent with memory tools
    agent = ReActAgent.create(
        model="gemini-2.0-flash",
        provider=provider,
        tools=memory_tools,
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
        
        # Reset agent state for new task
        agent.state_manager.initialize({"task": user_input, "messages": []})
        
        # Run agent
        await agent.runner.run()
        
        # Get result
        state = agent.state_manager.get()
        print(f"\n🤖 Agent: {state.final_answer}\n")
        print(f"(Memory items: {len(memory)})\n")


if __name__ == "__main__":
    asyncio.run(main())
