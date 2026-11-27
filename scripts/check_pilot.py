"""Run the three Windows manual pilot scenarios against a published Dify chat."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ABSTENTION = "В документации недостаточно сведений для ответа."
CASES = (
    ("text", "Что нужно сделать после завершения установки дистрибутива КриптоПро CSP?", 7),
    ("table", "Поддерживает ли Chrome двусторонний TLS с клиентским ГОСТ-сертификатом при использовании свойства shadow?", 88),
    ("abstention", "Какова стоимость продления лицензии в 2030 году?", None),
)
PAGE = re.compile(r"^PDF_PAGE=([1-9][0-9]*)\s*$", re.MULTILINE)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_config(config):
    fields = ("base_url", "source_url", "dataset_id", "document_id", "document", "version")
    missing = [k for k in fields if not isinstance(config.get(k), str) or not config[k].strip()]
    if missing:
        raise ValueError("Заполните поля: " + ", ".join(missing))
    for key in ("base_url", "source_url"):
        url = urlsplit(config[key])
        local_http = url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
        if (url.scheme != "https" and not local_http) or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError(f"{key}: укажите HTTPS URL без учётных данных, параметров и фрагмента.")


def ask(config, key, question):
    request = Request(
        config["base_url"].rstrip("/") + "/chat-messages",
        data=json.dumps({
            "query": question, "inputs": {}, "response_mode": "blocking",
            "user": "rag-windows-pilot", "conversation_id": "",
        }).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with build_opener(NoRedirect()).open(request, timeout=100) as response:
        return json.load(response)


def evaluate(raw, case, config):
    case_id, question, page = case
    answer = json.loads(raw["answer"])
    resources = raw["metadata"]["retriever_resources"]
    status, text, citations = answer["status"], answer["text"], answer["citations"]
    if not isinstance(text, str) or not isinstance(citations, list) or not isinstance(resources, list):
        raise ValueError("Неверный формат ответа или retriever_resources.")
    evidence = []
    for resource in resources:
        evidence.append({
            "dataset_id": resource.get("dataset_id"),
            "document_id": resource.get("document_id"),
            "segment_id": resource.get("segment_id"),
            "pages": [int(n) for n in PAGE.findall(resource.get("content") or "")],
        })
    isolated = all((r["dataset_id"], r["document_id"]) ==
                   (config["dataset_id"], config["document_id"]) for r in evidence)
    if page is None:
        checks = {"abstention": status == "insufficient" and text == ABSTENTION,
                  "no_citations": citations == []}
    else:
        citation = {"document": config["document"], "version": config["version"],
                    "page": page, "url": f'{config["source_url"]}#page={page}'}
        checks = {
            "answered": status == "answered" and bool(text.strip()) and text != ABSTENTION,
            "exact_citation": len(citations) == 1 and citations[0] == citation
                              and type(citations[0]["page"]) is int,
            "retrieved_page": any(r["pages"] == [page] and r["segment_id"] for r in evidence),
        }
    checks["pilot_only"] = isolated
    return {"id": case_id, "question": question, "expected_page": page,
            "checks": checks, "passed": all(checks.values()), "answer": answer,
            "evidence": evidence, "message_id": raw.get("message_id"),
            "manual_content_review": "required" if page is not None else "not_required"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--preflight", action="store_true", help="Check local settings without contacting Dify")
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8-sig"))
        validate_config(config)
        key = os.environ.get("DIFY_API_KEY", "").strip()
        if not key:
            raise ValueError("Передайте DIFY_API_KEY через окружение.")
        if args.preflight:
            if not os.environ.get("DIFY_KNOWLEDGE_API_KEY", "").strip():
                raise ValueError("Передайте DIFY_KNOWLEDGE_API_KEY через окружение для индексации.")
            print("Local configuration present; remote permissions unverified.")
            return 0
        if args.report is None:
            parser.error("--report is required for a live run")
        results = []
        for case in CASES:
            try:
                result = evaluate(ask(config, key, case[1]), case, config)
            except HTTPError as error:
                result = {"id": case[0], "passed": False, "error": f"HTTP {error.code}"}
            except (URLError, TimeoutError, ValueError, KeyError, TypeError, AttributeError):
                result = {"id": case[0], "passed": False, "error": "Сбой соединения или формата ответа"}
            results.append(result)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        report = {"mode": "dify_api", "automated_checks_passed": all(r["passed"] for r in results),
                  "semantic_review_complete": False, "cases": results}
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({r["id"]: r["passed"] for r in results}))
        return 0 if report["automated_checks_passed"] else 1
    except (ValueError, OSError, AttributeError) as error:
        print(f"Ошибка запуска: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
