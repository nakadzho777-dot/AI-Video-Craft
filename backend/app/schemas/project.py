"""プロジェクト関連スキーマ。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from ..db.models import MaterialMode, ProductionMode, ProjectStatus


class ProjectCreate(BaseModel):
    title: str
    description: str = ""
    production_mode: ProductionMode = ProductionMode.AUTO
    material_mode: MaterialMode = MaterialMode.REQUEST


class ProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    production_mode: ProductionMode | None = None
    material_mode: MaterialMode | None = None
    status: ProjectStatus | None = None
    target_duration_sec: float | None = None


class ProjectRead(BaseModel):
    id: int
    title: str
    description: str
    production_mode: ProductionMode
    material_mode: MaterialMode
    status: ProjectStatus
    target_duration_sec: float = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("target_duration_sec", mode="before")
    @classmethod
    def _none_to_zero(cls, v: object) -> float:
        # 旧DBで NULL のまま残った行でも 500 にせず 0 として返す
        return 0.0 if v is None else v
