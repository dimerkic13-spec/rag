import json
import unittest

from scripts.check_pilot import ABSTENTION, CASES, evaluate

CONFIG = {"source_url": "https://docs.example.invalid/windows.pdf", "dataset_id": "kb",
          "document_id": "windows", "document": "Windows", "version": "5.0"}


def payload(page):
    citations = [] if page is None else [
        {"document": "Windows", "version": "5.0", "page": page,
         "url": f"{CONFIG['source_url']}#page={page}"}
    ]
    return {
        "answer": json.dumps({"status": "insufficient" if page is None else "answered",
                              "text": ABSTENTION if page is None else "Fixture", "citations": citations}),
        "metadata": {"retriever_resources": [] if page is None else [
            {"dataset_id": "kb", "document_id": "windows", "segment_id": "chunk",
             "content": f"PDF_PAGE={page}\nFixture"},
        ]},
    }


class PilotChecks(unittest.TestCase):
    def test_three_fixture_cases(self):
        for case in CASES:
            with self.subTest(case=case[0]):
                self.assertTrue(evaluate(payload(case[2]), case, CONFIG)["passed"])

    def test_wrong_page_or_other_document_fails(self):
        for field, value in (("content", "PDF_PAGE=8"), ("document_id", "other"),
                             ("content", "PDF_PAGE=7\nPDF_PAGE=8")):
            raw = payload(7)
            raw["metadata"]["retriever_resources"][0][field] = value
            with self.subTest(field=field, value=value):
                self.assertFalse(evaluate(raw, CASES[0], CONFIG)["passed"])

    def test_wrong_link_and_false_abstention_fail(self):
        raw = payload(7)
        raw["answer"] = raw["answer"].replace("#page=7", "#page=8")
        self.assertFalse(evaluate(raw, CASES[0], CONFIG)["passed"])
        raw = payload(None)
        raw["answer"] = json.dumps({"status": "insufficient", "text": "100 рублей", "citations": []})
        self.assertFalse(evaluate(raw, CASES[-1], CONFIG)["passed"])
