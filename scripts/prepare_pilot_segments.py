"""Create Dify segment batches from the reviewed Windows PDF text export."""
import argparse
import json
from pathlib import Path
import re

FOOTER = re.compile(r"^\s*Страница\s+(\d+)\s+из\s+200\s*$", re.MULTILINE)
CODE = "ЖТЯИ.00101-04 92 01"


def prepare(extracted):
    pages = extracted.removesuffix("\f").split("\f")
    if len(pages) != 200 or CODE not in pages[0] or "5.0 R4 KC1" not in pages[0]:
        raise ValueError("Ожидается проверенное 200-страничное руководство Windows.")
    segments = []
    for number, page in enumerate(pages, 1):
        if number > 1:
            if FOOTER.findall(page) != [str(number)]:
                raise ValueError(f"Не совпадает номер страницы {number}.")
            page = FOOTER.sub("", page)
            page = "\n".join(line for line in page.splitlines() if not line.lstrip().startswith(CODE))
        remaining = page.strip()
        if not remaining:
            raise ValueError(f"Нет текста на странице {number}.")
        while remaining:
            end = len(remaining)
            if end > 750:
                end = remaining.rfind("\n", 375, 750)
                if end == -1:
                    end = remaining.rfind(" ", 375, 750)
                if end == -1:
                    end = 750
            segments.append({"content": f"PDF_PAGE={number}\n{remaining[:end].strip()}"})
            remaining = remaining[end:].lstrip("\n ")
    # One row transcribed during visual comparison with table 2 (RAG-002).
    segments.append({"content": (
        "PDF_PAGE=88\nТаблица 2. Свойство shadow. Chrome. Двусторонний TLS "
        "с клиентским ГОСТ-сертификатом: не поддерживается (−)."
    )})
    return segments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", type=Path, help="Output of pdftotext -layout -enc UTF-8")
    parser.add_argument("output", type=Path, help="New local directory for upload batches")
    args = parser.parse_args()
    try:
        segments = prepare(args.text.read_text(encoding="utf-8-sig"))
        args.output.mkdir(parents=True)
        for index in range(0, len(segments), 20):
            path = args.output / f"segments-{index // 20 + 1:03}.json"
            path.write_text(json.dumps({"segments": segments[index:index + 20]},
                                       ensure_ascii=False), encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.exit(1, f"Segment preparation failed: {error}\n")
    print(f"Prepared {len(segments)} segments for 200 PDF pages.")


if __name__ == "__main__":
    main()
