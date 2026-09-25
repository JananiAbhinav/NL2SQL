from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import Catalog
from .retrieval import HybridRetriever


def main() -> None:
    parser = argparse.ArgumentParser(prog="queryops")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="run retrieval against the bundled example catalog")
    retrieve = sub.add_parser("retrieve", help="retrieve schema context for a question")
    retrieve.add_argument("question")
    retrieve.add_argument("--catalog", default="examples/catalog.json")
    retrieve.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    catalog_path = Path(getattr(args, "catalog", "examples/catalog.json"))
    catalog = Catalog.from_dict(json.loads(catalog_path.read_text()))
    retriever = HybridRetriever(catalog)
    question = "show monthly revenue by region" if args.command == "demo" else args.question
    for hit in retriever.retrieve(question, top_k=getattr(args, "top_k", 5)):
        print(f"{hit.object.qualified_name}\t{hit.score:.3f}\t{hit.object.description}")


if __name__ == "__main__":
    main()
