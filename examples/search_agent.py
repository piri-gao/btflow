"""
Search Agent Demo - uses DuckDuckGo to answer real-time questions.
"""
import asyncio
import os
from dotenv import load_dotenv
load_dotenv() # Load from .env file

from btflow.core.state import StateManager
from btflow.core.runtime import ReactiveRunner
from btflow.patterns.react import ReActState, ReActAgent
from btflow.llm import LLMProvider
from btflow.tools import DuckDuckGoSearchTool
from btflow.core.logging import logger

async def main():
    # 1. Setup tools
    search_tool = DuckDuckGoSearchTool()
    
    # 2. Setup LLM Provider (OpenAI-compatible proxy for Gemini)
    api_key = os.getenv("API_KEY")
    base_url = os.getenv("BASE_URL")
    if not api_key:
        print("Please set API_KEY environment variable in .env.")
        return
        
    provider = LLMProvider.default(api_key=api_key, base_url=base_url)
    
    # 3. Create the ReAct agent tree
    # This agent wrapping the tree and state_manager
    agent = ReActAgent.create(
        model="gemini-2.0-flash", # Use a fast model
        provider=provider,
        tools=[search_tool],
        max_rounds=10,
        stream=False # Disabled for proxy compatibility
    )
    
    # 4. Access internal components for demo control
    runner = agent.runner
    state_manager = agent.state_manager
    
    # 5. Define the task
    task = "Who won the Australian Open men's singles in 2025? If it hasn't happened or finished yet, report the current status."
    state_manager.initialize({
        "task": task,
        "messages": []
    })
    
    # 6. Run the agent
    print(f"\n🚀 [Agent Task]: {task}\n")
    print("-" * 50)
    
    # We can subscribe to state changes to show streaming output
    def on_state_change():
        state = state_manager.get()
        # You could print streaming_output here if you want real-time jumpy text,
        # but for a CLI demo, we'll let it finish or use trace events.
        pass
    
    state_manager.subscribe(on_state_change)
    
    await runner.run()
    
    # 7. Final Results
    final_state = state_manager.get()
    print("-" * 50)
    print(f"\n🎯 [Final Answer]:\n{final_state.final_answer}")

if __name__ == "__main__":
    asyncio.run(main())
