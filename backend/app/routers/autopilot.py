"""AI自動撮影 API.

- POST /autopilot/plan : URL＋テーマから、AIがブラウザ操作台本を生成
- POST /autopilot/run  : 台本を実行（Playwrightで自動操作＆録画＋TTS＋合成）→ MP4
- GET  /autopilot/voices : 使用可能なナレーション音声
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..ai.runtime import build_provider, resolve_model
from ..autopilot.desktop import (
    DesktopPlanService,
    list_windows,
    run_desktop_autopilot,
)
from ..autopilot.models import (
    DesktopPlanRequest,
    DesktopPlanResponse,
    DesktopRunRequest,
    PlanRequest,
    PlanResponse,
    RunRequest,
    RunResponse,
)
from ..autopilot.service import (
    JA_VOICES,
    AutopilotPlanService,
    PlanParseError,
    request_cancel,
    run_autopilot,
)
from ..config import get_settings
from ..db.database import get_session
from ..deps import get_device_id
from ..license.guard import (
    enforce_ai_quota,
    enforce_provider_allowed,
    record_ai_run,
)
from ..license.manager import limits_for_device
from ..logging_conf import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/autopilot", tags=["autopilot"])


@router.get("/voices")
async def voices() -> dict:
    from ..yukkuri import voicevox

    vs = list(JA_VOICES)
    try:
        vs += await voicevox.voice_options()
    except Exception:
        pass
    return {"voices": vs}


@router.post("/plan", response_model=PlanResponse)
async def make_plan(
    req: PlanRequest,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> PlanResponse:
    if not req.url.strip():
        raise HTTPException(400, "対象URLを入力してください。")

    limits = limits_for_device(device_id, session)
    try:
        provider_id, provider = build_provider(req.provider)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    enforce_provider_allowed(limits, provider)
    enforce_ai_quota(limits, session, device_id)
    try:
        model = await resolve_model(provider, provider_id, req.model)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e

    service = AutopilotPlanService(provider)
    try:
        plan = await service.generate(req, model=model)
    except PlanParseError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        logger.exception("autopilot plan failed")
        raise HTTPException(502, f"台本生成に失敗しました: {e}") from e
    record_ai_run(session, device_id)

    return PlanResponse(plan=plan, provider=provider_id, model=model)


@router.post("/run", response_model=RunResponse)
async def run(
    req: RunRequest,
    device_id: str = Depends(get_device_id),
) -> RunResponse:
    if not req.plan.url.strip() or not req.plan.steps:
        raise HTTPException(400, "実行する台本がありません。")
    settings = get_settings()
    out_dir = str(settings.data_dir / "autopilot")
    try:
        return await run_autopilot(
            req.plan,
            req.voice or "ja-JP-NanamiNeural",
            out_dir,
            subtitles=req.subtitles,
            yukkuri=req.yukkuri,
            yukkuri_name=req.yukkuri_name or "霊夢",
            yukkuri_avatar=req.yukkuri_avatar,
            yukkuri_show=req.yukkuri_show,
            allowed_urls=req.allowed_urls,
            token=req.token,
            narrate=req.narrate,
        )
    except Exception as e:
        logger.exception("autopilot run failed")
        raise HTTPException(502, f"自動撮影に失敗しました: {e}") from e


# ============================================================
# デスクトップアプリ版
# ============================================================
@router.get("/desktop/windows")
def desktop_windows(_: str = Depends(get_device_id)) -> dict:
    """現在開いているウィンドウのタイトル一覧。"""
    return {"windows": list_windows()}


@router.post("/desktop/plan", response_model=DesktopPlanResponse)
async def desktop_plan(
    req: DesktopPlanRequest,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> DesktopPlanResponse:
    if not req.window_title.strip():
        raise HTTPException(400, "対象ウィンドウを選んでください。")

    limits = limits_for_device(device_id, session)
    try:
        provider_id, provider = build_provider(req.provider)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    enforce_provider_allowed(limits, provider)
    enforce_ai_quota(limits, session, device_id)
    try:
        model = await resolve_model(provider, provider_id, req.model)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e

    service = DesktopPlanService(provider)
    try:
        plan = await service.generate(req, model=model)
    except PlanParseError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        logger.exception("desktop plan failed")
        raise HTTPException(502, f"台本生成に失敗しました: {e}") from e
    record_ai_run(session, device_id)

    return DesktopPlanResponse(plan=plan, provider=provider_id, model=model)


@router.post("/desktop/run", response_model=RunResponse)
async def desktop_run(
    req: DesktopRunRequest,
    device_id: str = Depends(get_device_id),
) -> RunResponse:
    if not req.plan.window_title.strip() or not req.plan.steps:
        raise HTTPException(400, "実行する台本がありません。")
    settings = get_settings()
    out_dir = str(settings.data_dir / "autopilot")
    try:
        return await run_desktop_autopilot(
            req.plan,
            req.voice or "ja-JP-NanamiNeural",
            out_dir,
            subtitles=req.subtitles,
            token=req.token,
            narrate=req.narrate,
        )
    except Exception as e:
        logger.exception("desktop autopilot run failed")
        raise HTTPException(502, f"アプリの自動撮影に失敗しました: {e}") from e


class CancelIn(BaseModel):
    token: str


@router.post("/cancel")
def cancel_run(payload: CancelIn, _: str = Depends(get_device_id)) -> dict:
    """実行中の自動操作をキャンセルする（トークンで指定）。"""
    request_cancel(payload.token)
    return {"cancelled": True}
