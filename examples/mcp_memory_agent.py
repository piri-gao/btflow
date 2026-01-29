"""
MCP Memory Agent Demo - Uses Memory MCP server for persistent storage.

This demo shows how to connect a ReAct agent to an MCP server,
giving the agent the ability to store and retrieve memories.

Prerequisites:
    npm install -g @anthropic-ai/mcp-server-memory
    # or use npx (will auto-install)
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from btflow.patterns.react import ReActAgent
from btflow.llm.providers.openai import OpenAIProvider
from btflow.protocols.mcp import MCPClient
from btflow.core.logging import logger


async def main():
    # 1. Setup LLM Provider
    api_key = os.getenv("API_KEY")
    base_url = os.getenv("BASE_URL")
    if not api_key:
        print("Please set API_KEY in .env")
        return
    
    provider = OpenAIProvider(api_key=api_key, base_url=base_url)
    
    # 2. Connect to Memory MCP Server
    # Uses npx to auto-install and run the server
    # Package: @modelcontextprotocol/server-memory
    mcp_client = MCPClient(
        server_source=["npx", "-y", "@modelcontextprotocol/server-memory"]
    )
    
    try:
        # 3. Get tools from MCP server
        print("🔌 Connecting to Memory MCP server...")
        mcp_tools = await mcp_client.as_tools()
        
        print(f"✅ Found {len(mcp_tools)} MCP tools:")
        for tool in mcp_tools:
            print(f"   - {tool.name}: {tool.description[:60]}...")
        
        # 4. Create ReAct agent with MCP tools
        agent = ReActAgent.create(
            model="gemini-2.0-flash",
            provider=provider,
            tools=mcp_tools,
            max_rounds=10,
        )
        
        runner = agent.runner
        state_manager = agent.state_manager
        
        # 5. First task: Store some memories
        task1 = "Please store the following facts in memory: 1) My name is Alice 2) I like Python programming 3) My favorite color is blue"
        
        print(f"\n🚀 Task 1: {task1}\n")
        print("-" * 50)
        
        state_manager.initialize({"task": task1, "messages": []})
        await runner.run()
        
        final_state = state_manager.get()
        print(f"\n🎯 Result: {final_state.final_answer}")
        
        # 6. Second task: Retrieve memories
        # Reset agent state but keep MCP server connection (memories persist)
        # Use read_graph or search for "Alice" to find stored entities
        task2 = "Please read the knowledge graph and tell me all the facts you know about Alice."
        
        print(f"\n🚀 Task 2: {task2}\n")
        print("-" * 50)
        
        # Create a new agent instance with same MCP tools
        agent2 = ReActAgent.create(
            model="gemini-2.0-flash",
            provider=provider,
            tools=mcp_tools,
            max_rounds=10,
        )
        
        agent2.state_manager.initialize({"task": task2, "messages": []})
        await agent2.runner.run()
        
        final_state2 = agent2.state_manager.get()
        print(f"\n🎯 Result: {final_state2.final_answer}")
        
    finally:
        # 7. Cleanup: Close MCP connection
        await mcp_client.close()
        print("\n👋 MCP connection closed.")
        # Give subprocess time to terminate cleanly
        await asyncio.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(main())
