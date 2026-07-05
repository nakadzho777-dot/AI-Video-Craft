"""FastAPI アプリケーション エントリポイント.

起動時に: ロギング初期化 → DB 初期化 → AIプロバイダー読み込み。
CORS は Electron(Vite) からのローカルアクセスを許可する。
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .ai import registry
from .config import get_settings
from .db.database import init_db
from .logging_conf import get_logger, setup_logging
from .routers import (
    ai,
    auth,
    billing,
    editing,
    health,
    license,
    marketing,
    planning,
    projects,
    publishing,
    recording,
    settings,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger = get_logger("startup")
    logger.info("Starting AI VideoCraft backend v%s", __version__)
    init_db()
    registry.load_builtin_providers()
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="AI VideoCraft API",
    version=__version__,
    lifespan=lifespan,
)

# CORS: 認証は Bearer トークン（Cookie不使用）のため、任意オリジンを許可し
# 資格情報モードは無効にする。これにより開発サーバ・Electron本番ロード
# （file:// / app:// = Origin null）・別ホスト配信のいずれからでも利用できる。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(license.router)
app.include_router(billing.router)
app.include_router(projects.router)
app.include_router(ai.router)
app.include_router(planning.router)
app.include_router(recording.router)
app.include_router(editing.router)
app.include_router(publishing.router)
app.include_router(marketing.router)
app.include_router(settings.router)


def main() -> None:
    """`python -m app.main` での起動用。"""
    import uvicorn

    cfg = get_settings()
    uvicorn.run("app.main:app", host=cfg.host, port=cfg.port, reload=False)


if __name__ == "__main__":
    main()
