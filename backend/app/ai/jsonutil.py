"""AI応答からの JSON 抽出ユーティリティ.

企画・録画ガイドなど、AIに構造化 JSON を出力させる機能で共通利用する。
素のJSON / コードフェンス付き / 前後に文章、のいずれにも対応する。
"""
from __future__ import annotations

import json
import re


class JsonExtractError(RuntimeError):
    """AI応答から JSON を抽出できなかった。"""


def extract_json(text: str) -> dict:
    """AI応答テキストから最初の JSON オブジェクトを抽出する。"""
    text = text.strip()

    # 1) そのまま JSON として読めるか
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2) ```json ... ``` フェンスの中身
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # 3) 最初の { から最後の } までを試す
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise JsonExtractError("AI応答からJSONを抽出できませんでした")
