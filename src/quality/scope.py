"""Metadata boundary for a future retrieval adapter. Principals come from the server."""
from dataclasses import dataclass
from datetime import datetime
import re


@dataclass(frozen=True)
class Page:
    product: str
    product_version: str
    document: str
    document_version: str
    page: int
    section: str
    checksum: str
    indexed_at: datetime
    allowed_groups: frozenset[str]

    def __post_init__(self):
        if not all(isinstance(v, str) and v.strip() for v in
                   (self.product, self.product_version, self.document, self.document_version, self.section)):
            raise ValueError("Missing metadata")
        if type(self.page) is not int or self.page < 1 or not re.fullmatch("[0-9a-f]{64}", self.checksum):
            raise ValueError("Invalid PDF page or SHA-256")
        if self.indexed_at.utcoffset() is None or not isinstance(self.allowed_groups, frozenset):
            raise ValueError("Expected UTC offset and immutable ACL")


def visible(page, product, version, approved, groups):
    key = (page.product, page.product_version, page.document, page.document_version)
    return (page.product == product and page.product_version == version
            and approved.get(key) == page.checksum and bool(page.allowed_groups & groups))
