"""DB エンジン / セッション管理。"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from ..config import get_settings
from ..logging_conf import get_logger

logger = get_logger(__name__)

_settings = get_settings()

# check_same_thread=False は FastAPI のスレッドプールから使うため
engine = create_engine(
    _settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """テーブルを作成し、不足カラムを追加する。"""
    # モデルを import してメタデータに登録されるようにする
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _migrate_add_missing_columns()
    logger.info("Database initialized at %s", _settings.db_path)


def _migrate_add_missing_columns() -> None:
    """モデルに存在するがテーブルに無いカラムを追加する簡易マイグレーション.

    SQLModel.create_all は既存テーブルを変更しないため、
    フィールド追加時に既存 DB でもカラムを補う（開発向けの軽量措置）。
    """
    inspector = inspect(engine)
    for table_name, table in SQLModel.metadata.tables.items():
        existing = {c["name"] for c in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name in existing:
                continue
            col_type = column.type.compile(engine.dialect)
            # 既存行を有効な値で埋めるため型に応じた既定値を付与する
            if "CHAR" in col_type.upper() or "TEXT" in col_type.upper():
                default = "DEFAULT ''"
            elif "INT" in col_type.upper():
                default = "DEFAULT 0"
            else:
                default = ""
            ddl = (
                f'ALTER TABLE "{table_name}" '
                f'ADD COLUMN "{column.name}" {col_type} {default}'.strip()
            )
            with engine.begin() as conn:
                conn.execute(text(ddl))
            logger.info("Migrated: added column %s.%s", table_name, column.name)


def get_session() -> Iterator[Session]:
    """FastAPI 依存性注入用のセッション供給。"""
    with Session(engine) as session:
        yield session
