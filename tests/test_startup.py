"""Detect stale Colab listeners before allocating another model on the GPU."""

import os
import socket
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as launcher
from apps.api.app.app import app
from apps.api.services.RAG import rag


class StartupTests(unittest.TestCase):
    def test_occupied_port_exits_before_indexing_or_model_startup(self):
        with socket.socket() as existing:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                existing.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            existing.bind(("127.0.0.1", 0))
            existing.listen()
            port = existing.getsockname()[1]
            args = ["app.py", "--host", "127.0.0.1", "--port", str(port),
                    "--build-index", "--preload"]
            with patch("sys.argv", args), patch.object(rag, "build_index") as build, \
                 patch.object(launcher.uvicorn, "Server") as server:
                with self.assertRaises(SystemExit) as result:
                    launcher.main()
                self.assertNotEqual(result.exception.code, 0)
                build.assert_not_called()
                server.assert_not_called()

    def test_health_identifies_the_process_serving_the_request(self):
        result = TestClient(app).get("/health")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["pid"], os.getpid())


if __name__ == "__main__":
    unittest.main()
