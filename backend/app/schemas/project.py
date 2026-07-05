"""プロジェクト関連スキーマ。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

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


class ProjectRead(BaseModel):
    id: int
    title: str
    description: str
    production_mode: ProductionMode
    material_mode: MaterialMode
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
