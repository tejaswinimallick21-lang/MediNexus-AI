from typing import List

from pydantic import BaseModel


class ErrorOut(BaseModel):
    detail: str
    code: str


class LabelCount(BaseModel):
    label: str
    count: int


# Documented error responses shared by every router
ERROR_RESPONSES = {
    400: {"model": ErrorOut},
    401: {"model": ErrorOut},
    403: {"model": ErrorOut},
    404: {"model": ErrorOut},
    422: {"model": ErrorOut},
    503: {"model": ErrorOut},
}

__all__: List[str] = ["ErrorOut", "LabelCount", "ERROR_RESPONSES"]
