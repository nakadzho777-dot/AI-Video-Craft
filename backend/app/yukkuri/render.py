"""ゆっくり解説のフレーム描画（Pillow）.

背景＋2キャラ＋セリフ枠を1枚のPNGに描く。話しているキャラを強調する。
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

from .models import CharacterConfig, YukkuriLine

W, H = 1280, 720

# 日本語フォント（無ければ Pillow 既定にフォールバック）
_FONT_REG = "C:/Windows/Fonts/meiryo.ttc"
_FONT_BOLD = "C:/Windows/Fonts/meiryob.ttc"

# キャラの色（左=シアン / 右=バイオレット）
ACC_A = (34, 211, 238)
ACC_B = (168, 85, 247)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = _FONT_BOLD if bold else _FONT_REG
    try:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
        return ImageFont.truetype("meiryo.ttc", size)
    except Exception:
        return ImageFont.load_default(size)


def _gradient_bg() -> Image.Image:
    top, bot = (14, 14, 30), (5, 5, 12)
    img = Image.new("RGB", (W, H), bot)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        d.line([(0, y), (W, y)], fill=c)
    return img


def _wrap(draw, text: str, fnt, max_w: int):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if draw.textlength(cur + ch, font=fnt) <= max_w:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def _avatar(img, cx, cy, r, accent, name, active, avatar_path=None):
    d = ImageDraw.Draw(img, "RGBA")
    dim = 255 if active else 90
    d.ellipse(
        [cx - r - 8, cy - r - 8, cx + r + 8, cy + r + 8],
        outline=accent + (dim,), width=6 if active else 2,
    )
    if avatar_path and os.path.exists(avatar_path):
        try:
            av = Image.open(avatar_path).convert("RGBA").resize((r * 2, r * 2))
            mask = Image.new("L", (r * 2, r * 2), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, r * 2, r * 2], fill=dim)
            img.paste(av, (cx - r, cy - r), mask)
        except Exception:
            avatar_path = None
    if not (avatar_path and os.path.exists(avatar_path)):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent + (int(dim * 0.35),))
        f = _font(90, True)
        ch = (name or "?")[0]
        w = d.textlength(ch, font=f)
        d.text((cx - w / 2, cy - 70), ch, font=f, fill=(255, 255, 255, dim))
    fn = _font(34, True)
    nw = d.textlength(name, font=fn)
    d.text((cx - nw / 2, cy + r + 18), name, font=fn, fill=(255, 255, 255, dim))


def _tachie(img, cx, bottom, max_h, accent, name, active, path, show_name=True):
    """立ち絵（画像）を下端 bottom・中央 cx に、縦 max_h に収めて貼る。"""
    d = ImageDraw.Draw(img, "RGBA")
    dim = 255 if active else 110
    try:
        pic = Image.open(path).convert("RGBA")
    except Exception:
        return False
    ratio = min(max_h / pic.height, 520 / pic.width)
    w, h = max(1, int(pic.width * ratio)), max(1, int(pic.height * ratio))
    pic = pic.resize((w, h))
    if not active:  # 話していないキャラは少し暗く
        alpha = pic.split()[3].point(lambda a: int(a * 0.55))
        pic.putalpha(alpha)
    img.paste(pic, (int(cx - w / 2), int(bottom - h)), pic)
    if show_name:
        fn = _font(34, True)
        nw = d.textlength(name, font=fn)
        d.rectangle([cx - nw / 2 - 14, bottom + 6, cx + nw / 2 + 14, bottom + 52],
                    fill=(0, 0, 0, 150))
        d.text((cx - nw / 2, bottom + 12), name, font=fn, fill=accent + (dim,))
    return True


def _draw_char(img, cx, cy, r, accent, name, active, avatar_path,
               tachie_bottom=490, tachie_h=450, show_name=True):
    """立ち絵（画像あり）または丸顔（画像なし）でキャラを描く。"""
    if avatar_path and os.path.exists(avatar_path):
        if _tachie(img, cx, tachie_bottom, tachie_h, accent, name, active,
                   avatar_path, show_name):
            return
    _avatar(img, cx, cy, r, accent, name, active)


def render_frame(
    chars: CharacterConfig,
    line: YukkuriLine,
    out_path: str,
    avatar_a: str | None = None,
    avatar_b: str | None = None,
) -> None:
    img = _gradient_bg()
    active_a = line.speaker == "a"
    av_a = avatar_a or (chars.avatar_a or None)
    av_b = avatar_b or (chars.avatar_b or None)
    if not chars.show_chars:
        pass  # キャラ非表示（セリフ枠だけ）
    elif chars.single:
        _draw_char(img, W // 2, 250, 150, ACC_A, chars.name_a, True, av_a,
                   tachie_bottom=478, tachie_h=470, show_name=False)
    else:
        _draw_char(img, 300, 260, 130, ACC_A, chars.name_a, active_a, av_a,
                   tachie_bottom=478, tachie_h=460, show_name=False)
        _draw_char(img, 980, 260, 130, ACC_B, chars.name_b, not active_a, av_b,
                   tachie_bottom=478, tachie_h=460, show_name=False)

    d = ImageDraw.Draw(img, "RGBA")
    bx0, by0, bx1, by1 = 80, 500, 1200, 690
    d.rounded_rectangle(
        [bx0, by0, bx1, by1], radius=24,
        fill=(0, 0, 0, 150), outline=(255, 255, 255, 40), width=2,
    )
    acc = ACC_A if active_a else ACC_B
    nm = chars.name_a if active_a else chars.name_b
    d.text((bx0 + 30, by0 + 18), nm, font=_font(30, True), fill=acc)
    fnt = _font(44, True)
    for i, ln in enumerate(_wrap(d, line.text, fnt, bx1 - bx0 - 60)[:3]):
        d.text((bx0 + 30, by0 + 62 + i * 54), ln, font=fnt, fill=(255, 255, 255))

    img.convert("RGB").save(out_path)


def render_overlay(
    chars: CharacterConfig,
    out_path: str,
    avatar_a: str | None = None,
    avatar_b: str | None = None,
) -> None:
    """実況用の透過オーバーレイ（左右の隅に2キャラ・中央は透明）。

    元動画の上に重ねて使う。字幕は動画側に焼き込むため、ここには描かない。
    """
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if not chars.show_chars:
        img.save(out_path)  # キャラ非表示（透明のまま）
        return
    av_a = avatar_a or (chars.avatar_a or None)
    av_b = avatar_b or (chars.avatar_b or None)
    # 立ち絵は下端に大きめ、丸顔は隅に小さめ
    _draw_char(img, 170, 545, 78, ACC_A, chars.name_a, True, av_a,
               tachie_bottom=H - 20, tachie_h=360)
    if not chars.single:
        _draw_char(img, W - 170, 545, 78, ACC_B, chars.name_b, True, av_b,
                   tachie_bottom=H - 20, tachie_h=360)
    img.save(out_path)
