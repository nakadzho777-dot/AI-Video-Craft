"""編集提案サービス.

AIプロバイダーへプロンプトを投げ、応答 JSON を EditSuggestion へ構造化する。
"""
from __future__ import annotations

from ..ai.base import AIProvider, ChatMessage
from ..ai.jsonutil import JsonExtractError
from ..ai.structured import chat_json
from ..logging_conf import get_logger
from .materials import KIND_LABEL, material_sources
from .models import (
    AutoEditPlan,
    EditSuggestion,
    MaterialSource,
    StyleProfile,
    SuggestRequest,
)
from .prompts import (
    AUTO_EDIT_SYSTEM_PROMPT,
    STYLE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_auto_edit_prompt,
    build_style_prompt,
    build_user_prompt,
)

logger = get_logger(__name__)


class AutoEditService:
    """自動編集プラン生成（AI）＋無料素材URLの付与。"""

    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def plan(
        self,
        *,
        instructions: str,
        duration_sec: float,
        silence_count: int,
        model: str,
        edit_heavy: bool = False,
    ) -> AutoEditPlan:
        messages = [
            ChatMessage(role="system", content=AUTO_EDIT_SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=build_auto_edit_prompt(
                    instructions, duration_sec, silence_count, edit_heavy
                ),
            ),
        ]
        try:
            data = await chat_json(
                self.provider, messages, model=model, temperature=0.5
            )
        except JsonExtractError as e:
            raise SuggestParseError(str(e)) from e
        try:
            plan = AutoEditPlan.model_validate(data)
        except Exception as e:
            raise SuggestParseError(f"編集プランの形式が不正です: {e}") from e
        # 素材に無料サイトのURLを付与
        for m in plan.materials:
            m.kind_label = KIND_LABEL.get(m.kind, m.kind)
            m.sources = [
                MaterialSource(**s) for s in material_sources(m.kind, m.query)
            ]
        return plan


class SuggestParseError(RuntimeError):
    """AI応答を編集提案として解釈できなかった。"""


class EditingSuggestService:
    """編集提案生成のユースケース。"""

    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def learn_style(
        self, *, creator: str, source: str, notes: str, model: str
    ) -> StyleProfile:
        """参考情報から編集スタイルを言語化する。"""
        messages = [
            ChatMessage(role="system", content=STYLE_SYSTEM_PROMPT),
            ChatMessage(
                role="user", content=build_style_prompt(creator, source, notes)
            ),
        ]
        try:
            data = await chat_json(
                self.provider, messages, model=model, temperature=0.6
            )
        except JsonExtractError as e:
            raise SuggestParseError(str(e)) from e
        # creator が空ならヒントで補完
        if not data.get("creator") and creator:
            data["creator"] = creator
        try:
            return StyleProfile.model_validate(data)
        except Exception as e:
            logger.warning("Style profile validation failed: %s", e)
            raise SuggestParseError(f"スタイルの形式が不正です: {e}") from e

    async def suggest(self, req: SuggestRequest, *, model: str) -> EditSuggestion:
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="user", content=build_user_prompt(req)),
        ]
        try:
            data = await chat_json(
                self.provider, messages, model=model, temperature=0.7
            )
        except JsonExtractError as e:
            raise SuggestParseError(str(e)) from e

        try:
            suggestion = EditSuggestion.model_validate(data)
        except Exception as e:
            logger.warning("Edit suggestion validation failed: %s", e)
            raise SuggestParseError(f"編集提案の形式が不正です: {e}") from e
        return suggestion
