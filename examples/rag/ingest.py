"""
RAG Ingestion Script - build or extend a SQLite memory store.

Usage:
  python examples/rag/ingest.py --path docs/handbook.md
  python examples/rag/ingest.py --path docs --recursive --ext .md --ext .txt
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Iterable, List

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
load_dotenv()

from btflow.memory import Memory, resolve_embedder
from btflow.memory.store import SQLiteStore


def iter_files(paths: List[str], exts: List[str], recursive: bool) -> Iterable[Path]:
    seen = set()
    for p in paths:
        path = Path(p).expanduser().resolve()
        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            for f in path.glob(pattern):
                if not f.is_file():
                    continue
                if exts and f.suffix.lower() not in exts:
                    continue
                if f in seen:
                    continue
                seen.add(f)
                yield f
        else:
            if path.is_file():
                if exts and path.suffix.lower() not in exts:
                    continue
                if path not in seen:
                    seen.add(path)
                    yield path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest documents into BTFlow Memory")
    parser.add_argument(
        "--path",
        action="append",
        required=True,
        help="File or directory path to ingest (can be used multiple times)",
    )
    parser.add_argument(
        "--db",
        default=".memory/rag.sqlite",
        help="SQLite DB path (default: .memory/rag.sqlite)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="Chunk size in characters (default: 500)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=50,
        help="Chunk overlap in characters (default: 50)",
    )
    parser.add_argument(
        "--ext",
        action="append",
        default=[".md", ".txt"],
        help="File extensions to include (default: .md .txt)",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing memory before ingesting",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="File encoding (default: utf-8)",
    )
    parser.add_argument(
        "--provider",
        choices=["gemini", "openai"],
        default=None,
        help="Force embedding provider (gemini/openai)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    db_path = Path(args.db).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    preference = [args.provider] if args.provider else None
    embedder = resolve_embedder(preference=preference)
    if embedder is None:
        print("❌ No embedding provider configured. Set GEMINI_API_KEY or OPENAI_API_KEY.")
        return

    memory = Memory(store=SQLiteStore(str(db_path)), embedder=embedder)
    if args.clear:
        memory.clear()

    exts = [e.lower() if e.startswith(".") else f".{e.lower()}" for e in (args.ext or [])]

    files = list(iter_files(args.path, exts, args.recursive))
    if not files:
        print("❌ No files matched. Check --path and --ext.")
        return

    total_chunks = 0
    for f in files:
        ids = memory.ingest_file(
            str(f),
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            metadata={"source": str(f)},
            encoding=args.encoding,
        )
        total_chunks += len(ids)
        print(f"✅ Ingested {f} ({len(ids)} chunks)")

    memory.save()
    print(f"\n📚 DB: {db_path}")
    print(f"📦 Files: {len(files)} | Chunks: {total_chunks} | Records: {len(memory)}")


if __name__ == "__main__":
    main()
