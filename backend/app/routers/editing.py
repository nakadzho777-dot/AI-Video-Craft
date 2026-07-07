"""編集支援 API.

- POST /editing/suggest : AI編集提案（カット/テロップ/BGM/テンポ/ショート化）
- POST /editing/probe   : 動画情報取得（FFmpeg）
- POST /editing/silence : 無音検出（FFmpeg）
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..ai.runtime import build_provider, resolve_model
from ..deps import get_device_id
from ..db.database import get_session
from ..db.models import Project, ProjectStatus
from ..editing.editor import apply_edit, extract_frames
from ..editing.materials import KIND_LABEL, material_sources
from ..editing.models import (
    AutoEditRequest,
    AutoEditResponse,
    LearnStyleRequest,
    LearnStyleResponse,
    ManualEditRequest,
    ManualEditResponse,
    MaterialSearchRequest,
    MaterialSearchResponse,
    MaterialSource,
    MaterialSuggestion,
    ProbeResponse,
    SilenceRangeOut,
    SilenceRequest,
    SuggestRequest,
    SuggestResponse,
)
from ..editing.service import (
    AutoEditService,
    EditingSuggestService,
    SuggestParseError,
)
from ..editing.youtube import fetch_reference_info
from ..license.guard import (
    enforce_advanced_editing,
    enforce_ai_quota,
    enforce_provider_allowed,
    enforce_export_resolution,
    enforce_video_duration,
    record_ai_run,
)
from ..license.manager import limits_for_device
from ..logging_conf import get_logger
from ..video.ffmpeg import FFmpegError, FFmpegService

logger = get_logger(__name__)
router = APIRouter(prefix="/editing", tags=["editing"])


class ProbeRequest(BaseModel):
    input_path: str


class ExportRequest(BaseModel):
    input_path: str
    output_path: str
    height: int | None = None   # 出力の高さ(px)。None なら元のまま
    vertical: bool = False       # 縦動画化（ショート）— 高度編集


async def _require_ffmpeg() -> FFmpegService:
    ffmpeg = FFmpegService()
    if not await ffmpeg.is_available():
        raise HTTPException(
            503,
            "FFmpeg が見つかりません。FFmpeg をインストールし、PATH を通してください。",
        )
    return ffmpeg


@router.post("/suggest", response_model=SuggestResponse)
async def suggest(
    req: SuggestRequest,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> SuggestResponse:
    limits = limits_for_device(device_id, session)
    # 1) プロジェクトから台本/企画を文脈として取り込む
    project: Project | None = None
    if req.project_id is not None:
        project = session.get(Project, req.project_id)
        if not project or project.device_id != device_id:
            raise HTTPException(404, "プロジェクトが見つかりません")
        if not req.script and project.script_text:
            req.script = project.script_text
        if req.duration_sec <= 0 and project.plan_json:
            try:
                plan = json.loads(project.plan_json)
                req.duration_sec = float(plan.get("target_duration_sec", 0) or 0)
            except (json.JSONDecodeError, ValueError):
                pass

    # 2) プロバイダー / モデル解決 + プラン制限
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

    # 3) 提案生成
    service = EditingSuggestService(provider)
    try:
        suggestion = await service.suggest(req, model=model)
    except SuggestParseError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        logger.exception("edit suggestion failed")
        detail = str(e) or type(e).__name__
        raise HTTPException(502, f"編集提案の生成に失敗しました: {detail}") from e
    record_ai_run(session, device_id)

    # 4) 任意で保存
    saved: int | None = None
    if project is not None:
        project.edit_plan_json = suggestion.model_dump_json()
        project.status = ProjectStatus.EDITING
        project.updated_at = datetime.now(timezone.utc)
        session.add(project)
        session.commit()
        saved = project.id

    return SuggestResponse(
        suggestion=suggestion, provider=provider_id, model=model, saved_to_project=saved
    )


@router.post("/learn-style", response_model=LearnStyleResponse)
async def learn_style(
    req: LearnStyleRequest,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> LearnStyleResponse:
    """参考動画/クリエイター/特徴から編集スタイルを言語化する。"""
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

    # 参考URLがあれば公開情報（投稿者/タイトル）を取得（ベストエフォート）
    source = await fetch_reference_info(req.reference_url)

    service = EditingSuggestService(provider)
    try:
        style = await service.learn_style(
            creator=req.creator, source=source, notes=req.notes, model=model
        )
    except SuggestParseError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        logger.exception("style learning failed")
        detail = str(e) or type(e).__name__
        raise HTTPException(502, f"スタイル学習に失敗しました: {detail}") from e
    record_ai_run(session, device_id)

    return LearnStyleResponse(
        style=style, provider=provider_id, model=model, source=source
    )


@router.post("/probe", response_model=ProbeResponse)
async def probe(
    req: ProbeRequest, device_id: str = Depends(get_device_id)
) -> ProbeResponse:
    ffmpeg = await _require_ffmpeg()
    try:
        info = await ffmpeg.probe(req.input_path)
    except FFmpegError as e:
        raise HTTPException(400, f"動画の読み込みに失敗しました: {e}") from e
    return ProbeResponse(
        duration_sec=info.duration_sec, width=info.width, height=info.height
    )


@router.post("/export")
async def export_video(
    req: ExportRequest,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> dict:
    limits = limits_for_device(device_id, session)
    # プラン制限（FFmpeg 実行前にチェックできるものを先に）
    if req.vertical:
        enforce_advanced_editing(limits, "縦動画化（ショート生成）")
    enforce_export_resolution(limits, req.height)

    ffmpeg = await _require_ffmpeg()

    # 尺の上限は実測が必要なので probe してから確認する
    try:
        info = await ffmpeg.probe(req.input_path)
    except FFmpegError as e:
        raise HTTPException(400, f"動画の読み込みに失敗しました: {e}") from e
    enforce_video_duration(limits, info.duration_sec)

    try:
        if req.vertical:
            out = await ffmpeg.to_vertical(req.input_path, req.output_path)
        else:
            out = await ffmpeg.export(req.input_path, req.output_path, height=req.height)
    except FFmpegError as e:
        raise HTTPException(400, f"書き出しに失敗しました: {e}") from e
    return {"output_path": str(out)}


@router.post("/silence", response_model=list[SilenceRangeOut])
async def detect_silence(
    req: SilenceRequest, device_id: str = Depends(get_device_id)
) -> list[SilenceRangeOut]:
    ffmpeg = await _require_ffmpeg()
    try:
        ranges = await ffmpeg.detect_silence(
            req.input_path,
            noise_db=req.noise_db,
            min_silence_sec=req.min_silence_sec,
        )
    except FFmpegError as e:
        raise HTTPException(400, f"無音検出に失敗しました: {e}") from e
    return [
        SilenceRangeOut(
            start_sec=r.start_sec, end_sec=r.end_sec, duration_sec=r.duration_sec
        )
        for r in ranges
    ]


class ThumbsRequest(BaseModel):
    input_path: str
    count: int = 10


@router.post("/thumbnails")
async def timeline_thumbnails(
    req: ThumbsRequest, device_id: str = Depends(get_device_id)
) -> dict:
    """タイムライン用に、動画から等間隔のサムネイル(base64 data URL)を返す。"""
    import asyncio
    import base64

    n = max(3, min(24, req.count))
    frames = await asyncio.to_thread(extract_frames, req.input_path, n, 240)
    urls = [
        "data:image/jpeg;base64," + base64.b64encode(f).decode("ascii")
        for f in frames
    ]
    return {"frames": urls}


# ============================================================
# 動画編集（自動 / 手動 / 素材検索）
# ============================================================
def _edit_out_dir() -> str:
    from ..config import get_settings

    return str(get_settings().data_dir / "edited")


@router.post("/auto", response_model=AutoEditResponse)
async def auto_edit(
    req: AutoEditRequest,
    session: Session = Depends(get_session),
    device_id: str = Depends(get_device_id),
) -> AutoEditResponse:
    """指示に従ってAIが編集プランを作り、カット＋テロップを自動適用する。"""
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

    ffmpeg = await _require_ffmpeg()
    try:
        info = await ffmpeg.probe(req.input_path)
        silence = await ffmpeg.detect_silence(req.input_path)
    except FFmpegError as e:
        raise HTTPException(400, f"動画の読み込みに失敗しました: {e}") from e

    service = AutoEditService(provider)
    try:
        plan = await service.plan(
            instructions=req.instructions,
            duration_sec=info.duration_sec,
            silence_count=len(silence),
            model=model,
            edit_heavy=req.edit_heavy,
        )
    except SuggestParseError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        logger.exception("auto edit plan failed")
        raise HTTPException(502, f"編集プラン生成に失敗しました: {e}") from e
    record_ai_run(session, device_id)

    # カット集合 = (無音区間 if remove_silence) + AI提案カット
    cuts: list[tuple[float, float]] = []
    if plan.remove_silence:
        cuts += [(r.start_sec, r.end_sec) for r in silence]
    cuts += [(c.start_sec, c.end_sec) for c in plan.cuts if c.end_sec > c.start_sec]
    telops = [{"time_sec": t.time_sec, "text": t.text} for t in plan.telops]

    warnings: list[str] = []
    try:
        out, dur = await apply_edit(
            req.input_path, _edit_out_dir(), cuts=cuts, telops=telops,
            subtitles=req.has_subtitles, vertical=req.vertical,
        )
    except Exception as e:
        logger.exception("auto edit apply failed")
        raise HTTPException(502, f"編集の適用に失敗しました: {e}") from e

    return AutoEditResponse(
        output_path=out,
        duration_sec=dur,
        original_sec=round(info.duration_sec, 2),
        plan=plan,
        warnings=warnings,
    )


@router.post("/apply", response_model=ManualEditResponse)
async def apply_manual_edit(
    req: ManualEditRequest,
    device_id: str = Depends(get_device_id),
) -> ManualEditResponse:
    """手動編集（カット・テロップ・音量・縦動画化）を適用する。"""
    cuts = [(c.start_sec, c.end_sec) for c in req.cuts if c.end_sec > c.start_sec]
    telops = [t.model_dump() for t in req.telops if t.text.strip()]
    overlays = [
        {
            "image": o.image,
            "start_sec": o.start_sec,
            "end_sec": o.end_sec,
            "position": o.position,
        }
        for o in req.overlays
        if o.image.strip()
    ]
    try:
        out, dur = await apply_edit(
            req.input_path,
            _edit_out_dir(),
            cuts=cuts,
            telops=telops,
            vertical=req.vertical,
            volume=req.volume,
            mute=req.mute,
            bgm=req.bgm.strip() or None,
            bgm_volume=req.bgm_volume,
            overlays=overlays,
            subtitles=req.has_subtitles,
            speed=req.speed,
            vfilter=req.vfilter,
            fade_in=req.fade_in,
            fade_out=req.fade_out,
        )
    except Exception as e:
        logger.exception("manual edit failed")
        raise HTTPException(502, f"編集の適用に失敗しました: {e}") from e
    return ManualEditResponse(output_path=out, duration_sec=dur)


@router.post("/materials", response_model=MaterialSearchResponse)
async def search_materials(
    req: MaterialSearchRequest,
    device_id: str = Depends(get_device_id),
) -> MaterialSearchResponse:
    """キーワードに対して、無料で使える素材サイトのURLを種別ごとに返す。"""
    q = req.query.strip()
    mats = [
        MaterialSuggestion(
            kind=kind,
            kind_label=KIND_LABEL[kind],
            query=q,
            reason="",
            sources=[MaterialSource(**s) for s in material_sources(kind, q)],
        )
        for kind in ("bgm", "se", "image", "video")
    ]
    return MaterialSearchResponse(materials=mats)


# ---- ダウンロードした素材の検出（フォルダを走査）----
_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


class DetectMaterialsRequest(BaseModel):
    folder: str


class DetectedFile(BaseModel):
    path: str
    name: str


class DetectMaterialsResponse(BaseModel):
    audio: list[DetectedFile] = []
    images: list[DetectedFile] = []


@router.post("/detect-materials", response_model=DetectMaterialsResponse)
def detect_materials(
    req: DetectMaterialsRequest, device_id: str = Depends(get_device_id)
) -> DetectMaterialsResponse:
    """素材フォルダを走査し、ダウンロード済みの音声/画像ファイルを検出する。"""
    import os

    folder = req.folder.strip()
    if not folder or not os.path.isdir(folder):
        raise HTTPException(400, "有効なフォルダを指定してください。")
    audio: list[DetectedFile] = []
    images: list[DetectedFile] = []
    try:
        for name in sorted(os.listdir(folder)):
            full = os.path.join(folder, name)
            if not os.path.isfile(full):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in _AUDIO_EXT:
                audio.append(DetectedFile(path=full, name=name))
            elif ext in _IMAGE_EXT:
                images.append(DetectedFile(path=full, name=name))
    except OSError as e:
        raise HTTPException(400, f"フォルダを読み込めませんでした: {e}") from e
    return DetectMaterialsResponse(audio=audio, images=images)
