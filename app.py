"""Run the same API locally or in Colab: python app.py --build-index --preload."""

import argparse
import os

import uvicorn

from apps.api.app.app import app


def main():
    parser = argparse.ArgumentParser(description="Run Marjaak AlQanoni API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--build-index", action="store_true")
    parser.add_argument("--preload", action="store_true")
    args = parser.parse_args()
    if args.build_index:
        from apps.api.services.RAG.rag import build_index

        build_index()
    if args.preload:
        os.environ["LLM_PRELOAD"] = "1"
    # A single worker keeps one Qwen model in memory.
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
