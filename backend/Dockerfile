# AI VideoCraft バックエンド（ライセンス/決済サーバ）
# Render / Railway / Fly.io などにそのままデプロイできます。
FROM python:3.12-slim

WORKDIR /app

# 依存関係
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリ本体
COPY app ./app
COPY scripts ./scripts

# データ/ログは /data に置く（永続化するにはボリュームをマウント）
ENV AIVC_DATA_DIR=/data \
    AIVC_DB_PATH=/data/videocraft.sqlite3 \
    AIVC_LOG_DIR=/data/logs
VOLUME ["/data"]

EXPOSE 8756

# クラウドが渡す $PORT があればそれを使う
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8756}"]
