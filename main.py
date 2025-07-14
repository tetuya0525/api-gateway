# ==============================================================================
# 1. main.py
# 他サービス呼び出し時に、自身のIDトークンを付与する認証ロジックを追加。
# ==============================================================================
import os
import requests
import firebase_admin
from functools import wraps
from firebase_admin import auth
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.auth.transport.requests
import google.oauth2.id_token

try:
    firebase_admin.initialize_app()
except ValueError:
    pass

app = Flask(__name__)
CORS(app)

ARTICLE_INGEST_SERVICE_URL = os.environ.get("ARTICLE_INGEST_SERVICE_URL")
MANUAL_WORKFLOW_TRIGGER_URL = os.environ.get("MANUAL_WORKFLOW_TRIGGER_URL")

def get_service_to_service_auth_header(target_url):
    """他のCloud Runサービスを呼び出すための認証ヘッダーを生成する"""
    auth_req = google.auth.transport.requests.Request()
    identity_token = google.oauth2.id_token.fetch_id_token(auth_req, target_url)
    return {
        'Authorization': f'Bearer {identity_token}',
        'Content-Type': 'application/json'
    }

def firebase_auth_required(f):
    """UIからのリクエストのFirebase IDトークンを検証するデコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"status": "error", "message": "認証エラー: UIからのトークンがありません。"}), 403
        
        id_token = auth_header.split("Bearer ")[1]
        
        try:
            decoded_token = auth.verify_id_token(id_token)
            kwargs['decoded_token'] = decoded_token
        except Exception as e:
            return jsonify({"status": "error", "message": f"認証エラー: トークンが無効です。 {e}"}), 403
            
        return f(*args, **kwargs)
    return decorated_function

@app.route("/dispatch/article", methods=["POST"])
@firebase_auth_required
def dispatch_article(decoded_token):
    """記事投入リクエストを検証・転送する"""
    try:
        if not ARTICLE_INGEST_SERVICE_URL:
            return jsonify({"status": "error", "message": "設定エラー: 転送先URLが未設定です。"}), 500

        # ★★★ 改善点：サービス間認証ヘッダーを付与 ★★★
        auth_headers = get_service_to_service_auth_header(ARTICLE_INGEST_SERVICE_URL)

        response = requests.post(
            url=ARTICLE_INGEST_SERVICE_URL,
            headers=auth_headers,
            data=request.get_data(),
            timeout=30 
        )
        response.raise_for_status()
        return response.json(), response.status_code
    except Exception as e:
        print(f"予期せぬエラー: {e}")
        return jsonify({"status": "error", "message": f"ゲートウェイ内部エラー: {e}"}), 500

@app.route("/dispatch/workflow", methods=["POST"])
@firebase_auth_required
def dispatch_workflow(decoded_token):
    """ワークフロー開始リクエストを検証・転送する"""
    try:
        if not MANUAL_WORKFLOW_TRIGGER_URL:
            return jsonify({"status": "error", "message": "設定エラー: 転送先URLが未設定です。"}), 500

        # ★★★ 改善点：サービス間認証ヘッダーを付与 ★★★
        auth_headers = get_service_to_service_auth_header(MANUAL_WORKFLOW_TRIGGER_URL)

        response = requests.post(
            url=MANUAL_WORKFLOW_TRIGGER_URL,
            headers=auth_headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json(), response.status_code
    except Exception as e:
        print(f"予期せぬエラー: {e}")
        return jsonify({"status": "error", "message": f"ゲートウェイ内部エラー: {e}"}), 500
