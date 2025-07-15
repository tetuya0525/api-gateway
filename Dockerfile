# ==============================================================================
# 3. Dockerfile (v2.1 最終版)
# Gunicornのワーカー数とタイムアウト設定を、Cloud Run環境に最適化しました。
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

# ★★★ エントリーポイント (最終版) ★★★
# ワーカー数を「CPUコア数 x 2 + 1」の推奨値に近い3に調整し、
# タイムアウトを60秒に延長して、安定性を向上させます。
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "3", "--timeout", "60", "main:app"]
