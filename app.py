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
    # Reserve the port before allocating GPU memory. A second Colab cell must
    # fail here instead of loading another model while an older server responds.
    config = uvicorn.Config(app, host=args.host, port=args.port, workers=1)
    with config.bind_socket() as listener:
        if args.build_index:
            from apps.api.services.RAG.rag import build_index

            build_index()
        if args.preload:
            os.environ["LLM_PRELOAD"] = "1"
        # Use the reserved socket, with one worker and one model per process.
        uvicorn.Server(config).run(sockets=[listener])


if __name__ == "__main__":
    main()
