"""
Memory Demo - Hybrid memory with keyword + semantic search.
"""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from btflow.memory import Memory, SearchOptions, resolve_embedder


def main():
    embedder = resolve_embedder()
    if embedder is None:
        print("❌ No embedding provider configured. Set GEMINI_API_KEY or OPENAI_API_KEY.")
        return

    memory = Memory(persist_path=".memory/demo.json", embedder=embedder)
    memory.clear()

    memory.add("I like pizza")
    memory.add("Python is a programming language")
    memory.add("The sky is blue")

    print("\nSearch: 'programming'")
    for item in memory.search("programming", options=SearchOptions(k=2, mode="hybrid")):
        print(f"- {item.text}")

    print("\nSearch: 'blue'")
    for item in memory.search("blue", options=SearchOptions(k=2, mode="semantic")):
        print(f"- {item.text}")


if __name__ == "__main__":
    main()
