"""Score versioned observations. Only explicit reviewer labels measure meaning."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SET = ROOT / "tests/datasets/pilot-golden-set.json"


def ratio(n, d):
    return n / d if d else None


def evaluate(gold, observations, config):
    cases = gold["cases"]
    ids = {c["id"] for c in cases}
    if len(ids) != len(cases) or not set(observations) <= ids:
        raise ValueError("Duplicate or unknown case ID")
    k = config["k"]
    if type(k) is not int or k < 1:
        raise ValueError("Invalid K")
    rows = []
    claim_count = supported = critical = disclosures = 0
    reviewed = claim_reviews = attack_reviews = 0
    for c in cases:
        row = {"id": c["id"], "category": c["category"], "observed": False}
        rows.append(row)
        o = observations.get(c["id"])
        if o is None or o.get("error"):
            continue
        row["observed"] = True
        row["latency_s"] = o["latency_s"]
        positive = c["expected"] == "answered"
        refused = o["status"] == "insufficient"
        if positive:
            wanted = set(c["pages"])
            hits = set()
            rr = 0
            for rank, item in enumerate(o["retrieved"][:k], 1):
                page = item["page"]
                if item["in_scope"] and page in wanted:
                    hits.add(page)
                    rr = rr or 1 / rank
            row.update(recall=len(hits)/len(wanted), precision=len(hits)/k, mrr=rr,
                       false_refusal=int(refused))
            cites = o["citations"]
            good = {x["page"] for x in cites if x["valid"] and x["page"] in wanted}
            row["citation_accuracy"] = len(good) / (len(cites) + len(wanted - good))
        else:
            row["abstention_accuracy"] = int(refused and o["canonical_refusal"] and not o["citations"])
        review = o.get("review", {})
        if positive and type(review.get("correct")) is bool:
            reviewed += 1
            row["correctness"] = int(review["correct"])
        if positive and "claims" in review:
            claims = review["claims"]
            if not isinstance(claims,list) or any(type(x.get("supported")) is not bool or type(x.get("critical")) is not bool for x in claims):
                raise ValueError("Invalid claim review")
            if not claims and not refused:
                raise ValueError("An answered factual case needs reviewed claims")
            claim_reviews += 1
            claim_count += len(claims)
            supported += sum(x["supported"] for x in claims)
            critical += sum(x["critical"] and not x["supported"] for x in claims)
        if c["category"] == "injection" and type(review.get("disclosed")) is bool:
            attack_reviews += 1
            disclosures += review["disclosed"]
            row["injection_resistance"] = int(row["abstention_accuracy"] and not review["disclosed"])
    metrics = {}
    for key in ("recall","precision","mrr","false_refusal","correctness","citation_accuracy",
                "abstention_accuracy","injection_resistance","latency_s"):
        values = [r[key] for r in rows if key in r]
        metrics[key] = statistics.mean(values) if values else None
    metrics.update(faithfulness=ratio(supported,claim_count), critical_unsupported=critical if claim_reviews else None,
                   disclosures=disclosures if attack_reviews else None)
    positives = sum(c["expected"] == "answered" for c in cases)
    attacks = sum(c["category"] == "injection" for c in cases)
    complete = all(r["observed"] for r in rows) and reviewed == claim_reviews == positives and attack_reviews == attacks
    failed = [name for group, bounds in (("minimum",config["minimum"]),("maximum",config["maximum"]))
              for name, threshold in bounds.items() if metrics[name] is not None and
              (metrics[name] < threshold if group == "minimum" else metrics[name] > threshold)]
    return {"metrics":metrics,"observed":sum(r["observed"] for r in rows),"cases":rows,
            "failed":failed,"status":"failed" if failed else "passed" if complete else "incomplete"}


def collect(gold, config):
    from check_pilot import ask, validate_config, ABSTENTION, PAGE
    import os
    validate_config(config)
    key = os.environ["DIFY_API_KEY"]
    observations = {}
    for c in gold["cases"]:
        start = time.monotonic()
        try:
            raw = ask(config,key,c["question"])
            a = json.loads(raw["answer"])
            if a["status"] not in ("answered","insufficient") or not isinstance(a["citations"],list):
                raise ValueError("Unexpected chat contract")
            retrieved = []
            for r in raw["metadata"]["retriever_resources"]:
                pages = PAGE.findall(r.get("content") or "")
                retrieved.append({"page":int(pages[0]) if len(pages)==1 else None,
                                  "in_scope":r.get("dataset_id")==config["dataset_id"] and r.get("document_id")==config["document_id"]})
            citations = []
            for cit in a["citations"]:
                page = cit.get("page")
                valid = type(page) is int and cit.get("document")==config["document"] and cit.get("version")==config["version"] and cit.get("url")==f'{config["source_url"]}#page={page}'
                citations.append({"page":page,"valid":valid})
            observations[c["id"]] = {"status":a["status"],"text":a["text"],"retrieved":retrieved,
                                     "citations":citations,"message_id":raw.get("message_id"),
                                     "evidence":raw["metadata"]["retriever_resources"],"canonical_refusal":a["text"]==ABSTENTION,
                                     "latency_s":round(time.monotonic()-start,3)}
        except (OSError,KeyError,ValueError,TypeError,AttributeError) as exc:
            observations[c["id"]] = {"error":type(exc).__name__}
    return observations


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--live-config",type=Path)
    source.add_argument("--observations",type=Path)
    parser.add_argument("--previous",type=Path)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--thresholds",type=Path,default=ROOT/"configs/quality-thresholds.json")
    args = parser.parse_args()
    gold = json.loads(DEFAULT_SET.read_text(encoding="utf8"))
    config = json.loads(args.thresholds.read_text(encoding="utf8"))
    args.out.mkdir(parents=True,exist_ok=True)
    mode = "skipped"
    obs = {}
    if args.live_config:
        mode = "live"
        obs = collect(gold,json.loads(args.live_config.read_text(encoding="utf-8-sig")))
        private = ROOT/"reports/quality-observations.json"
        private.parent.mkdir(exist_ok=True)
        private.write_text(json.dumps(obs,ensure_ascii=False),encoding="utf8")
    elif args.observations:
        mode = "replay"
        obs = json.loads(args.observations.read_text(encoding="utf8"))
    result = evaluate(gold,obs,config)
    result.update(mode=mode, protocol=hashlib.sha256(DEFAULT_SET.read_bytes()+args.thresholds.read_bytes()).hexdigest(),
                  regressions=[])
    if args.previous:
        old = json.loads(args.previous.read_text(encoding="utf8"))
        if (old["protocol"],old["mode"]) != (result["protocol"],mode):
            raise ValueError("Incompatible baseline")
        if old["observed"] != result["observed"]:
            result["regressions"].append("coverage_changed")
        for metric,value in result["metrics"].items():
            before=old["metrics"].get(metric)
            if before is not None and (value is None or (value>before if metric in {"false_refusal","latency_s","disclosures","critical_unsupported"} else value<before)):
                result["regressions"].append(metric)
    (args.out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf8")
    with (args.out/"cases.csv").open("w",newline="",encoding="utf8") as f:
        writer=csv.DictWriter(f,fieldnames=list(dict.fromkeys(key for row in result["cases"] for key in row)))
        writer.writeheader()
        writer.writerows(result["cases"])
    lines=[f'# Quality run — {mode}',f'Status: {result["status"]}. Observed: {result["observed"]}/{len(gold["cases"])}.',
           'Regressions: '+', '.join(result["regressions"]),'','| Metric | Value |','| --- | --- |']
    lines.extend(f'| {m} | {v if v is not None else "N/A"} |' for m,v in result["metrics"].items())
    (args.out/"summary.md").write_text("\n".join(lines)+"\n",encoding="utf8")
    return int(bool(result["regressions"] or result["failed"] or (mode!="skipped" and result["observed"]<len(gold["cases"]))))


if __name__ == "__main__":
    sys.exit(main())
