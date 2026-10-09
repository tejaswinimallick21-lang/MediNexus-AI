"""
Cursor pagination (?limit=&cursor=) for list endpoints. Cursors are opaque to clients.
"""

import base64
from dataclasses import dataclass
from typing import Generic, List, Optional, TypeVar

from fastapi import Query
from pydantic import BaseModel

from backend.app.core.errors import APIError

T = TypeVar("T")

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


class Page(BaseModel, Generic[T]):
    items: List[T]
    next_cursor: Optional[str] = None


@dataclass(frozen=True)
class PageParams:
    limit: int = DEFAULT_LIMIT
    offset: int = 0


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"o:{offset}".encode()).decode().rstrip("=")


def decode_cursor(cursor: Optional[str]) -> int:
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        kind, value = base64.urlsafe_b64decode(padded.encode()).decode().split(":", 1)
        offset = int(value)
        if kind != "o" or offset < 0:
            raise ValueError
        return offset
    except (ValueError, UnicodeDecodeError):
        raise APIError(400, "invalid_cursor", "The pagination cursor is invalid.")


def page_params(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Page size (max 100)"),
    cursor: Optional[str] = Query(None, description="Opaque cursor from a previous page"),
) -> PageParams:
    return PageParams(limit=limit, offset=decode_cursor(cursor))


def build_page(rows: List[T], params: PageParams) -> Page[T]:
    """`rows` must be fetched with LIMIT params.limit + 1 to detect a following page."""
    has_more = len(rows) > params.limit
    return Page[T](
        items=rows[: params.limit],
        next_cursor=encode_cursor(params.offset + params.limit) if has_more else None,
    )
