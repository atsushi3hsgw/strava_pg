import time
from stravalib.client import Client
from stravalib.exc import RateLimitExceeded
import argparse
import os
import psycopg2
import json
import requests
import datetime

def save_activities_to_db(client, db_conn, before=None, after=None, limit=30):
    """
    Strava APIからアクティビティ詳細を取得し、PostgreSQLにJSONのまま保存
    """
    
    # https://stravalib.readthedocs.io/en/latest/reference/api/stravalib.client.Client.get_activities.html#stravalib.client.Client.get_activities
    activities = client.get_activities(before=before, after=after, limit=limit)
    cur = db_conn.cursor()

    for activity in activities:
        if activity.type != 'Ride':
            continue
        
        print(f"Fetched activity Date: {activity.start_date},ID: {activity.id}, Name: {activity.name}")    
        # https://stravalib.readthedocs.io/en/latest/reference/api/stravalib.client.Client.get_activity.html
        detailed_activity = client.get_activity(activity_id = activity.id, include_all_efforts=True)
        detailed_activity_json = detailed_activity.json()

        cur.execute("""
            INSERT INTO activities (id, athlete_id, data)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (
             detailed_activity.id,
             detailed_activity.athlete.id,
             detailed_activity_json)
        )
        db_conn.commit()
        time.sleep(10.0) # A100 15分毎のリクエスト
    cur.close()

def str_to_local_datetime(date_str: str) -> datetime.datetime:
    d = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    local_tz = datetime.datetime.now().astimezone().tzinfo
    return datetime.datetime.combine(d, datetime.time.min, tzinfo=local_tz)

if __name__ == '__main__':
    
    parser = argparse.ArgumentParser(description='Save your activities to database')
    parser.add_argument('--before', type=str_to_local_datetime, default=None, help='Result will start with activities whose start date is before specified date.')
    parser.add_argument('--after', type=str_to_local_datetime, default=None, help='Result will start with activities whose start date is after specified value')
    parser.add_argument('--limit', type=int, default=30, help='Maximum number of activities')
    args = parser.parse_args()
    before_utc = args.before.astimezone(datetime.timezone.utc) if args.before else None
    after_utc = args.after.astimezone(datetime.timezone.utc) if args.after else None
    
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

    save_activities_to_db(client, db_conn, before_utc, after_utc, args.limit)
    db_conn.close()