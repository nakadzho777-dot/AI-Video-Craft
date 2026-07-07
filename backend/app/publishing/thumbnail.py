"""サムネイル生成（Pillow）.

ベース画像（動画のシーン / インポート画像 / AI生成 / グラデーション）に
タイトル等のテキストを重ねて 1280x720 のサムネイルPNGを作る。
投稿支援の「サムネ作業場」から呼ばれる。
"""
from __future__ import annotations

import os
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

_FONT_REG = "C:/Windows/Fonts/meiryo.ttc"
_FONT_BOLD = "C:/Windows/Fonts/meiryob.ttc"


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    path = _FONT_BOLD if bold else _FONT_REG
    try:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
        return ImageFont.truetype("meiryob.ttc", size)
    except Exception:
        return ImageFont.load_default(size)


def _hex(c: str, default=(255, 255, 255)) -> tuple[int, int, int]:
    c = (c or "").strip().lstrip("#")
    if len(c) == 6:
        try:
            return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
        except ValueError:
            pass
    return default


# ---- テキスト要素 ----
class ThumbText(BaseModel):
    text: str = ""
    x: float = 0.5           # 0..1（中心基準の水平位置）
    y: float = 0.5           # 0..1
    size: int = 96           # フォントサイズ(px)
    color: str = "#ffffff"
    stroke: str = "#000000"  # 縁取り色
    stroke_width: int = 8
    bold: bool = True
    align: str = "center"    # left|center|right


class ThumbSpec(BaseModel):
    width: int = 1280
    height: int = 720
    base_kind: str = "gradient"      # scene | image | gradient | ai
    image_path: str = ""             # base_kind=image/ai/scene の結果画像
    video_path: str = ""             # base_kind=scene 用
    scene_time: float = 0.0          # base_kind=scene 用（秒）
    color_a: str = "#7c5cff"         # gradient 上
    color_b: str = "#0b0b18"         # gradient 下
    darken: float = 0.25             # 文字を読みやすくする暗幕(0..1)
    texts: List[ThumbText] = Field(default_factory=list)


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """アスペクトを保ったまま w x h を覆うようにリサイズ＋中央クロップ。"""
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    img = img.resize((nw, nh))
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def _gradient(w: int, h: int, top: tuple, bot: tuple) -> Image.Image:
    img = Image.new("RGB", (w, h), bot)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        d.line([(0, y), (w, y)], fill=c)
    return img


def _draw_text(img: Image.Image, t: ThumbText) -> None:
    d = ImageDraw.Draw(img)
    W, H = img.size
    fnt = _font(max(12, t.size), t.bold)
    lines = (t.text or "").split("\n")
    # 各行の寸法
    heights, widths = [], []
    for ln in lines:
        bbox = d.textbbox((0, 0), ln or " ", font=fnt, stroke_width=t.stroke_width)
        widths.append(bbox[2] - bbox[0])
        heights.append(bbox[3] - bbox[1])
    total_h = sum(heights) + int(t.size * 0.2) * (len(lines) - 1)
    cx, cy = t.x * W, t.y * H
    y = cy - total_h / 2
    fill = _hex(t.color)
    stroke = _hex(t.stroke, (0, 0, 0))
    for ln, lw, lh in zip(lines, widths, heights):
        if t.align == "left":
            x = cx
        elif t.align == "right":
            x = cx - lw
        else:
            x = cx - lw / 2
        d.text(
            (x, y), ln, font=fnt, fill=fill,
            stroke_width=t.stroke_width, stroke_fill=stroke,
        )
        y += lh + int(t.size * 0.2)


def build_base(spec: ThumbSpec, extract_frame=None) -> Image.Image:
    """ベース画像を用意する。extract_frame は scene 用のフレーム抽出関数。"""
    W, H = spec.width, spec.height
    if spec.base_kind in ("image", "ai") and spec.image_path and os.path.exists(spec.image_path):
        try:
            return _cover(Image.open(spec.image_path).convert("RGB"), W, H)
        except Exception:
            pass
    if spec.base_kind == "scene" and spec.image_path and os.path.exists(spec.image_path):
        try:
            return _cover(Image.open(spec.image_path).convert("RGB"), W, H)
        except Exception:
            pass
    # フォールバック: グラデーション
    return _gradient(W, H, _hex(spec.color_a, (124, 92, 255)), _hex(spec.color_b, (11, 11, 24)))


def render_thumbnail(spec: ThumbSpec, out_path: str) -> str:
    img = build_base(spec)
    # 暗幕（文字の可読性向上）
    if spec.darken > 0:
        overlay = Image.new("RGBA", img.size, (0, 0, 0, int(min(1.0, spec.darken) * 255)))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    for t in spec.texts:
        if (t.text or "").strip():
            _draw_text(img, t)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path)
    return out_path


# ---- AIによるサムネ文言の提案 ----
THUMB_SUGGEST_SYS = (
    "あなたはYouTubeサムネイルのコピーライターです。"
    "クリック率を最大化する、短く力強いサムネイル用の文言を作ります。\n"
    "出力は必ず次のJSONのみ:\n"
    '{"title": "サムネ大見出し(最大12文字・改行は\\nで最大2行)", '
    '"subtitle": "小さめの補足(最大16文字・任意)"}\n'
    "- 具体的な数字・ベネフィット・意外性で目を引く。\n"
    "- 長い文章にしない。パッと読める単語/短文にする。日本語で。"
)


def build_suggest_user(topic: str, notes: str, analysis: Optional[str]) -> str:
    lines = [f"動画テーマ: {topic or '(未指定)'}"]
    if notes:
        lines.append(f"補足: {notes}")
    if analysis:
        lines.append(f"AIが確認した動画内容: {analysis}")
    lines.append("上記に最適なサムネ文言をJSONで出してください。")
    return "\n".join(lines)
