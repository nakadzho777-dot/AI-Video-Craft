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
    owner_user_id: Optional[int] = Field(default=None, index=True)  # 所有アカウント
    title: str = Field(index=True)
    description: str = ""

    production_mode: ProductionMode = ProductionMode.AUTO
    material_mode: MaterialMode = MaterialMode.REQUEST
    status: ProjectStatus = ProjectStatus.PLANNING

    # 企画・台本などは初期段階では JSON 文字列として保持し、
    # 将来的に正規化テーブルへ分離できるようにしておく。
    plan_json: str = ""        # AI企画結果
    script_text: str = ""      # 台本
    materials_json: str = ""   # 素材リスト
    recording_json: str = ""   # 録画ガイド
    edit_plan_json: str = ""   # 編集案
    publish_json: str = ""     # タイトル/説明欄/ハッシュタグ等

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class UsageRecord(SQLModel, table=True):
    """アカウント×日付ごとのAI利用回数（Free版の1日制限に使用）。

    date は "YYYY-MM-DD"（サーバのローカル日付）。
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    date: str = Field(index=True)
    ai_runs: int = 0


# ============================================================
# アカウント / 認証 / ライセンス
# ============================================================


class User(SQLModel, table=True):
    """利用アカウント。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    username: str = ""
    password_hash: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class AuthToken(SQLModel, table=True):
    """ログインセッションのトークン。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(index=True, unique=True)
    user_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow)


class License(SQLModel, table=True):
    """ライセンス（Pro）。

    BOOTHで配布するシリアルキー1つ = 1レコード。
    販売者が発行し、購入者がアカウントに引き換える。
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    plan: str = "pro"
    source: str = "booth"                       # booth | manual | offline_signed
    booth_order_number: Optional[str] = None    # 将来のBOOTH照合用
    max_devices: int = 2                         # 1ライセンス2台まで
    redeemed_by_user_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow)
    redeemed_at: Optional[datetime] = None

    # オフライン署名ライセンス用
    kind: str = "perpetual"                      # perpetual（買い切り）| subscription
    expires_at: Optional[datetime] = None        # subscription の失効日時
    bound_email: str = ""                        # 署名で紐付いたメール

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


class DeviceRegistration(SQLModel, table=True):
    """ライセンスに紐づく登録端末（最大2台）。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    license_id: int = Field(index=True)
    device_id: str = Field(index=True)
    device_name: str = ""
    registered_at: datetime = Field(default_factory=_utcnow)
