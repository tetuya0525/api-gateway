# ==============================================================================
# Memory Library - API Gateway Service (api-gateway)
# main.py (v5.0 / Tag Management Integration)
#
# Role:         システムの唯一の公開窓口。UIからのリクエストを受け付け、
#               認証を行い、適切な内部サービスへ安全に転送する。
# Version:      5.0
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
ARTICLE_INGEST_SERVICE_URL = os.environ.get("ARTICLE_INGEST_SERVICE_URL")
MANUAL_WORKFLOW_TRIGGER_URL = os.environ.get("MANUAL_WORKFLOW_TRIGGER_URL")
DIALOGUE_INDEX_BUILDER_URL = os.environ.get("DIALOGUE_INDEX_BUILDER_URL")
# ★★★【新規】タグ管理サービスのURLを追加 ★★★
TAG_MANAGEMENT_SERVICE_URL = os.environ.get("TAG_MANAGEMENT_SERVICE_URL")


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


# --- 汎用ディスパッチ関数 ---
def dispatch_request(target_url_env_var, audience_url, timeout=60):
    if not audience_url:
        return jsonify({"status": "error", "message": f"設定エラー: {target_url_env_var}が未設定です。"}), 500
    
    service_token = get_service_to_service_token(audience_url)
    if not service_token:
        return jsonify({"status": "error", "message": "ゲートウェイ内部エラー: サービス間認証に失敗しました。"}), 500

    try:
        headers = {'Authorization': f'Bearer {service_token}', 'Content-Type': 'application/json'}
        response = requests.post(
            url=audience_url,
            headers=headers,
            data=request.get_data(), # UIからのリクエストボディをそのまま転送
            timeout=timeout
        )
        response.raise_for_status()
        return response.json(), response.status_code
    except requests.exceptions.RequestException as e:
        app.logger.error(f"{audience_url}への転送に失敗: {e}")
        status_code = e.response.status_code if e.response else 503
        return jsonify({"status": "error", "message": f"下流サービスへの接続に失敗しました。"}), status_code


# --- ルーティング (Routing) ---

@app.route("/dispatch/article", methods=["POST"])
@firebase_auth_required
def dispatch_article(decoded_token):
    return dispatch_request("ARTICLE_INGEST_SERVICE_URL", ARTICLE_INGEST_SERVICE_URL, timeout=30)

@app.route("/dispatch/workflow", methods=["POST"])
@firebase_auth_required
def dispatch_workflow(decoded_token):
    return dispatch_request("MANUAL_WORKFLOW_TRIGGER_URL", MANUAL_WORKFLOW_TRIGGER_URL, timeout=60)

@app.route("/dispatch/build-index", methods=["POST"])
@firebase_auth_required
def dispatch_build_index(decoded_token):
    return dispatch_request("DIALOGUE_INDEX_BUILDER_URL", DIALOGUE_INDEX_BUILDER_URL, timeout=120)


# ★★★【新規】タグ管理のエンドポイント ★★★

@app.route("/dispatch/generate-tag-suggestions", methods=["POST"])
@firebase_auth_required
def dispatch_generate_tag_suggestions(decoded_token):
    """
    [認証必須] タグ最適化提案の生成を tag-management-service に依頼する。
    """
    return dispatch_request("TAG_MANAGEMENT_SERVICE_URL", f"{TAG_MANAGEMENT_SERVICE_URL}/generate-suggestions", timeout=300)

@app.route("/dispatch/execute-tag-integration", methods=["POST"])
@firebase_auth_required
def dispatch_execute_tag_integration(decoded_token):
    """
    [認証必須] タグの統合実行を tag-management-service に依頼する。
    """
    return dispatch_request("TAG_MANAGEMENT_SERVICE_URL", f"{TAG_MANAGEMENT_SERVICE_URL}/execute-integration", timeout=300)


# Gunicornから直接実行されるためのエントリーポイント
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
