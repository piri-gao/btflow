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

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), \"../..\")))
load_dotenv()

from btflow.memory import Memory, SearchOptions
from btflow.memory.store import SQLiteStore
from btflow.llm import LLMProvider


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
        "--k",
        type=int,
        default=3,
        help="Top-k chunks to retrieve (default: 3)",
    )
    parser.add_argument(
        "--mode",
        default="hybrid",
        choices=["hybrid", "semantic", "keyword"],
        help="Retrieval mode (default: hybrid)",
    )
    return parser.parse_args()


def build_prompt(question: str, context_items) -> str:
    if not context_items:
        context = "No context."
    else:
        lines = []
        for i, item in enumerate(context_items, 1):
            source = item.metadata.get("source", "unknown") if item.metadata else "unknown"
            lines.append(f"[{i}] ({source}) {item.text}")
        context = "\n".join(lines)

    return (
        "Use the context to answer the question. If the context is insufficient, say so.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}\n"
        "Answer:"
    )


async def main() -> None:
    args = parse_args()

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
    base_url = os.getenv("BASE_URL")
    if not api_key:
        print("❌ Error: OPENAI_API_KEY (or API_KEY) not set in .env")
        return

    try:
        provider = LLMProvider.default(preference=["gemini", "openai"], base_url=base_url)
        print(f"🤖 Using LLM Provider: {type(provider).__name__}")
    except Exception as e:
        print(f"❌ Error initializing LLM provider: {e}")
        return

    db_path = Path(args.db).expanduser().resolve()
    if not db_path.exists():
        print(f"❌ DB not found: {db_path}")
        print("   Run: python examples/rag/ingest.py --path <docs>")
        return

    memory = Memory(store=SQLiteStore(str(db_path)))
    if len(memory) == 0:
        print("❌ DB is empty. Run ingest first.")
        return

    question = args.question
    results = memory.search(question, options=SearchOptions(k=args.k, mode=args.mode))
    prompt = build_prompt(question, results)

    response = await provider.generate_text(
        prompt=prompt,
        model=os.getenv("MODEL", "gemini-2.5-flash"),
        temperature=0.2,
    )

    print("\n🔎 Retrieved Context:")
    if not results:
        print("(none)")
    else:
        for item in results:
            src = item.metadata.get("source", "unknown") if item.metadata else "unknown"
            print(f"- [{src}] {item.text}")

    print("\n🤖 Answer:")
    print(response.content)


if __name__ == "__main__":
    asyncio.run(main())
