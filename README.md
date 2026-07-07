# AI VideoCraft

AI と人間が協力して動画を制作するデスクトップアプリ。
企画・台本・素材整理・録画支援・編集支援・投稿準備までを一括で支援します。

> このリポジトリは設計書 Ver.0.1 に基づく **初期雛形（スケルトン）** です。
> 拡張しやすい設計を最優先に、UI / バックエンド / AI / 動画処理 / データを明確に分離しています。

---

## アーキテクチャ概要

```
┌────────────────────────────┐        HTTP (localhost)        ┌────────────────────────────┐
│  Frontend (Electron)       │  ───────────────────────────▶ │  Backend (FastAPI)         │
│  React + TypeScript        │  ◀─────────────────────────── │  Python                    │
│                            │                                │                            │
│  - pages/ (画面)           │                                │  - routers/  (API層)       │
│  - api/    (通信層)        │                                │  - ai/       (AI抽象化)    │
│  - components/             │                                │  - video/    (FFmpeg)      │
│                            │                                │  - db/       (SQLite)      │
│                            │                                │  - license/  (認証)        │
└────────────────────────────┘                                └────────────────────────────┘
```

設計上の分離境界:

| レイヤ        | ディレクトリ            | 責務                                        |
| ------------- | ----------------------- | ------------------------------------------- |
| UI            | `frontend/src`          | 画面表示・ユーザー操作                      |
| API           | `backend/app/routers`   | HTTP エンドポイント                         |
| AI 処理       | `backend/app/ai`        | プロバイダー抽象化・切替（交換可能）        |
| 動画処理      | `backend/app/video`     | FFmpeg ラッパー（交換可能）                 |
| データ        | `backend/app/db`        | SQLite / モデル定義                         |
| ライセンス    | `backend/app/license`   | Free / Pro 認証                             |
| 設定・ログ    | `backend/app/config.py` | 設定管理・ロギング                          |

AI プロバイダー（Ollama / OpenAI / Gemini / Claude）は共通インターフェース
`AIProvider` を実装し、`registry` に登録するだけで追加できます。

---

## 必要環境

- Node.js 20+
- Python 3.11+
- FFmpeg（PATH に通っていること。動画処理を使う場合）

---

## セットアップ

### バックエンド

```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8756
```

起動後、http://localhost:8756/docs で API ドキュメントを確認できます。

### フロントエンド

```bash
cd frontend
npm install
npm run dev        # Vite 開発サーバ + Electron を起動
```

---

## 現状の実装範囲（雛形）

- [x] モジュール分離されたディレクトリ構成
- [x] FastAPI 起動 + ヘルスチェック
- [x] AI プロバイダー抽象化（Ollama / OpenAI / Gemini / Claude のスタブ）
- [x] SQLite + プロジェクトモデルの CRUD 土台
- [x] **プラン制限の実適用**（Free/Pro）
- [x] FFmpeg ラッパーのインターフェース
- [x] ライセンス管理（Free / Pro）の土台
- [x] Electron + React + TS の最小 UI（モード選択・設定・チャット）
- [x] **AI企画**（タイトル・構成・尺配分・掴み・CTA・サムネイル案の生成 → プロジェクト保存）
- [x] **録画支援**（企画を元に録画ガイド生成 → ステップ実行モード + **自動画面録画**）
- [x] **編集支援**（AI編集提案: カット/テロップ/BGM/テンポ/ショート化 + 編集スタイル学習 + FFmpeg: 無音検出/音量/縦動画/書き出し）
- [x] **投稿支援**（YouTubeタイトル/説明欄/ハッシュタグ/固定コメント + X/Instagram/TikTok/BOOTH投稿文、各テキストにコピー機能）

**初期優先機能（AI企画・録画支援・編集支援・投稿支援）がすべて実装完了しました。**
企画 → 録画 → 編集 → 投稿 の一連の流れを、プロジェクト単位で保存しながら進められます。

### アカウント / ログイン / ライセンス

- **アカウント制**: メール+パスワードで登録・ログイン（`/auth/*`）。パスワードは stdlib pbkdf2 でハッシュ化、トークン認証。
- **アカウントごとに保持**: プロジェクト・AI利用状況・プランはすべて **ユーザー単位**。未ログインではAI機能は 401。
- **BOOTHライセンス（キー方式）**: BOOTHには第三者向け購入検証APIが無いため、実際のBOOTHデジタル販売と同じ **ライセンスキー配布方式** を採用:
  1. 販売者が設定画面（開発モード）でキーを**発行** → BOOTHの商品にシリアル/ファイルとして登録
  2. 購入者がBOOTHで購入しキーを受け取る
  3. アプリで**引き換え**（`/license/redeem`）→ Pro化。**1ライセンス2台まで**端末登録、PC変更時は解除して再登録
  - 将来BOOTHが注文APIを公開した際に照合できるよう `booth_order_number` の継ぎ目を用意。

### オフライン署名ライセンス（方式A・買い切り/サブスク）— サーバ不要で単体販売

BOOTH等の販売サイトに依存せず、**Ed25519署名**でライセンスを配布できます。

- **仕組み**: アプリに**公開鍵**を埋め込み、販売者が**秘密鍵**で `{email, plan, kind, exp}` を署名。買い手はメール＋トークンを貼り付け、アプリが**オフライン検証**。
- **買い切り(perpetual)**: 無期限。 **サブスク(subscription)**: 期限付き、切れると自動でFreeに戻る（`plan_for_user` が失効判定）。
- **メール紐付け**: 署名の `email` とログイン中アカウントのメールが一致しないと有効化不可（コピー耐性）。
- **改ざん検知**: 署名が壊れると拒否。 **時計巻き戻し対策**: `last_seen` を記録し `effective_now` を単調化（`app/license/clock.py`）。

**販売者の運用（購入のたび）**:
```bash
# 最初の1回だけ: 鍵ペア生成 → 公開鍵をアプリに、秘密鍵を手元に
python scripts/keygen.py init

# 購入ごと: 入金確認 → メールに紐づけて署名発行 → 買い手へメール送付
export AIVC_LICENSE_PRIVATE_KEY=...   # 手元の秘密鍵
python scripts/keygen.py sign --email buyer@example.com --kind perpetual
python scripts/keygen.py sign --email buyer@example.com --kind subscription --days 365
```
アプリの設定→ライセンス（開発モード）からGUIでも署名発行できます。
公開/秘密鍵は環境変数 `AIVC_LICENSE_PUBLIC_KEY` / `AIVC_LICENSE_PRIVATE_KEY` で設定
（未設定時は同梱DEV鍵。**実販売前に必ず自分の鍵へ差し替え**）。

**サブスク更新リマインド**: 期限7日前から画面上部に警告バナー、切れると「更新して再有効化」を促す
（`/settings/usage` が `license_expires_in_days` を返す）。

**本番鍵への差し替え支援**: 同梱DEV鍵を使用中は設定画面に警告を表示。「本番鍵を生成」ボタン
（開発モード）で鍵ペアを生成し、環境変数の設定手順とともに公開鍵/秘密鍵を表示（`keygen.py init` のGUI版）。

**購入通知メール**: 買い手が設定→ライセンスで「購入をリクエスト」すると、販売者
（既定 `nakadzho777@gmail.com`、`AIVC_NOTIFY_EMAIL` で変更）へ購入者メール・希望プランが届く。
- **SMTP設定時**（`AIVC_SMTP_HOST/PORT/USER/PASSWORD`。Gmailはアプリパスワード）→ 自動送信
- **未設定時** → 買い手のメールソフトを `mailto:` で開き、本人が送信（認証情報不要・安全）

  各PCでローカル動作するため、配布ビルドにSMTP認証情報を埋め込むと漏洩します。
  自分で1インスタンス運用する場合のみSMTPを設定し、配布アプリでは mailto フォールバックを推奨。

> 制約: サーバが無いため端末台数の厳密制限と即時失効(revoke)は不可（サブスクは期限で対処）。
> 「買って即・完全自動発行」まで求める場合は決済Webhook（自己ホスト）方式が別途必要です。

### 方式B: Stripe 決済で自動発行（手作業ゼロ）

買い手が決済すると、**Webhookを受けてサーバがライセンスを自動発行**し、即Pro化します
（署名の手作業が不要）。外部SDKなし（httpx + 標準ライブラリ hmac で実装）。

**フロー**: アプリで「決済して購入」→ Stripe Checkout で支払い →
`checkout.session.completed` Webhook → 対象アカウントを自動Pro化。
サブスクは `invoice.paid`（更新で期限延長）/ `customer.subscription.deleted`（解約でFree化）に対応。

**⚠️ 前提**:
- **バックエンドの公開ホスティングが必須**（Webhookがインターネットから届く必要がある）。
  各PCローカルではなく、クラウドに1つ設置しアプリをそこへ向ける。ローカル開発は Stripe CLI で
  `stripe listen --forward-to localhost:8756/billing/webhook` を使う。
- **Stripe アカウント**（テストキーは即発行・無料。実課金なしに全フロー確認可）。

**セットアップ**（環境変数）:
```bash
AIVC_STRIPE_SECRET_KEY=sk_test_...          # Stripe シークレットキー
AIVC_STRIPE_WEBHOOK_SECRET=whsec_...        # Webhook 署名シークレット
AIVC_STRIPE_PRICE_PERPETUAL=price_...       # 買い切り(一括)用の Price ID
AIVC_STRIPE_PRICE_SUBSCRIPTION=price_...    # サブスク(継続)用の Price ID
AIVC_BILLING_SUCCESS_URL=https://.../thanks
```
Stripeダッシュボードで一括課金と継続課金の Price を作成し、Webhookの宛先を
`https://<公開URL>/billing/webhook` に設定します。未設定なら決済機能は自動的にオフになり、
アプリは方式A（購入リクエスト＋オフライン署名）にフォールバックします。

### A+Bハイブリッド（自動発行 × オフライン対応）

決済(B)で自動発行しつつ、**サーバが署名したオフライン利用トークン(A)も同時に発行**し、
アプリがキャッシュします。バックエンドに接続できないときは、**アプリが埋め込んだ公開鍵で
そのトークンを検証**してPro状態を維持します（`electron/main.ts` の Ed25519 検証をIPCで提供）。

- 決済/更新のたびにサーバがトークンを再発行（`GET /license/offline-token`）、解約で無効化
- アプリ: オンライン時にトークン＋アカウントをキャッシュ、`/auth/me` 失敗時はキャッシュを
  オフライン検証してPro継続（「📴 オフラインモード」バナー表示）

### プラン制限（Free / Pro）— 実適用済み

Free版の制限が実際に機能します（`LicenseManager.limits` で一元管理、超過時は 402）:

| 制限 | Free | 適用箇所 |
|---|---|---|
| プロジェクト数 | 1件 | 作成時 |
| AI制作（企画/録画/編集提案/投稿） | 1日5回 | 生成時に日次カウント（`DailyUsage`）|
| 無料AIのみ（有料API不可） | Ollama等ローカルのみ | 全AI生成（チャット含む）|
| 書き出し解像度 | 720p | `/editing/export` |
| 動画の長さ | 5分 | `/editing/export`（probe後）|
| 高度編集（縦動画化/ショート） | 不可 | `/editing/export` の vertical |

- 本日の利用状況は `GET /settings/usage`。UIはサイドバーの利用バーと設定の「現在のプラン」で表示。
- Pro版（ライセンスキー `AIVC-PRO-*`）はすべて無制限/許可。

### 編集スタイル学習（好きな人の編集に寄せる）

- 参考にしたい**YouTube等のURL・クリエイター名・好きな編集の特徴**を入力すると、
  AIがそのスタイルを言語化した「スタイルプロファイル」を作成（`/editing/learn-style`）。
- 以降の**AI編集提案がそのスタイルに寄せて**生成される（カット/テロップ/BGM/テンポ/掴み）。
- URL指定時は YouTube の公開 oEmbed（投稿者名・タイトル）を手がかりに使用。
  ※ 動画そのものの視聴・ダウンロード・機械学習は行わない（スタイルの言語的モデル化）。

### AI企画の使い方

1. 「設定」で利用する AI プロバイダーを設定（Ollama はローカル起動、他は APIキー）。
2. 「AI企画」でテーマを入力し、フォーマット（ショート/通常/おまかせ）を選んで生成。
3. 保存先プロジェクトを選ぶと企画が `plan_json` に保存され、ステータスが素材フェーズへ進む。

`backend/app/planning/` に企画ロジックを分離。AI プロバイダーには依存せず、
`ai/runtime.py` 経由で任意のプロバイダー/モデルを利用できる。

初期バージョン優先機能: **AI企画・録画支援・編集支援・投稿支援**。
自動録画や高度な自動編集は将来機能として拡張できる構造にしています。
