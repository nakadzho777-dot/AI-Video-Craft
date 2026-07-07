"""AI 実行時ヘルパー.

設定ストア(config_store)とレジストリ(registry)を橋渡しし、
プロバイダー生成とモデル解決を一箇所にまとめる。
ルーターやサービスはこのヘルパー経由で AI を利用する。
"""
from __future__ import annotations

import httpx

from . import registry
from .base import AIProvider
from .config_store import ai_config


def build_provider(provider_id: str | None = None) -> tuple[str, AIProvider]:
    """既定 or 指定の provider_id からインスタンスを生成する。

    Returns: (実際に使う provider_id, インスタンス)
    Raises: KeyError（未知のプロバイダー）
    """
    pid = provider_id or ai_config.default_provider
    cfg = ai_config.get(pid)
    return pid, registry.create(pid, api_key=cfg.api_key, base_url=cfg.base_url)


async def resolve_model(
    provider: AIProvider, provider_id: str, model: str | None
) -> str:
    """使用モデルを決定する（指定 > 既定 > 一覧の先頭）。

    Raises: RuntimeError（利用可能なモデルが無い）
    """
    if model:
        return model
    default = ai_config.get(provider_id).default_model
    if default:
        return default
    try:
        models = await provider.list_models()
    except (httpx.TransportError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
        # モデル一覧取得のネットワーク失敗を分かりやすいエラーにする
        raise RuntimeError(
            "AIサービスに接続できませんでした（モデル一覧の取得に失敗）。"
            "ネットワークを確認して再試行してください。"
        ) from e
    if not models:
        raise RuntimeError("利用可能なモデルがありません")
    return models[0]
