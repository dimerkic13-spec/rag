import tempfile
import unittest
from pathlib import Path

from scripts.check_registry import check_registry


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "examples/pilot_catalog.csv"


class RegistryTest(unittest.TestCase):
    def test_existing_example(self):
        self.assertEqual(check_registry(ROOT / "examples/documents.csv"), 1)

    def test_catalog(self):
        self.assertEqual(check_registry(CATALOG), 2)

    def test_invalid_catalog(self):
        original = CATALOG.read_text(encoding="utf-8")
        variants = [
            (original.replace(",pilot,", ",expansion,"), "ровно один"),
            (original.replace(",expansion,", ",pilot,"), "ровно один"),
            (original.replace(",expansion,", ",other,"), "неизвестное"),
            (original.replace(",17\n", ",0\n"), "положительным"),
            (original.replace("04 91 09", "04 92 01"), "уже указан"),
            (original.replace(",ЖТЯИ.00101-03", ",../ЖТЯИ.00101-03"), "без пути"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "registry.csv"
            for content, message in variants:
                with self.subTest(message=message):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, message):
                        check_registry(path)
