# 本番デプロイ手順（方式A+Bハイブリッド）

決済で自動発行(B)しつつ、署名トークンでオフライン対応(A)する構成の本番手順です。

## 価格（既定）

| プラン | 価格 | Stripe価格の種別 | マッピング環境変数 |
| --- | --- | --- | --- |
| Free | ¥0 | — | — |
| Pro 買い切り | ¥2,980（ローンチ） | 一括 (one-time) | `AIVC_STRIPE_PRICE_PERPETUAL` |
| Pro サブスク | ¥380 / 月 | 継続 (recurring) | `AIVC_STRIPE_PRICE_SUBSCRIPTION` |

---

## ① 署名鍵を生成（1回だけ）

```bash
cd backend
python scripts/keygen.py init
```
出力の `AIVC_LICENSE_PUBLIC_KEY`（公開）と `AIVC_LICENSE_PRIVATE_KEY`（秘密）を控える。
- **公開鍵** → サーバ環境変数 + アプリのビルド設定（両方に同じ値）
- **秘密鍵** → サーバ環境変数のみ（配布物には絶対に入れない）

## ② Stripe を準備（テストモードで開始）

1. [dashboard.stripe.com](https://dashboard.stripe.com) でシークレットキー `sk_test_...` を取得
2. 商品と価格を作成（通貨 JPY）
   - 買い切り: 一括 ¥2,980 → `price_...`
   - サブスク: 継続（月次）¥380 → `price_...`
3. Webhook を登録: エンドポイント `https://<公開URL>/billing/webhook`、イベント
   `checkout.session.completed` / `invoice.paid` / `customer.subscription.deleted`
   → 署名シークレット `whsec_...` を控える

## ③ バックエンドをデプロイ（Docker）

`backend/Dockerfile` をそのまま使えます（Render / Railway / Fly.io など）。

```bash
# 例: ローカルで動作確認
cd backend
docker build -t aivc-backend .
docker run -p 8756:8756 --env-file .env -v aivc-data:/data aivc-backend
```

環境変数は `backend/.env.example` を参照して設定（②③④の値）。
データ永続化のため `/data` にボリュームをマウントすること（SQLite）。規模拡大時は Postgres 化を検討。

デプロイ後の**公開URL**（例 `https://api.your-domain.com`）を控える。

## ④ 配布アプリをビルド（接続先・公開鍵を埋め込み）

```bash
cd frontend
# .env.production.example をコピーして値を設定
#   AIVC_BACKEND_URL=https://api.your-domain.com
#   AIVC_LICENSE_PUBLIC_KEY=<①の公開鍵>
cp .env.production.example .env.production   # 値を編集
npm run build
```
`vite.config.ts` がビルド時に接続先URLと公開鍵を埋め込みます。CSP は https 接続を許可済み。

## ⑤ テスト（実課金なし）

- アプリで「決済して購入」→ Stripe のテストカード `4242 4242 4242 4242`（期限は未来・CVC任意）
- 支払い後、Webhook 経由で自動的に Pro 化されることを確認
- ローカル確認は Stripe CLI: `stripe listen --forward-to localhost:8756/billing/webhook`

## ⑥ 本番切替

Stripe を本番モードにし、`sk_live_...` / 本番 Price / 本番 Webhook に差し替え。
鍵・URL も本番用に更新して再ビルド。

---

### セキュリティ要点
- 秘密鍵（署名・Stripe）は**サーバのみ**。配布アプリには公開鍵と接続先URLのみ。
- 認証は Bearer トークン（Cookie不使用）。CORS は任意オリジン許可・資格情報無効。
- Webhook は HMAC 署名検証済み。改ざん・偽リクエストは 400 で拒否。
