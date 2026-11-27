"""Проверка заполнения реестра документов для пилота."""

import argparse
import csv
from pathlib import Path

FIELDS = ["product", "version", "title", "filename"]


def check_registry(path):
    seen = set()
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source, strict=True)
        if next(reader, None) != FIELDS:
            raise ValueError("Ожидается заголовок " + ",".join(FIELDS))
        for row in reader:
            values = [value.strip() for value in row]
            if len(values) != len(FIELDS) or not all(values):
                raise ValueError(f"Строка {reader.line_num}: заполните все четыре поля")
            product, version, _, filename = values
            if Path(filename).suffix.lower() != ".pdf":
                raise ValueError(f"Строка {reader.line_num}: ожидается имя PDF-файла")
            key = (product, version, filename)
            if key in seen:
                raise ValueError(f"Строка {reader.line_num}: документ уже указан")
            seen.add(key)
    if not seen:
        raise ValueError("Добавьте хотя бы один документ")
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
