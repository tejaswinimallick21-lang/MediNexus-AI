from typing import List

from pydantic import BaseModel


class SystemStatus(BaseModel):
    gold_ready: bool
    ml_ready: bool
    llm_provider: str
    version: str


class RoleCard(BaseModel):
    role: str
    title: str
    description: str
    routes: List[str]


class PlatformOverview(BaseModel):
    app_name: str
    tagline: str
    version: str
    pipeline_stages: List[str]
    roles: List[RoleCard]
