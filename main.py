# ==============================================================================
# 1. main.py
# UIからのリクエストを認証し、バックエンドサービスに転送するAPIゲートウェイ。
# ==============================================================================
import os
import requests
import firebase_admin
from firebase_admin import auth
from flask import Flask, request, jsonify

# Firebase Admin SDKを初期化 (Cloud Run環境では自動検出)
try:
    firebase_admin.initialize_app()
except ValueError:
    pass

app = Flask(__name__)

# 環境変数からバックエンドサービスのURLを取得
ARTICLE_INGEST_SERVICE_URL = os.environ.get("ARTICLE_INGEST_SERVICE_URL")
MANUAL_WORKFLOW_TRIGGER_URL = os.environ.get("MANUAL_WORKFLOW_TRIGGER_URL")

@app.route("/")
def index():
    """サービス起動確認用のルートエンドポイント"""
    return "API Gateway is running.", 200

@app.route("/dispatch/article", methods=["POST"])
def dispatch_article():
    """記事投入リクエストを検証・転送する"""
    try:
        # IDトークンを取得・検証
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"status": "error", "message": "認証エラー: トークンがありません。"}), 403
        id_token = auth_header.split("Bearer ")[1]
        decoded_token = auth.verify_id_token(id_token)
        
        # 検証後、リクエストを転送
        if not ARTICLE_INGEST_SERVICE_URL:
            return jsonify({"status": "error", "message": "設定エラー: 転送先URLが未設定です。"}), 500

        response = requests.post(
            url=ARTICLE_INGEST_SERVICE_URL,
            headers={'Content-Type': 'application/json'},
            data=request.get_data(),
            timeout=30 
        )
        response.raise_for_status()
        return response.json(), response.status_code

    except auth.InvalidIdTokenError:
        return jsonify({"status": "error", "message": "認証エラー: トークンが無効か、期限切れです。"}), 403
    except Exception as e:
        print(f"予期せぬエラー: {e}")
        return jsonify({"status": "error", "message": f"ゲートウェイ内部エラー: {e}"}), 500

@app.route("/dispatch/workflow", methods=["POST"])
def dispatch_workflow():
    """ワークフロー開始リクエストを検証・転送する"""
    try:
        # IDトークンを検証
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"status": "error", "message": "認証エラー: トークンがありません。"}), 403
        id_token = auth_header.split("Bearer ")[1]
        decoded_token = auth.verify_id_token(id_token)

        # 検証後、リクエストを転送
        if not MANUAL_WORKFLOW_TRIGGER_URL:
            return jsonify({"status": "error", "message": "設定エラー: 転送先URLが未設定です。"}), 500
        
        response = requests.post(
            url=MANUAL_WORKFLOW_TRIGGER_URL,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        response.raise_for_status()
        return response.json(), response.status_code

    except auth.InvalidIdTokenError:
        return jsonify({"status": "error", "message": "認証エラー: トークンが無効か、期限切れです。"}), 403
    except Exception as e:
        print(f"予期せぬエラー: {e}")
        return jsonify({"status": "error", "message": f"ゲートウェイ内部エラー: {e}"}), 500
