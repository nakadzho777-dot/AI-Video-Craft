"""決済（方式B: Stripe 自動発行）.

Stripe Checkout で購入 → Webhook を受けてライセンスを自動発行する。
外部SDKは使わず httpx + 標準ライブラリ(hmac) で実装。
"""
