# 決済テスト手順（Stripe テストモード）

インストーラー版アプリ → ローカルバックエンド（localhost:8756）→ Stripe テスト決済 →
Webhook でこのPCが自動的に Pro 化される、という一連の流れをテストします。

> インストーラー: `C:\Users\nakad\aivc-release\AI VideoCraft Setup 0.1.0.exe`
> このビルドはバックエンド URL が `http://localhost:8756` です。テスト中はローカルの
> バックエンドを起動しておく必要があります。

---

## 0. 事前準備（初回のみ）

### a) Stripe CLI をインストール（Webhook をローカルに転送するため）
- https://github.com/stripe/stripe-cli/releases から Windows 版 `stripe_X.Y.Z_windows_x86_64.zip` を取得
- 解凍して `stripe.exe` を PATH の通った場所（例: `C:\Windows` や任意のフォルダ＋PATH追加）に置く
- 動作確認: PowerShell で `stripe version`

### b) Stripe をテストモードにして価格を用意
1. https://dashboard.stripe.com/test/ にログイン（右上が「テストモード」になっていること）
2. **商品** → 新規作成
   - 買い切り: 価格タイプ「一括」 ¥2,980 → 生成された `price_...` をメモ
   - サブスク: 価格タイプ「継続」月額 ¥380 → 生成された `price_...` をメモ
3. **開発者 → APIキー** の「シークレットキー（`sk_test_...`）」をメモ

---

## 1. Stripe CLI で Webhook 転送を開始

新しい PowerShell を開いて:

```powershell
stripe login          # 初回のみ。ブラウザで承認
stripe listen --forward-to localhost:8756/billing/webhook
```

表示される **`whsec_...`**（Webhook signing secret）をコピー。
※このウィンドウは決済テスト中つけっぱなしにします。

---

## 2. バックエンドに Stripe テストキーを設定

`backend\.env` を開いて、1・0で控えた値を貼り付けます:

```ini
AIVC_DEV_MODE=1
AIVC_STRIPE_SECRET_KEY=sk_test_あなたの値
AIVC_STRIPE_WEBHOOK_SECRET=whsec_手順1で表示された値
AIVC_STRIPE_PRICE_PERPETUAL=price_買い切りの値
AIVC_STRIPE_PRICE_SUBSCRIPTION=price_サブスクの値
```

（`backend\.env` は Git 管理外なのでキーが外部に出ることはありません）

---

## 3. バックエンドを（再）起動

別の PowerShell で:

```powershell
cd C:\Users\nakad\OneDrive\Desktop\q\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8756
```

起動確認:
```powershell
curl http://localhost:8756/billing/config
# => {"stripe_enabled": true, "perpetual_available": true, "subscription_available": true}
```
`stripe_enabled` が **true** ならOK。

---

## 4. アプリで決済テスト

1. `AI VideoCraft Setup 0.1.0.exe` を実行してインストール → アプリ起動
2. **設定 → ライセンス** を開く
3. プラン（買い切り or サブスク）を選び **「決済して購入」**
4. 既定ブラウザで Stripe の決済ページが開く → テストカードで支払い:
   - カード番号: `4242 4242 4242 4242`
   - 有効期限: 任意の未来（例 `12/34`）／ CVC: 任意（例 `123`）／ 郵便番号: 任意
5. 支払い完了後、アプリに戻ると **数秒で自動的に Pro 表示**に切り替わります
   （アプリが裏でライセンス状態をポーリングしています）

---

## 5. 確認ポイント

- **Stripe CLI ウィンドウ**: `checkout.session.completed` などのイベントが `[200]` で流れる
- **バックエンドのログ**: `stripe webhook: checkout.session.completed -> ...`
- **アプリ**: サイドバーの表示が「Free プラン」→「Pro プラン」に変化
- **サブスクの場合**: `invoice.paid` で期限更新、Stripe 側で解約 → `customer.subscription.deleted`
  が届くと Free に戻る（テストは Stripe ダッシュボードのサブスク画面から解約で確認可）

### うまくいかないとき
- `stripe_enabled: false` → `.env` の値が空／バックエンド未再起動。3をやり直し
- 決済ページが開かない → アプリを一度終了して再起動（Electron の外部リンク許可の反映）
- 支払ったのに Pro にならない → CLI ウィンドウで Webhook が `[400]` になっていないか確認
  （`whsec_...` が `.env` の値と一致しているか、バックエンドを再起動したか）

---

## 本番（実販売）に切り替えるとき
- Stripe を**本番モード**に切り替え、`sk_live_...` と本番 `price_...` を使用
- Webhook はクラウド（Render 等）の公開 URL に設定（`https://<your-app>/billing/webhook`）
- アプリは `AIVC_BACKEND_URL=https://<your-app>` を指定して再ビルド（`npm run dist`）
- 署名ライセンス（方式A）の DEV 鍵も本番鍵に差し替え（設定→ライセンス→本番鍵を生成）
