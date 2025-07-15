# ==============================================================================
# Memory Library - API Gateway Service (api-gateway)
# main.py (v3.0 Final / Production Ready)
#
# Role:         システムの唯一の公開窓口。UIからのリクエストを受け付け、
#               認証を行い、適切な内部サービスへ安全に転送する。
# Version:      3.0
# Author:       心理 (Thinking Partner)
# Last Updated: 2025-07-15
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
    # Cloud Run環境では引数なしで自動的に初期化される
    firebase_admin.initialize_app()
except ValueError:
    # ローカルでの複数回実行などを考慮
    pass

app = Flask(__name__)
# UIからのリクエストを許可するためのCORS設定
CORS(app)

# 環境変数から内部サービスのURLを読み込む
# これらの変数が設定されていない場合、サービスは起動時にエラーとなる
ARTICLE_INGEST_SERVICE_URL = os.environ.get("ARTICLE_INGEST_SERVICE_URL")
MANUAL_WORKFLOW_TRIGGER_URL = os.environ.get("MANUAL_WORKFLOW_TRIGGER_URL")


# --- 認証デコレーター (Authentication Decorator) ---
def firebase_auth_required(f):
    """
    リクエストヘッダーのIDトークンを検証し、正規のUI利用者からの
    リクエストであることを保証するデコレーター。
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"status": "error", "message": "認証エラー: Authorizationヘッダーがありません。"}), 403
        
        id_token = auth_header.split("Bearer ")[1]
        
        try:
            # Firebase Admin SDKでIDトークンを検証
            decoded_token = auth.verify_id_token(id_token)
            # 検証済みトークン情報をルート関数に渡す
            kwargs['decoded_token'] = decoded_token
        except Exception as e:
            app.logger.error(f"IDトークンの検証に失敗: {e}")
            return jsonify({"status": "error", "message": f"認証エラー: トークンが無効です。"}), 403
            
        return f(*args, **kwargs)
    return decorated_function


# --- サービス間認証トークン生成 (Service-to-Service Auth Token) ---
def get_service_to_service_token(audience_url):
    """
    指定されたaudience (呼び出し先サービスURL) に対する
    IDトークンを生成する。これにより、api-gatewayは自身の身分を証明する。
    """
    try:
        auth_req = google.auth.transport.requests.Request()
        # google-authライブラリが、現在のサービスアカウントの権限を元に
        # 新しいIDトークンを自動的に生成・取得する
        id_token = google.oauth2.id_token.fetch_id_token(auth_req, audience_url)
        return id_token
    except Exception as e:
        app.logger.error(f"サービス間認証トークンの生成に失敗: {e}")
        # トークン生成に失敗した場合は、処理を続行できないためNoneを返す
        return None


# --- ルーティング (Routing) ---
@app.route("/dispatch/article", methods=["POST"])
@firebase_auth_required
def dispatch_article(decoded_token):
    """
    [認証必須] UIからの記事投入リクエストを、
    内部の article-ingest-service へ転送する。
    """
    if not ARTICLE_INGEST_SERVICE_URL:
        return jsonify({"status": "error", "message": "設定エラー: 転送先URL(ARTICLE_INGEST_SERVICE_URL)が未設定です。"}), 500

    # ★★★【正常化】サービス間認証の復活 ★★★
    # article-ingest-serviceを呼び出すための、新しいIDトークンを生成する
    service_token = get_service_to_service_token(ARTICLE_INGEST_SERVICE_URL)
    if not service_token:
        return jsonify({"status": "error", "message": "ゲートウェイ内部エラー: サービス間認証に失敗しました。"}), 500

    try:
        # ヘッダーに「サービス間認証トークン」を付与してリクエスト
        headers = {
            'Authorization': f'Bearer {service_token}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            url=ARTICLE_INGEST_SERVICE_URL,
            headers=headers,
            data=request.get_data(), # UIからのリクエストボディをそのまま転送
            timeout=30 
        )
        # 内部サービスからの応答がエラーだった場合、例外を発生させる
        response.raise_for_status()
        
        # 内部サービスからの応答をそのままUIに返す
        return response.json(), response.status_code

    except requests.exceptions.RequestException as e:
        app.logger.error(f"article-ingest-serviceへの転送に失敗: {e}")
        # ネットワークエラーや内部サービスからのエラー応答をハンドリング
        status_code = e.response.status_code if e.response else 503
        return jsonify({"status": "error", "message": f"下流サービスへの接続に失敗しました。"}), status_code


@app.route("/dispatch/workflow", methods=["POST"])
@firebase_auth_required
def dispatch_workflow(decoded_token):
    """
    [認証必須] UIからのワークフロー開始リクエストを、
    内部の manual-workflow-trigger へ転送する。
    """
    if not MANUAL_WORKFLOW_TRIGGER_URL:
        return jsonify({"status": "error", "message": "設定エラー: 転送先URL(MANUAL_WORKFLOW_TRIGGER_URL)が未設定です。"}), 500

    # ★★★【正常化】サービス間認証の復活 ★★★
    # manual-workflow-triggerを呼び出すための、新しいIDトークンを生成する
    service_token = get_service_to_service_token(MANUAL_WORKFLOW_TRIGGER_URL)
    if not service_token:
        return jsonify({"status": "error", "message": "ゲートウェイ内部エラー: サービス間認証に失敗しました。"}), 500

    try:
        # ヘッダーに「サービス間認証トークン」を付与してリクエスト
        headers = {
            'Authorization': f'Bearer {service_token}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            url=MANUAL_WORKFLOW_TRIGGER_URL,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json(), response.status_code

    except requests.exceptions.RequestException as e:
        app.logger.error(f"manual-workflow-triggerへの転送に失敗: {e}")
        status_code = e.response.status_code if e.response else 503
        return jsonify({"status": "error", "message": f"下流サービスへの接続に失敗しました。"}), status_code

# Gunicornから直接実行されるためのエントリーポイント
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)

