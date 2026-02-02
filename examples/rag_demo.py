"""
RAG Demo - minimal retrieval + answer generation using btflow Memory.

Database: SQLite file (no external dependencies).
"""
import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from btflow.memory import Memory, SearchOptions
from btflow.memory.store import SQLiteStore


DOCS = [
    {
        "source": "doc:btflow_overview",
        "text": (
            "BTFlow is a lightweight agent framework that uses behavior trees. "
            "It focuses on modular design, composable nodes, and pluggable tools."
        ),
    },
    {
        "source": "doc:memory_design",
        "text": (
            "Memory in BTFlow uses a minimal triad: Record, Store, Retriever. "
            "The Memory facade manages ingestion and search, and supports hybrid retrieval."
        ),
    },
    {
        "source": "doc:rag_notes",
        "text": (
            "A minimal RAG pipeline can be built by ingesting text chunks into Memory, "
            "retrieving top-k chunks with hybrid search, and constructing a prompt with context."
        ),
    },
]


def build_memory(db_path: str) -> Memory:
    memory = Memory(store=SQLiteStore(db_path))
    if len(memory) == 0:
        for doc in DOCS:
            memory.ingest_text(
                doc["text"],
                chunk_size=300,
                overlap=40,
                metadata={"source": doc["source"]},
            )
    return memory


def build_prompt(question: str, context_items):
    context_lines = []
    for idx, item in enumerate(context_items, start=1):
        source = item.metadata.get("source", "unknown")
        context_lines.append(f"[{idx}] ({source}) {item.text}")
    context = "\n".join(context_lines) if context_lines else "No context."
    return (
        "Use the context to answer the question. If the context is insufficient, say so.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}\n"
        "Answer:"
    )


async def main():
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
    base_url = os.getenv("BASE_URL")
    if not api_key:
        print("❌ Error: OPENAI_API_KEY (or API_KEY) not set in .env")
        return

    from btflow.llm import LLMProvider
    
    # Automatically choose provider based on env vars
    try:
        provider = LLMProvider.default(api_key=api_key, base_url=base_url)
        print(f"🤖 Using LLM Provider: {type(provider).__name__}")
    except Exception as e:
        print(f"❌ Error initializing LLM provider: {e}")
        return

    db_path = ".memory/rag_demo.sqlite"
    memory = build_memory(db_path)
    print(f"📚 Memory DB: {db_path} (records: {len(memory)})")

    question = "What is the minimal RAG pipeline in BTFlow?"
    results = memory.search(question, options=SearchOptions(k=3, mode="hybrid"))
    prompt = build_prompt(question, results)

    response = await provider.generate_text(
        prompt=prompt,
        model=os.getenv("MODEL", "gemini-2.5-flash"),
        temperature=0.2,
    )

    print("\n🔎 Retrieved Context:")
    for item in results:
        src = item.metadata.get("source", "unknown")
        print(f"- [{src}] {item.text}")

    print("\n🤖 Answer:")
    print(response.content)


if __name__ == "__main__":
    asyncio.run(main())
