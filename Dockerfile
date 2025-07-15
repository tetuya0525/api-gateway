# ==============================================================================
# 3. Dockerfile
# (内容は以前のバージョンから変更ありません)
# ==============================================================================
# ベースイメージ: Python 3.12-slim
FROM python:3.12-slim

# 環境変数: Pythonログのバッファリングを無効化
ENV PYTHONUNBUFFERED True

# 作業ディレクトリを設定
WORKDIR /app

# 依存関係をインストール (ビルドキャッシュ活用)
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ソースコードをコピー
COPY . .

# Cloud RunのPORT環境変数を設定
ENV PORT 8080

# ★★★ エントリーポイント ★★★
# GunicornでFlaskアプリ(main:app)を起動
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "4", "main:app"]
