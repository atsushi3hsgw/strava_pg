import time
from stravalib.client import Client
from stravalib.exc import RateLimitExceeded
import argparse
import os
import psycopg2
import json
import requests

def save_activities_to_db(client, db_conn):
    """
    Strava APIからアクティビティ詳細を取得し、PostgreSQLにJSONのまま保存
    """
    activities = client.get_activities(limit=800)
    cur = db_conn.cursor()
    access_token = os.getenv("STRAVA_ACCESS_TOKEN")

    for activity in activities:
        if activity.type != 'Ride':
            continue

        # stravalib の DetailedActivity には .to_dict() がないので、直接JSONを取得する
        # REST APIでJSON取得
        url = f"https://www.strava.com/api/v3/activities/{activity.id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        activity_json = r.json()

        print(f"Fetched activity ID: {activity.id}, Name: {activity.name}")

        # DB保存
        cur.execute("""
            INSERT INTO activities (id, athlete_id, data)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (
            activity_json["id"],
            activity_json["athlete"]["id"],
            json.dumps(activity_json)
        ))
        db_conn.commit()

        # 100 15分毎のリクエスト
        time.sleep(10.0) # APIレート制限回避のため少し待つ

    cur.close()

if __name__ == '__main__':
    client_id = os.getenv('STRAVA_CLIENT_ID')
    client_secret = os.getenv('STRAVA_CLIENT_SECRET')
    access_token = os.getenv('STRAVA_ACCESS_TOKEN')
    refresh_token = os.getenv('STRAVA_REFRESH_TOKEN')
    token_expires_at = int(os.getenv('STRAVA_TOKEN_EXPIRES_AT', '0'))

    client = Client(
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires=token_expires_at
    )
    client.client_id = client_id
    client.client_secret = client_secret

    # DB接続
    db_conn = psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "strava"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres")
    )

    save_activities_to_db(client, db_conn)
    db_conn.close()