# ==============================================================================
# Memory Library - API Gateway Service (api-gateway)
# main.py (v4.0 / Dialogue Index Integration)
#
# Role:         システムの唯一の公開窓口。UIからのリクエストを受け付け、
#               認証を行い、適切な内部サービスへ安全に転送する。
# Version:      4.0
# Author:       心理 (Thinking Partner)
# Last Updated: 2025-07-16
# ==============================================================================
import os
import requests
import firebase_admin
import google.auth
import google.auth.transport.requests

from functools import wraps
from firebase_admin import auth
from flask import Flask, request, jsonify
from flask_cors import CORS

# --- 初期化 (Initialization) ---
try:
    firebase_admin.initialize_app()
except ValueError:
    pass

app = Flask(__name__)
CORS(app)

# --- 環境変数 ---
# 内部サービスのURLを環境変数から読み込む
ARTICLE_INGEST_SERVICE_URL = os.environ.get("ARTICLE_INGEST_SERVICE_URL")
MANUAL_WORKFLOW_TRIGGER_URL = os.environ.get("MANUAL_WORKFLOW_TRIGGER_URL")
# ★★★【新規】対話インデックスビルダーサービスのURLを追加 ★★★
DIALOGUE_INDEX_BUILDER_URL = os.environ.get("DIALOGUE_INDEX_BUILDER_URL")


# --- 認証デコレーター ---
def firebase_auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"status": "error", "message": "認証エラー: Authorizationヘッダーがありません。"}), 403
        
        id_token = auth_header.split("Bearer ")[1]
        
        try:
            decoded_token = auth.verify_id_token(id_token)
            kwargs['decoded_token'] = decoded_token
        except Exception as e:
            app.logger.error(f"IDトークンの検証に失敗: {e}")
            return jsonify({"status": "error", "message": f"認証エラー: トークンが無効です。"}), 403
            
        return f(*args, **kwargs)
    return decorated_function


# --- サービス間認証トークン生成 ---
def get_service_to_service_token(audience_url):
    try:
        auth_req = google.auth.transport.requests.Request()
        id_token = google.oauth2.id_token.fetch_id_token(auth_req, audience_url)
        return id_token
    except Exception as e:
        app.logger.error(f"サービス間認証トークンの生成に失敗: {e}")
        return None


# --- ルーティング (Routing) ---

# ... (既存の /dispatch/article と /dispatch/workflow は変更なし) ...

@app.route("/dispatch/article", methods=["POST"])
@firebase_auth_required
def dispatch_article(decoded_token):
    if not ARTICLE_INGEST_SERVICE_URL:
        return jsonify({"status": "error", "message": "設定エラー: ARTICLE_INGEST_SERVICE_URLが未設定です。"}), 500
    service_token = get_service_to_service_token(ARTICLE_INGEST_SERVICE_URL)
    if not service_token:
        return jsonify({"status": "error", "message": "ゲートウェイ内部エラー: サービス間認証に失敗しました。"}), 500
    try:
        headers = {'Authorization': f'Bearer {service_token}', 'Content-Type': 'application/json'}
        response = requests.post(url=ARTICLE_INGEST_SERVICE_URL, headers=headers, data=request.get_data(), timeout=30)
        response.raise_for_status()
        return response.json(), response.status_code
    except requests.exceptions.RequestException as e:
        app.logger.error(f"article-ingest-serviceへの転送に失敗: {e}")
        return jsonify({"status": "error", "message": "下流サービスへの接続に失敗しました。"}), e.response.status_code if e.response else 503

@app.route("/dispatch/workflow", methods=["POST"])
@firebase_auth_required
def dispatch_workflow(decoded_token):
    if not MANUAL_WORKFLOW_TRIGGER_URL:
        return jsonify({"status": "error", "message": "設定エラー: MANUAL_WORKFLOW_TRIGGER_URLが未設定です。"}), 500
    service_token = get_service_to_service_token(MANUAL_WORKFLOW_TRIGGER_URL)
    if not service_token:
        return jsonify({"status": "error", "message": "ゲートウェイ内部エラー: サービス間認証に失敗しました。"}), 500
    try:
        headers = {'Authorization': f'Bearer {service_token}', 'Content-Type': 'application/json'}
        response = requests.post(url=MANUAL_WORKFLOW_TRIGGER_URL, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json(), response.status_code
    except requests.exceptions.RequestException as e:
        app.logger.error(f"manual-workflow-triggerへの転送に失敗: {e}")
        return jsonify({"status": "error", "message": "下流サービスへの接続に失敗しました。"}), e.response.status_code if e.response else 503


# ★★★【新規】対話インデックス構築のエンドポイント ★★★
@app.route("/dispatch/build-index", methods=["POST"])
@firebase_auth_required
def dispatch_build_index(decoded_token):
    """
    [認証必須] UIからの対話インデックス構築リクエストを、
    内部の dialogue-index-builder へ転送する。
    """
    if not DIALOGUE_INDEX_BUILDER_URL:
        return jsonify({"status": "error", "message": "設定エラー: 転送先URL(DIALOGUE_INDEX_BUILDER_URL)が未設定です。"}), 500

    service_token = get_service_to_service_token(DIALOGUE_INDEX_BUILDER_URL)
    if not service_token:
        return jsonify({"status": "error", "message": "ゲートウェイ内部エラー: サービス間認証に失敗しました。"}), 500

    try:
        headers = {
            'Authorization': f'Bearer {service_token}',
            'Content-Type': 'application/json'
        }
        
        # インデックス構築は時間がかかる可能性があるため、タイムアウトを長めに設定
        response = requests.post(
            url=DIALOGUE_INDEX_BUILDER_URL,
            headers=headers,
            timeout=120 
        )
        response.raise_for_status()
        return response.json(), response.status_code

    except requests.exceptions.RequestException as e:
        app.logger.error(f"dialogue-index-builderへの転送に失敗: {e}")
        status_code = e.response.status_code if e.response else 503
        return jsonify({"status": "error", "message": f"下流サービスへの接続に失敗しました。"}), status_code


# Gunicornから直接実行されるためのエントリーポイント
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
