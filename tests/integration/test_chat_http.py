"""Exercise real blocking HTTP transport against synthetic Dify replies."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys
from threading import Thread
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.check_pilot import CASES, ask, evaluate
sys.path.insert(0, str(ROOT / "tests/unit"))
from test_pilot import CONFIG, payload


class ChatHTTPTest(unittest.TestCase):
    def test_three_independent_requests(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                seen.append((self.path, self.headers.get("Authorization"), request))
                case = next(case for case in CASES if case[1] == request["query"])
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(payload(case[2])).encode())

        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            config = {**CONFIG, "base_url": f"http://127.0.0.1:{server.server_port}/v1"}
            try:
                for case in CASES:
                    raw = ask(config, "fixture", case[1])
                    self.assertTrue(evaluate(raw, case, config)["passed"])
            finally:
                server.shutdown()
                thread.join()
        self.assertEqual(len(seen), 3)
        for path, auth, body in seen:
            self.assertEqual(path, "/v1/chat-messages")
            self.assertEqual(auth, "Bearer fixture")
            self.assertEqual(body["conversation_id"], "")
            self.assertEqual(body["response_mode"], "blocking")
