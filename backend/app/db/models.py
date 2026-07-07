"""データモデル定義.

動画1本ごとに Project を作成し、企画・台本・素材・編集案・投稿情報などを保持する。
まずは中核となる Project を定義し、詳細エンティティは今後分割して追加する。
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProductionMode(str, Enum):
    """制作モード。"""

    AUTO = "auto"        # AIおまかせ
    ASSIST = "assist"    # AIサポート
    MANUAL = "manual"    # 手動制作


class MaterialMode(str, Enum):
    """素材モード。"""

    PROVIDE = "provide"  # ユーザーが素材を渡す
    REQUEST = "request"  # AIが素材を要求する


class ProjectStatus(str, Enum):
    PLANNING = "planning"
    MATERIALS = "materials"
    RECORDING = "recording"
    EDITING = "editing"
    PUBLISHING = "publishing"
    DONE = "done"


class Project(SQLModel, table=True):
    """動画プロジェクト。

    設計書の「保存する内容」は段階的にフィールド/関連テーブルへ展開する。
    現段階では中核メタデータのみを保持する。
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: str = Field(default="", index=True)  # 所有PC（デバイス単位）
    title: str = Field(index=True)
    description: str = ""

    production_mode: ProductionMode = ProductionMode.AUTO
    material_mode: MaterialMode = MaterialMode.REQUEST
    status: ProjectStatus = ProjectStatus.PLANNING

    # 企画・台本などは初期段階では JSON 文字列として保持し、
    # 将来的に正規化テーブルへ分離できるようにしておく。
    plan_json: str = ""        # AI企画結果（決定した最新の企画）
    plan_history_json: str = ""  # 決定済み企画の履歴（別バリエーション生成用）
    script_text: str = ""      # 台本
    materials_json: str = ""   # 素材リスト
    recording_json: str = ""   # 録画ガイド
    edit_plan_json: str = ""   # 編集案
    publish_json: str = ""     # タイトル/説明欄/ハッシュタグ等

    # 目標の完成尺（秒）。録画で決めて編集でも共有する。0=未設定。
    target_duration_sec: float = 0

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class UsageRecord(SQLModel, table=True):
    """デバイス×日付ごとのAI利用回数（Free版の1日制限に使用）。

    date は "YYYY-MM-DD"（サーバのローカル日付）。
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: str = Field(default="", index=True)
    date: str = Field(index=True)
    ai_runs: int = 0


# ============================================================
# ライセンス（PC/デバイス単位）
# ============================================================


class License(SQLModel, table=True):
    """ライセンス（Pro）。PC（デバイス）単位で管理する。

    署名ライセンス(方式A) / Stripe決済(方式B) のいずれも device_id に紐づく。
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    plan: str = "pro"
    source: str = "manual"                      # manual | offline_signed | stripe
    device_id: str = Field(default="", index=True)  # 紐づくPC
    created_at: datetime = Field(default_factory=_utcnow)
    redeemed_at: Optional[datetime] = None

    # 種別・失効
    kind: str = "perpetual"                      # perpetual（買い切り）| subscription
    expires_at: Optional[datetime] = None        # subscription の失効日時

    # Stripe 決済（方式B）
    stripe_subscription_id: Optional[str] = Field(default=None, index=True)
    stripe_customer_id: Optional[str] = None

    # A+Bハイブリッド: サーバが署名したオフライン利用トークン（アプリがキャッシュ）
    signed_token: str = ""


class AppState(SQLModel, table=True):
    """アプリ状態のキー/値（時計巻き戻し対策の last_seen など）。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    value: str = ""
    registered_at: datetime = Field(default_factory=_utcnow)
