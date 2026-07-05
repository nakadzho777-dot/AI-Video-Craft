"""プロジェクト CRUD.

動画1本ごとのプロジェクト管理。アカウント単位で所有し、
Free プランは作成数制限（1件）を適用する。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..auth.deps import get_current_user
from ..db.database import get_session
from ..db.models import Project, User
from ..license.manager import limits_for_user
from ..schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


def _owned(session: Session, project_id: int, user: User) -> Project:
    project = session.get(Project, project_id)
    if not project or project.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "プロジェクトが見つかりません")
    return project


@router.get("", response_model=list[ProjectRead])
def list_projects(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[Project]:
    return list(
        session.exec(
            select(Project)
            .where(Project.owner_user_id == user.id)
            .order_by(Project.updated_at.desc())
        )
    )


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Project:
    # Free プランのプロジェクト数制限（自分のプロジェクトのみ数える）
    limit = limits_for_user(user, session).max_projects
    if limit is not None:
        count = len(
            list(
                session.exec(
                    select(Project).where(Project.owner_user_id == user.id)
                )
            )
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
    project.owner_user_id = user.id
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Project:
    return _owned(session, project_id, user)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Project:
    project = _owned(session, project_id, user)

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
    user: User = Depends(get_current_user),
) -> None:
    project = _owned(session, project_id, user)
    session.delete(project)
    session.commit()
