"""プロジェクト CRUD.

動画1本ごとのプロジェクト管理。PC（デバイス）単位で所有し、
Free プランは作成数制限（1件）を適用する。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..db.database import get_session
from ..db.models import Project
from ..deps import get_device_id
from ..license.manager import limits_for_device
from ..schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


def _owned(session: Session, project_id: int, device_id: str) -> Project:
    project = session.get(Project, project_id)
    if not project or project.device_id != device_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "プロジェクトが見つかりません")
    return project


@router.get("", response_model=list[ProjectRead])
def list_projects(
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> list[Project]:
    return list(
        session.exec(
            select(Project)
            .where(Project.device_id == device_id)
            .order_by(Project.updated_at.desc())
        )
    )


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> Project:
    # Free プランのプロジェクト数制限（このPCのプロジェクトのみ数える）
    limit = limits_for_device(device_id, session).max_projects
    if limit is not None:
        count = len(
            list(session.exec(select(Project).where(Project.device_id == device_id)))
        )
        if count >= limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    f"Free版はプロジェクト{limit}件までです。"
                    "Pro版へのアップグレードで無制限になります。"
                ),
            )

    project = Project.model_validate(payload)
    project.device_id = device_id
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: int,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> Project:
    return _owned(session, project_id, device_id)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> Project:
    project = _owned(session, project_id, device_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    project.updated_at = datetime.now(timezone.utc)

    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> None:
    project = _owned(session, project_id, device_id)
    session.delete(project)
    session.commit()
