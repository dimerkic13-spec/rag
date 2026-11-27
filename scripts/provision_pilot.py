"""Create or resume a private Dify pilot KB and verify its page-marked segments."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from check_pilot import NoRedirect, PAGE

NAME = "rag004-windows-5.0-R4-KC1"
DOCUMENT = "ЖТЯИ.00101-04 92 01. Windows"
SEP = "\nRAG004_PAGE_BREAK\n"


def request(path, body=None):
    base = os.environ["DIFY_BASE_URL"].rstrip("/")
    url = urlsplit(base)
    if not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Invalid Dify URL")
    if url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"}):
        raise ValueError("Use HTTPS or loopback")
    headers = {"Authorization": "Bearer " + os.environ["DIFY_KNOWLEDGE_API_KEY"], "Content-Type": "application/json"}
    data = None if body is None else json.dumps(body).encode()
    with build_opener(NoRedirect()).open(Request(base + path, data=data, headers=headers), timeout=120) as response:
        return json.load(response)


def listed(api, path):
    rows = []
    for page in range(1, 1001):
        result = api(f"{path}?page={page}&limit=100")
        rows.extend(result["data"])
        if not result["has_more"]:
            return rows
    raise ValueError("Pagination exceeded")


def provision(parts, provider, model, api=request, wait=time.sleep):
    matches = [PAGE.findall(p) for p in parts]
    if len(parts) != 363 or any(len(m) != 1 for m in matches) or {int(m[0]) for m in matches} != set(range(1, 201)):
        raise ValueError("Expected 363 segments for pages 1–200")
    datasets = [r for r in listed(api, "/datasets") if r["name"] == NAME]
    if len(datasets) > 1:
        raise ValueError("Ambiguous pilot dataset")
    kb = datasets[0] if datasets else api("/datasets", {"name": NAME, "permission": "only_me",
        "indexing_technique": "high_quality", "embedding_model_provider": provider, "embedding_model": model})
    if datasets and (kb.get("embedding_model_provider"), kb.get("embedding_model")) != (provider, model):
        raise ValueError("Existing dataset provider/model mismatch")
    path = "/datasets/" + kb["id"]
    docs = listed(api, path + "/documents")
    if docs and (len(docs) != 1 or docs[0]["name"] != DOCUMENT):
        raise ValueError("Dataset already contains another document")
    doc = docs[0] if docs else api(path + "/document/create-by-text", {
        "name": DOCUMENT, "text": SEP.join(parts), "indexing_technique": "high_quality",
        "process_rule": {"mode": "custom", "rules": {"pre_processing_rules": [],
                        "segmentation": {"separator": SEP, "max_tokens": 1000, "chunk_overlap": 0}}}
    })["document"]
    for _ in range(120):
        rows = listed(api, path + "/documents/" + doc["id"] + "/segments")
        if any(r.get("status") == "error" for r in rows):
            raise ValueError("Indexing failed")
        if len(rows) == len(parts) and all(r.get("enabled") and r["status"] == "completed" for r in rows):
            if Counter(r["content"] for r in rows) != Counter(parts):
                raise ValueError("Indexed content differs from reviewed segments")
            return {"dataset_id": kb["id"], "document_id": doc["id"], "verified_segments": len(parts)}
        wait(5)
    raise ValueError("Index not complete within 10 minutes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batches", type=Path)
    parser.add_argument("--config-out", type=Path, help="Write new pilot JSON using PILOT_PDF_URL")
    args = parser.parse_args()
    try:
        parts = [s["content"] for p in sorted(args.batches.glob("segments-*.json"))
                 for s in json.loads(p.read_text(encoding="utf-8"))["segments"]]
        if args.config_out:
            from check_pilot import validate_config
            template = Path(__file__).resolve().parents[1] / "configs/pilot.example.json"
            config = json.loads(template.read_text(encoding="utf-8"))
            config.update(base_url=os.environ["DIFY_BASE_URL"], source_url=os.environ["PILOT_PDF_URL"],
                          dataset_id="pending", document_id="pending")
            validate_config(config)
            if args.config_out.exists():
                raise ValueError("Output configuration already exists")
        result = provision(parts, os.environ["EMBEDDING_PROVIDER"], os.environ["EMBEDDING_MODEL"])
        if args.config_out:
            args.config_out.parent.mkdir(parents=True, exist_ok=True)
            config.update(dataset_id=result["dataset_id"], document_id=result["document_id"])
            with args.config_out.open("x", encoding="utf-8") as out:
                json.dump(config, out, ensure_ascii=False, indent=2)
        print(json.dumps(result))
    except (OSError, ValueError, KeyError) as exc:
        sys.exit(f"Pilot provisioning failed ({type(exc).__name__}). Check configuration and indexing status.")
