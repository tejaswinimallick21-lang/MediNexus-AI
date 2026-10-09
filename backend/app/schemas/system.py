from typing import List

from pydantic import BaseModel


class SystemStatus(BaseModel):
    gold_ready: bool
    ml_ready: bool
    llm_provider: str
    version: str


class PersonaCard(BaseModel):
    persona: str
    role: str
    title: str
    description: str
    route: str


class PlatformOverview(BaseModel):
    app_name: str
    tagline: str
    version: str
    pipeline_stages: List[str]
    personas: List[PersonaCard]
