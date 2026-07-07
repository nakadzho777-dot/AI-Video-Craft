"""無料素材サイトのURL提示.

AIが提案した素材（BGM/効果音/画像/動画）について、著作権に配慮し
「無料で使えるサイトの検索/トップURL」を返す（ファイル自体は落とさない）。
"""
from __future__ import annotations

from urllib.parse import quote


def material_sources(kind: str, query: str = "") -> list[dict]:
    """素材ごとに候補を3つ返す。できるだけキーワードの結果へ直接飛べるURLにする。

    先頭は Pixabay（BGM/効果音/画像/動画すべて対応・商用可・各結果ページで直接DL可）で、
    キーワード検索URLにより目的の素材へ直接ジャンプする。以降は日本語の定番サイト。
    """
    q = quote((query or "").strip())

    def px(path_search: str, path_top: str) -> str:
        return f"https://pixabay.com/{path_search}/{q}/" if q else f"https://pixabay.com/{path_top}/"

    if kind == "bgm":
        return [
            {"site": "Pixabay 音楽（商用可・直接DL）", "url": px("music/search", "music")},
            {"site": "DOVA-SYNDROME（無料BGM・商用可）", "url": "https://dova-s.jp/"},
            {"site": "甘茶の音楽工房（無料BGM）", "url": "https://amachamusic.chagasi.com/"},
        ]
    if kind == "se":
        return [
            {"site": "Pixabay 効果音（商用可・直接DL）", "url": px("sound-effects/search", "sound-effects")},
            {"site": "効果音ラボ（無料効果音）", "url": "https://soundeffect-lab.info/"},
            {"site": "魔王魂（効果音）", "url": "https://maou.audio/se/"},
        ]
    if kind == "image":
        return [
            {"site": "Pixabay 画像（商用可・直接DL）", "url": px("ja/images/search", "ja/images")},
            {
                "site": "いらすとや（無料イラスト）",
                "url": f"https://www.irasutoya.com/search?q={q}" if q else "https://www.irasutoya.com/",
            },
            {
                "site": "Pexels 画像（商用可）",
                "url": f"https://www.pexels.com/ja-jp/search/{q}/" if q else "https://www.pexels.com/ja-jp/",
            },
        ]
    if kind == "video":
        return [
            {"site": "Pixabay 動画（商用可・直接DL）", "url": px("ja/videos/search", "ja/videos")},
            {
                "site": "Pexels 動画（商用可）",
                "url": f"https://www.pexels.com/ja-jp/search/videos/{q}/" if q else "https://www.pexels.com/ja-jp/videos/",
            },
            {
                "site": "Mixkit 動画（無料・商用可）",
                "url": f"https://mixkit.co/free-stock-video/?q={q}" if q else "https://mixkit.co/free-stock-video/",
            },
        ]
    return []


# 種別の日本語ラベル
KIND_LABEL = {"bgm": "BGM", "se": "効果音", "image": "画像/イラスト", "video": "動画素材"}
