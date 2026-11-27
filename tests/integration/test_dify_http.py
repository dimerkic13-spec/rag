"""HTTP contract test. No document, model or production credential is used."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys
from threading import Thread
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from provision_pilot import SEP, provision


class DifyHTTPTest(unittest.TestCase):
    def test_create_index_and_resume(self):
        parts = [f"PDF_PAGE={i % 200 + 1}\nfixture {i}" for i in range(363)]
        state = {"kb": [], "docs": [], "segments": []}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, value):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(value).encode())

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/datasets":
                    state["kb"].append(dict(body, id="kb"))
                    self.reply(state["kb"][0])
                elif self.path == "/datasets/kb/document/create-by-text":
                    state["docs"].append({"id": "pdf", "name": body["name"]})
                    state["segments"] = [dict(content=p, enabled=True, status="completed") for p in body["text"].split(SEP)]
                    self.reply({"document": state["docs"][0]})
                else:
                    self.send_error(404)

            def do_GET(self):
                from urllib.parse import urlsplit, parse_qs
                url = urlsplit(self.path)
                rows = {"/datasets": state["kb"], "/datasets/kb/documents": state["docs"],
                        "/datasets/kb/documents/pdf/segments": state["segments"]}[url.path]
                start = (int(parse_qs(url.query)["page"][0]) - 1) * 100
                self.reply({"data": rows[start:start+100], "has_more": start + 100 < len(rows)})

        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with patch.dict(os.environ, DIFY_BASE_URL=f"http://127.0.0.1:{server.server_port}",
                                DIFY_KNOWLEDGE_API_KEY="fixture"):
                    for _ in range(2):
                        self.assertEqual(provision(parts, "fixture", "fixture")["verified_segments"], 363)
                    state["segments"][0]["content"] = "wrong page"
                    with self.assertRaisesRegex(ValueError, "differs"):
                        provision(parts, "fixture", "fixture")
                self.assertEqual(len(state["docs"]), 1)
            finally:
                server.shutdown()
                thread.join()
