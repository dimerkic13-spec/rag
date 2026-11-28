import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from scripts.rag_quality import DEFAULT_SET, ROOT, evaluate
from src.quality.scope import Page, visible


class Quality(unittest.TestCase):
    def setUp(self):
        self.gold = json.loads(DEFAULT_SET.read_text(encoding="utf8"))
        self.config = json.loads((ROOT/"configs/quality-thresholds.json").read_text())

    def test_counts_and_sources(self):
        from collections import Counter
        cases = self.gold["cases"]
        self.assertEqual(Counter(c["category"] for c in cases), dict(fact=15, procedure=10, table=5, multi=5,
                                                                       paraphrase=5, absent=5, injection=5))
        self.assertEqual(len({c["question"] for c in cases}), 50)
        for c in cases:
            self.assertEqual(bool(c["pages"]), c["expected"] == "answered")
            self.assertTrue(all(1 <= page <= 200 for page in c["pages"]))

    def test_no_observations(self):
        r = evaluate(self.gold, {}, self.config)
        self.assertEqual(r["status"], "incomplete")
        self.assertIsNone(r["metrics"]["correctness"])

    def test_rank_duplicate_and_wrong_scope(self):
        case = self.gold["cases"][0]
        o = dict(status="answered",latency_s=.1,retrieved=[
            dict(page=2,in_scope=False),dict(page=2,in_scope=True),dict(page=2,in_scope=True)],
            citations=[dict(page=2,valid=True)], review={"claims":[{"critical":True,"supported":False}]})
        r = evaluate(self.gold,{case["id"]:o},self.config)
        self.assertEqual((r["metrics"]["mrr"],r["metrics"]["precision"],r["metrics"]["recall"]),(.5,.2,1))
        self.assertEqual(r["status"], "failed")
        self.assertIsNone(r["metrics"]["correctness"])

    def test_acl_version_and_document_identity(self):
        p = Page("a","1","guide","v1",1,"intro","a"*64,datetime.now(timezone.utc),frozenset({"staff"}))
        registry = {("a","1","guide","v1"):p.checksum}
        self.assertTrue(visible(p,"a","1",registry,{"staff"}))
        for product,version,groups in [("b","1",{"staff"}),("c","1",{"staff"}),("a","2",{"staff"}),("a","1",set())]:
            self.assertFalse(visible(p,product,version,registry,groups))
        self.assertFalse(visible(replace(p,document_version="v2"),"a","1",registry,{"staff"}))
        self.assertFalse(visible(replace(p,checksum="b"*64),"a","1",registry,{"staff"}))

    def test_complete_review_and_disclosure_gate(self):
        observations = {}
        for c in self.gold["cases"]:
            positive = c["expected"] == "answered"
            observations[c["id"]] = {
                "latency_s": 0.2, "status": c["expected"], "canonical_refusal": not positive,
                "retrieved": [{"page":p, "in_scope":True} for p in c["pages"]],
                "citations": [{"page":p, "valid":True} for p in c["pages"]],
                "review": {"correct":True, "claims":[{"supported":True,"critical":False}]}
                          if positive else {"disclosed":False},
            }
        self.assertEqual(evaluate(self.gold,observations,self.config)["status"],"passed")
        attack = next(c["id"] for c in self.gold["cases"] if c["category"]=="injection")
        observations[attack]["review"] = {"disclosed":True}
        result = evaluate(self.gold,observations,self.config)
        self.assertIn("disclosures",result["failed"])
        self.assertEqual(result["metrics"]["injection_resistance"],0.8)
