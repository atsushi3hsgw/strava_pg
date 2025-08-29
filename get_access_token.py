from stravalib.client import Client
import webbrowser
import os

# 環境変数からクライアントIDとクライアントシークレットを取得する
CLIENT_ID = os.getenv('STRAVA_CLIENT_ID')
CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET')

# ユーザーザーがブラウザで認証を行い、認可コードを取得する。
client = Client()
authorize_url = client.authorization_url(
    client_id=CLIENT_ID,
    redirect_uri='http://localhost:8080/authorized',
    scope=['read', 'activity:read_all', 'profile:read_all']
)

# ブラウザで認証する。
print(authorize_url)
# ブラウザを自動で開く
webbrowser.open(authorize_url)

# ユーザーが認証を許可すると、ブラウザのURLに認可コード(code)が付加されます
# 例: http://localhost:8080/authorized?state=&code=YOUR_AUTHORIZATION_CODE&scope=read,read_all

# 認可コード(code)を入力する
authorization_code = input('Enter the authorization code:')

# 認可コードを受け取り、Stravaのサーバーと通信してアクセストークンと交換する
token_info = client.exchange_code_for_token(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    code=authorization_code
)

access_token = token_info['access_token']
refresh_token = token_info['refresh_token']
expires_at = token_info['expires_at']

print('access_token:', access_token)
print('refresh_token:', refresh_token)
print('expires_at:', expires_at)