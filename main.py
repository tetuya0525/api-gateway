# =============================================================================
# 1. main.py (v2.3 - CORS対応版)
# flask-corsを導入し、UIからのクロスオリジンリクエストを許可します。
# ==============================================================================
import os
import requests
import firebase_admin
from functools import wraps
from firebase_admin import auth
from flask import Flask, request, jsonify
from flask_cors import CORS # ★★★ 改善点：CORSライブラリをインポート ★★★

# Firebase Admin SDKを初期化
try:
    firebase_admin.initialize_app()
except ValueError:
    pass

app = Flask(__name__)

# ★★★ 改善点：CORSをアプリケーションに適用 ★★★
# これにより、ブラウザからのAPI呼び出しが許可されます。
CORS(app)

# 環境変数からバックエンドサービスのURLを取得
ARTICLE_INGEST_SERVICE_URL = os.environ.get("ARTICLE_INGEST_SERVICE_URL")
MANUAL_WORKFLOW_TRIGGER_URL = os.environ.get("MANUAL_WORKFLOW_TRIGGER_URL")

def firebase_auth_required(f):
    """Firebase IDトークンを検証するデコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"status": "error", "message": "認証エラー: トークンがありません。"}), 403
        
        id_token = auth_header.split("Bearer ")[1]
        
        try:
            decoded_token = auth.verify_id_token(id_token)
            kwargs['decoded_token'] = decoded_token
        except auth.InvalidIdTokenError:
            return jsonify({"status": "error", "message": "認証エラー: トークンが無効か、期限切れです。"}), 403
        except Exception as e:
            return jsonify({"status": "error", "message": f"認証エラー: {e}"}), 403
            
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
def index():
    """サービス起動確認用のルートエンドポイント"""
    return "API Gateway is running.", 200

@app.route("/dispatch/article", methods=["POST"])
@firebase_auth_required
def dispatch_article(decoded_token):
    """記事投入リクエストを受け付け、article-ingest-serviceに転送する"""
    try:
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
    except Exception as e:
        print(f"予期せぬエラー: {e}")
        return jsonify({"status": "error", "message": f"ゲートウェイ内部エラー: {e}"}), 500

@app.route("/dispatch/workflow", methods=["POST"])
@firebase_auth_required
def dispatch_workflow(decoded_token):
    """ワークフロー開始リクエストを受け付け、manual-workflow-triggerに転送する"""
    try:
        if not MANUAL_WORKFLOW_TRIGGER_URL:
            return jsonify({"status": "error", "message": "設定エラー: 転送先URLが未設定です。"}), 500
        
        response = requests.post(
            url=MANUAL_WORKFLOW_TRIGGER_URL,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        response.raise_for_status()
        return response.json(), response.status_code
    except Exception as e:
        print(f"予期せぬエラー: {e}")
        return jsonify({"status": "error", "message": f"ゲートウェイ内部エラー: {e}"}), 500
