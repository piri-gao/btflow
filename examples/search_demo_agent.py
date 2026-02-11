"""
Search Agent Demo - uses DuckDuckGo to answer real-time questions.
"""
import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv() # Load from .env file

from btflow.patterns.react import ReActAgent
from btflow.llm import LLMProvider
from btflow.tools import DuckDuckGoSearchTool

async def main():
    # 1. Setup tools
    search_tool = DuckDuckGoSearchTool()
    
    # 2. Setup LLM Provider (OpenAI-compatible proxy for Gemini)
    base_url = os.getenv("BASE_URL")
    # Prefer Gemini to avoid key mismatch issues if OpenAI package is missing
    provider = LLMProvider.default(preference=["gemini", "openai"], base_url=base_url)
    
    # 3. Create the ReAct agent tree with date context
    today = datetime.now().strftime("%Y-%m-%d")
    system_prompt = f"""You are a helpful assistant with access to web search.
Today's date is {today}. For any time-sensitive questions (sports results, current events, etc.),
ALWAYS use the search tool first to get accurate, up-to-date information."""
    
    agent = ReActAgent.create(
        model="gemini-2.5-flash", # Use a fast model
        provider=provider,
        tools=[search_tool],
        max_rounds=10,
        stream=False, # Disabled for proxy compatibility
        system_prompt=system_prompt
    )
    
    # 5. Define the task
    task = "Who won the Australian Open men's singles in 2025? If it hasn't happened or finished yet, report the current status."
    input_data = {
        "task": task,
        "messages": []
    }
    
    # 6. Run the agent
    print(f"\n🚀 [Agent Task]: {task}\n")
    print("-" * 50)
    
    await agent.run(input_data=input_data)
    
    # 7. Final Results
    final_state = agent.state_manager.get()
    print("-" * 50)
    print(f"\n🎯 [Final Answer]:\n{final_state.final_answer}")

if __name__ == "__main__":
    asyncio.run(main())
