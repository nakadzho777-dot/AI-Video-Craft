"""AI プロバイダー レジストリ.

プロバイダー実装クラスを登録し、id から生成する。
「交換・追加しやすいインターフェース設計」の中心。
"""
from __future__ import annotations

from typing import Type

from ..logging_conf import get_logger
from .base import AIProvider, ProviderInfo

logger = get_logger(__name__)

_registry: dict[str, Type[AIProvider]] = {}


def register(provider_cls: Type[AIProvider]) -> Type[AIProvider]:
    """プロバイダークラスを登録するデコレータ / 関数。"""
    pid = provider_cls.id
    if not pid:
        raise ValueError(f"Provider {provider_cls!r} has empty id")
    if pid in _registry:
        logger.warning("Provider id '%s' is being overwritten", pid)
    _registry[pid] = provider_cls
    logger.debug("Registered AI provider '%s'", pid)
    return provider_cls


def available_ids() -> list[str]:
    return list(_registry.keys())


def create(
    provider_id: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> AIProvider:
    """id からプロバイダーインスタンスを生成する。"""
    if provider_id not in _registry:
        raise KeyError(
            f"Unknown AI provider '{provider_id}'. "
            f"Available: {', '.join(_registry) or '(none)'}"
        )
    return _registry[provider_id](api_key=api_key, base_url=base_url)


def list_infos() -> list[ProviderInfo]:
    """全プロバイダーのメタ情報を返す（設定画面用）。"""
    infos: list[ProviderInfo] = []
    for cls in _registry.values():
        # メタ情報取得のみのため、鍵なしで一時生成
        infos.append(cls().info())
    return infos


def load_builtin_providers() -> None:
    """組み込みプロバイダーを読み込む（import 副作用で register される）。"""
    from .providers import (  # noqa: F401
        claude_provider,
        gemini_provider,
        ollama_provider,
        openai_provider,
    )

    logger.info("Loaded AI providers: %s", ", ".join(available_ids()))
