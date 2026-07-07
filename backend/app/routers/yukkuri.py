"""ゆっくり解説 API.

- POST /yukkuri/script : テーマから2キャラ掛け合い台本を生成
- POST /yukkuri/render : 台本を動画（音声＋キャラ＋字幕枠）に仕上げる
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..ai.runtime import build_provider, resolve_model
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
from ..yukkuri.models import (
    JikkyouRenderRequest,
    RenderRequest,
    RenderResponse,
    ScriptRequest,
    ScriptResponse,
)
from ..yukkuri.service import (
    ScriptParseError,
    YukkuriScriptService,
    render_jikkyou,
    render_video,
)
from ..yukkuri import voicevox
from ..yukkuri.voice import (
    AQUESTALK_DOWNLOAD_URL,
    aquestalk_available,
    detect_aquestalk,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/yukkuri", tags=["yukkuri"])


@router.get("/config")
async def yukkuri_config() -> dict:
    """使用中の音声エンジンと、選べる音声一覧。"""
    voices = [
        {"id": "ja-JP-NanamiNeural", "label": "Nanami（女性・標準）"},
        {"id": "ja-JP-KeitaNeural", "label": "Keita（男性・標準）"},
    ]
    vv_voices = await voicevox.voice_options()
    voices.extend(vv_voices)
    aq = aquestalk_available()
    engine = "aquestalk" if aq else "edge-tts"
    if vv_voices:
        engine = "voicevox"
    return {
        "voice_engine": engine,
        "voices": voices,
        "voicevox_available": bool(vv_voices),
        "voicevox_download_url": voicevox.DOWNLOAD_URL,
        "aquestalk_available": aq,
        "aquestalk_dir": detect_aquestalk(),
        "aquestalk_download_url": AQUESTALK_DOWNLOAD_URL,
    }


@router.post("/script", response_model=ScriptResponse)
async def make_script(
    req: ScriptRequest,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> ScriptResponse:
    if not req.topic.strip():
        raise HTTPException(400, "テーマを入力してください。")

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

    service = YukkuriScriptService(provider)
    try:
        script = await service.generate(req, model=model)
    except ScriptParseError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        logger.exception("yukkuri script failed")
        raise HTTPException(502, f"台本生成に失敗しました: {e}") from e
    record_ai_run(session, device_id)

    return ScriptResponse(script=script, provider=provider_id, model=model)


@router.post("/render", response_model=RenderResponse)
async def render(
    req: RenderRequest,
    device_id: str = Depends(get_device_id),
) -> RenderResponse:
    if not req.script.lines:
        raise HTTPException(400, "台本がありません。")
    out_dir = str(get_settings().data_dir / "yukkuri")
    try:
        return await render_video(req.script, req.chars, out_dir)
    except Exception as e:
        logger.exception("yukkuri render failed")
        raise HTTPException(502, f"動画生成に失敗しました: {e}") from e


@router.post("/jikkyou/render", response_model=RenderResponse)
async def jikkyou_render(
    req: JikkyouRenderRequest,
    device_id: str = Depends(get_device_id),
) -> RenderResponse:
    if not req.script.lines:
        raise HTTPException(400, "台本がありません。")
    if not req.base_video.strip():
        raise HTTPException(400, "元動画を選んでください。")
    out_dir = str(get_settings().data_dir / "yukkuri")
    try:
        return await render_jikkyou(
            req.base_video,
            req.script,
            req.chars,
            req.voice_a,
            req.voice_b,
            out_dir,
            subtitles=req.subtitles,
            keep_audio=req.keep_original_audio,
        )
    except Exception as e:
        logger.exception("jikkyou render failed")
        raise HTTPException(502, f"実況の生成に失敗しました: {e}") from e
