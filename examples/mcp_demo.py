import asyncio
import os
import shutil
from btflow.protocols.mcp import MCPServerConfig, MCPClient
from btflow.nodes import ReActLLMNode, ToolExecutor, IsFinalAnswer
from btflow.core.state import StateManager
from btflow.messages import Message
from py_trees.common import Status
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

class ReActState(BaseModel):
    messages: List[Message] = Field(default_factory=list)
    task: str = ""
    tools_desc: str = ""
    tools_schema: List[Dict[str, Any]] = Field(default_factory=list)
    final_answer: Optional[str] = None
    round: int = 0


async def main():
    # 1. Check dependencies
    npx_path = shutil.which("npx")
    if not npx_path:
        print("❌ 'npx' not found. Please install Node.js/npm to run this demo.")
        return

    # 2. Configure MCP Server (Filesystem Server)
    # This server provides tools like 'read_file', 'write_file', 'list_directory'
    # MCPClient uses fastmcp v2 under the hood and supports stdio/http/sse.
    # This demo uses stdio via npx.
    current_dir = os.getcwd()
    config = MCPServerConfig(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", current_dir],
        env=os.environ.copy()
    )

    print(f"🔌 Connecting to MCP Filesystem Server on: {current_dir}...")
    
    try:
        async with MCPClient(config) as client:
            # 3. Load MCP Tools (and optional prompts)
            tools = await client.as_tools()
            print(f"🛠️  Loaded {len(tools)} tools from MCP:")
            for t in tools:
                print(f"   - {t.name}: {t.description[:50]}...")
            prompts = await client.list_prompts()
            if prompts:
                print(f"🧾 Loaded {len(prompts)} prompts from MCP:")
                for p in prompts:
                    print(f"   - {p.name}: {getattr(p, 'description', '')[:50]}...")

            # 4. Create ReAct Agent
            state_manager = StateManager(ReActState)
            
            # Create a simple test file
            with open("test_mcp.txt", "w") as f:
                f.write("Hello from BTflow + MCP Integration!")

            # Agent Nodes
            llm_node = ReActLLMNode(
                model="gemini-2.0-flash-exp", # Faster model
                tools_description="", # Will be updated dynamically by executor 
            )
            llm_node.bind_state_manager(state_manager)

            tool_node = ToolExecutor(tools=tools) # Inject MCP tools
            tool_node.bind_state_manager(state_manager)

            check_node = IsFinalAnswer()
            check_node.state_manager = state_manager # Manual bind for simple behaviour

            # Behavior Tree vs manual loop:
            # This demo uses a manual loop for clarity instead of running a full Runner.
            # 5. Run it
            question = "Read the file 'test_mcp.txt' and tell me what it says."
            print(f"\n🤖 User: {question}")
            
            # Initialize task
            state_manager.update({"task": question})
            
            # Because ReactiveRunner runs forever until stopped, we'll run it for a bit
            # or rely on IsFinalAnswer to stop? 
            # btflow logic: nodes return RUNNING/SUCCESS/FAILURE.
            # We need a condition to stop the runner. Runner stops if root returns SUCCESS/FAILURE (if configured).
            # Repeat returns SUCCESS only if child returns SUCCESS (and num_failures work).
            # If child is Sequence, it returns SUCCESS if all children SUCCESS.
            # LLM -> SUCCESS. Tool -> SUCCESS. IsFinalAnswer -> SUCCESS (if found).
            # So if Final Answer found, Step returns SUCCESS. Repeat loops again?
            # py_trees Repeat: repeats child returns SUCCESS or FAILURE. 
            
            # Let's just do a manual tick loop for clarity in this demo
            print("🚀 Starting Agent Loop...")
            llm_node.initialise() 
            tool_node.initialise() # Register tools
            
            # Update tool descriptions manually once since we aren't using the full Runner's setup lifecycle here perfectly
            tool_node._update_tools_state() 
            
            for i in range(5):
                print(f"\n--- Step {i+1} ---")
                
                # 1. LLM
                await llm_node.update_async()
                
                # 2. Check Final
                if check_node.update() == Status.SUCCESS:
                    ans = state_manager.get().final_answer
                    print(f"\n✅ Final Answer: {ans}")
                    break
                
                # 3. Tool
                await tool_node.update_async()
                
            # Cleanup
            if os.path.exists("test_mcp.txt"):
                os.remove("test_mcp.txt")

    except Exception as e:
        print(f"\n💥 Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
