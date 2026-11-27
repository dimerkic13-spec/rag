"""Проверка заполнения реестра документов для пилота."""

import argparse
import csv
from pathlib import Path

FIELDS = ["product", "version", "title", "filename"]
CATALOG_FIELDS = [*FIELDS, "document_code", "scope", "pages"]


def check_registry(path):
    seen = set()
    pilot_count = 0
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source, strict=True)
        header = next(reader, None)
        if header not in (FIELDS, CATALOG_FIELDS):
            raise ValueError("Ожидается учебный или расширенный заголовок реестра")
        for row in reader:
            values = [value.strip() for value in row]
            if len(values) != len(header) or not all(values):
                raise ValueError(f"Строка {reader.line_num}: заполните все поля")
            product, version, _, filename = values[:4]
            if Path(filename).suffix.lower() != ".pdf":
                raise ValueError(f"Строка {reader.line_num}: ожидается имя PDF-файла")
            key = (product, version, filename)
            if header == CATALOG_FIELDS:
                document_code, scope, pages = values[4:]
                if "/" in filename or "\\" in filename:
                    raise ValueError(f"Строка {reader.line_num}: ожидается имя файла без пути")
                if scope not in {"pilot", "expansion"}:
                    raise ValueError(f"Строка {reader.line_num}: неизвестное назначение документа")
                if not pages.isascii() or not pages.isdecimal() or not pages.lstrip("0"):
                    raise ValueError(f"Строка {reader.line_num}: число страниц должно быть положительным целым")
                pilot_count += scope == "pilot"
                key = (product.casefold(), version.casefold(), " ".join(document_code.casefold().split()))
            if key in seen:
                raise ValueError(f"Строка {reader.line_num}: документ уже указан")
            seen.add(key)
    if not seen:
        raise ValueError("Добавьте хотя бы один документ")
    if header == CATALOG_FIELDS and pilot_count != 1:
        raise ValueError("Расширенный реестр должен содержать ровно один пилотный документ")
    return len(seen)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path, help="Путь к CSV-реестру")
    args = parser.parse_args()
    try:
        count = check_registry(args.registry)
    except (ValueError, OSError, csv.Error) as error:
        parser.exit(1, f"Ошибка реестра: {error}\n")
    print(f"Реестр проверен. Записей: {count}")
