"""
RAG Demo - retrieval + answer generation using BTFlow Memory.

Usage:
  python examples/rag/rag_demo.py --db .memory/rag.sqlite --question "..."
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
load_dotenv()

from btflow.memory import Memory, resolve_embedder
from btflow.memory.store import SQLiteStore
from btflow.llm import LLMProvider
from btflow.patterns.react import ReActAgent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BTFlow RAG demo")
    parser.add_argument(
        "--db",
        default=".memory/rag.sqlite",
        help="SQLite DB path (default: .memory/rag.sqlite)",
    )
    parser.add_argument(
        "--question",
        default="What is BTFlow and how does it use memory?",
        help="Question to ask",
    )
    parser.add_argument(
        "--provider",
        choices=["gemini", "openai"],
        default=None,
        help="Force embedding provider (gemini/openai)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # 1. Setup Provider (Relaxed check, support --provider)
    preference = [args.provider] if args.provider else ["gemini", "openai"]
    base_url = os.getenv("BASE_URL")
    
    try:
        provider = LLMProvider.default(preference=preference, base_url=base_url)
        print(f"🤖 Using LLM Provider: {type(provider).__name__}")
    except Exception as e:
        print(f"❌ Error initializing LLM provider: {e}")
        print("   Please set GEMINI_API_KEY or OPENAI_API_KEY.")
        return

    db_path = Path(args.db).expanduser().resolve()
    if not db_path.exists():
        print(f"❌ DB not found: {db_path}")
        print("   Run: python examples/rag/ingest.py --path <docs>")
        return

    # Embedder also follows preference
    embedder = resolve_embedder(preference=preference)
    if embedder is None:
        print("❌ No embedding provider configured.")
        return

    # Initialize Memory
    memory = Memory(store=SQLiteStore(str(db_path)), embedder=embedder)
    if len(memory) == 0:
        print("❌ DB is empty. Run ingest first.")
        return

    print("🧠 Memory loaded. Creating ReAct Agent...")

    from btflow.memory.tools import MemorySearchTool

    # Create ReAct Agent with Memory
    # We disable auto_memory_tools to avoid adding MemoryAddTool (read-only mode)
    # We pass memory=None to DISABLE Implicit RAG (context injection) so we rely ONLY on the tool.
    agent = ReActAgent.create(
        provider=provider,
        memory=None, # Disable implicit context injection
        tools=[MemorySearchTool(memory)],
        model=os.getenv("MODEL", "gemini-2.5-flash"),
        auto_memory_tools=False,
        # system_prompt="You are a helpful assistant with access to a knowledge base.",
    )

    from btflow.messages import human

    question = args.question
    print(f"\nQuestion: {question}\n")

    # Run Agent (agent.run returns Status, not state)
    await agent.run({"messages": [human(question)]})
    state = agent.state_manager.get()

    print("\n" + "="*50)
    print(f"🤖 Final Answer: {state.final_answer}")
    print("="*50)

    # Optional: Inspect tool usage
    print("\n🔍 Trace:")
    for msg in state.messages:
        if msg.role == "tool":
            print(f"  🔧 Tool Output: {msg.content[:200]}..." if len(msg.content) > 200 else f"  🔧 Tool Output: {msg.content}")
        elif msg.role == "assistant":
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                 print(f"  💭 Thought/Call: {msg.content} -> {msg.tool_calls}")
            else:
                 print(f"  💭 Thought: {msg.content}")

if __name__ == "__main__":
    asyncio.run(main())
