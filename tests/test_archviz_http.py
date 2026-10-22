"""Exercise the real loopback HTTP boundary without external services or jobs."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from archviz_server import StudioHTTPServer, StudioService


class ArchvizHTTPBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="archviz-http-qa-")
        self.root = Path(self.temp.name)
        self.registry = self.root / "registry.json"
        self.service = StudioService(self.registry)
        self.server = StudioHTTPServer(("127.0.0.1", 0), self.service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown()
        self.server.server_close()
        self.service.shutdown()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, route, data=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            body = None if data is None else json.dumps(data).encode()
            conn.request(method, route, body=body, headers=headers or {})
            response = conn.getresponse()
            raw = response.read()
            return response.status, json.loads(raw)
        finally:
            conn.close()

    def test_health_state_and_bootstrap_use_same_real_service_without_creating_project(self):
        status, health = self.request("GET", "/api/health")
        self.assertEqual(200, status)
        self.assertEqual("archviz-studio", health["service"])
        status, bootstrap = self.request("GET", "/api/bootstrap")
        self.assertEqual(200, status)
        self.assertTrue(bootstrap["token"])
        status, state = self.request("GET", "/api/state")
        self.assertEqual(200, status)
        self.assertIsNone(state["project"])
        self.assertNotIn("token", state)
        self.assertFalse(self.registry.exists())

    def test_missing_token_cannot_create_project_or_open_native_picker(self):
        payload = {"name": "forged", "work_dir": str(self.root / "forged"),
                   "input_dirs": [], "output_dir": str(self.root / "output")}
        status, _ = self.request("POST", "/api/project/create", payload)
        self.assertEqual(403, status)
        status, _ = self.request("GET", "/api/pick?kind=folder")
        self.assertEqual(403, status)
        self.assertFalse((self.root / "forged").exists())
        self.assertFalse(self.registry.exists())

    def test_cross_origin_and_unrecognized_host_fail_even_with_a_valid_token(self):
        _, bootstrap = self.request("GET", "/api/bootstrap")
        headers = {"X-Studio-Token": bootstrap["token"], "Origin": "https://unrelated.invalid"}
        status, _ = self.request("POST", "/api/project/create", {}, headers)
        self.assertEqual(403, status)
        status, _ = self.request("GET", "/api/state", headers={"Host": "unrelated.invalid"})
        self.assertEqual(403, status)
        self.assertFalse(self.registry.exists())


if __name__ == "__main__":
    unittest.main()
