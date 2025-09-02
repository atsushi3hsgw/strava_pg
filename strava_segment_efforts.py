import polyline
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, time, timezone, timedelta
import time as time_module
import os
from sqlalchemy import create_engine, text
from stravalib.client import Client
from stravalib.exc import RateLimitExceeded
import logging
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
import tempfile

def setup_logger(name=__name__):
    logger = logging.getLogger(name)
    if not logger.hasHandlers():
        level_str = os.getenv("STRAVA_LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_str, logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s in %(name)s: %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
    return logger

logger = setup_logger(__name__)

# Page configuration
st.set_page_config(
    page_title="My Segment Efforts Dashboard",
    page_icon="🚴",
    layout="wide"
)

# Helper function to format seconds into H:MM:SS
def format_time(seconds):
    """
    Formats a time in seconds into H:MM:SS format.
    """
    if pd.isna(seconds):
        return "N/A"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours:01d}:{minutes:02d}:{seconds:02d}"

# Database connection settings
@st.cache_resource
def get_db_engine():
    """Get SQLAlchemy engine."""
    db_url = f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', 'postgres')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'strava')}"
    return create_engine(db_url)

# Strava API authentication
def authenticate_strava():
    """
    Handles the Strava API authentication flow.
    """
    # Check if required environment variables are set
    if 'STRAVA_CLIENT_ID' not in os.environ or 'STRAVA_CLIENT_SECRET' not in os.environ or 'STRAVA_REDIRECT_URI' not in os.environ:
        st.error("Please set environment variables 'STRAVA_CLIENT_ID', 'STRAVA_CLIENT_SECRET', and 'STRAVA_REDIRECT_URI'.")
        st.stop()
    
    # Get authorization code from URL
    query_params = st.query_params
    auth_code = query_params.get("code")

    # Check if token is in session state or has expired
    if 'access_token' not in st.session_state or st.session_state['expires_at'] < time_module.time():
        client = Client()
        
        # Exchange authorization code for token
        if auth_code:
            logger.debug(f"Authorization Code: {auth_code}") # Debug log
            try:
                with st.spinner("Exchanging authorization code for token..."):
                    token_info = client.exchange_code_for_token(
                        client_id=os.environ['STRAVA_CLIENT_ID'],
                        client_secret=os.environ['STRAVA_CLIENT_SECRET'],
                        code=auth_code
                    )
                
                # Save token info to session state
                st.session_state['access_token'] = token_info['access_token']
                st.session_state['refresh_token'] = token_info['refresh_token']
                st.session_state['expires_at'] = token_info['expires_at']
                logger.debug(f"Exchange authorization code for token, Access Token: {st.session_state['access_token']}, {st.session_state['expires_at']-int(time_module.time())} seconds left") # Debug log
                
                st.rerun()
            except Exception as e:
                st.error(f"Error getting token: {e}")
                st.stop()
        else:
            # Generate and display authorization URL
            try:
                authorize_url = client.authorization_url(
                    client_id=os.environ['STRAVA_CLIENT_ID'],
                    redirect_uri=os.environ['STRAVA_REDIRECT_URI'],
                    scope=['read', 'activity:read_all', 'profile:read_all']
                )
                st.info("To connect to Strava and download your activities, please click the link below.")
                # Use explicit HTML to ensure link opens in the same tab
                st.markdown(f"<a href='{authorize_url}' target='_self'>Connect to Strava</a>", unsafe_allow_html=True)
                st.stop()
            except Exception as e:
                st.error(f"Error generating authorization URL: {e}")
                st.stop()

# Save activity data to DB
def save_activities_to_db(before, after, limit):
    """
    Fetches detailed activities from the Strava API and saves them as JSON in PostgreSQL.
    """
    try:
        client = Client(access_token=st.session_state['access_token'])
        
        # Refresh token if expired
        if st.session_state['expires_at'] < time_module.time():
            with st.spinner("Refreshing access token..."):
                token_info = client.refresh_access_token(
                    client_id=os.environ['STRAVA_CLIENT_ID'],
                    client_secret=os.environ['STRAVA_CLIENT_SECRET'],
                    refresh_token=st.session_state['refresh_token']
                )
            st.session_state['access_token'] = token_info['access_token']
            st.session_state['refresh_token'] = token_info['refresh_token']
            st.session_state['expires_at'] = token_info['expires_at']
            logger.debug(f"*********Refreshing access token, Access Token: {st.session_state['access_token']}, {st.session_state['expires_at']-int(time_module.time())} seconds left") # Debug log

        with get_db_engine().connect() as conn:
            with conn.begin() as transaction:
                st.info("Fetching activities from Strava API...")
                activities = client.get_activities(before=before, after=after, limit=limit)
                st.info(f"Fetched {len(list(activities))} activities. Processing...")
                
                rows_inserted = 0
                for activity in activities:
                    if activity.type != 'Ride':
                        continue
                    
                    try:
                        detailed_activity = client.get_activity(activity_id=activity.id, include_all_efforts=True)
                        detailed_activity_json = detailed_activity.model_dump_json()
                        
                        insert_query = text("""
                            INSERT INTO activities (id, athlete_id, data)
                            VALUES (:id, :athlete_id, :data)
                            ON CONFLICT (id) DO UPDATE SET
                            data = EXCLUDED.data, created_at = now();
                        """)
                        conn.execute(
                            insert_query,
                            {
                                "id": activity.id,
                                "athlete_id": activity.athlete.id,
                                "data": detailed_activity_json,
                            }
                        )
                        rows_inserted += 1
                    except RateLimitExceeded as e:
                        st.warning(f"Strava API rate limit exceeded. Please try again later.")
                        return
                    except Exception as e:
                        st.warning(f"Failed to fetch activity {activity.id}: {e}")
                        continue
                
                st.success(f"Successfully saved {rows_inserted} activities to the database.")

    except Exception as e:
        st.error(f"Database or API connection error: {e}")
        logger.debug(f"Error details: {e}")

# Get list of segments
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_segments():
    """Get a list of available segments."""
    engine = get_db_engine()
    query = """
    SELECT DISTINCT
        (effort->'segment'->>'id')::bigint AS segment_id,
        effort->'segment'->>'name' AS segment_name,
        COUNT(*) AS effort_count
    FROM activities,
         jsonb_array_elements(data->'segment_efforts') AS effort
    WHERE effort->'segment'->>'name' IS NOT NULL
    GROUP BY segment_id, segment_name
    ORDER BY effort_count DESC
    """
    df = pd.read_sql(query, engine)
    return df

# Get segment data
@st.cache_data(ttl=300)
def get_segment_data(segment_id):
    """Get data for a specific segment."""
    engine = get_db_engine()
    query = text("""
    SELECT
        (data->>'start_date_local')::timestamp AS start_time,
        effort->>'name' AS effort_name,
        (effort->>'elapsed_time')::int AS elapsed_time_sec,
        (effort->'segment'->>'average_grade')::numeric AS avg_grade,
        (effort->>'average_heartrate')::numeric AS avg_heartrate,
        (effort->>'average_cadence')::numeric AS avg_cadence,
        (effort->'segment'->'distance')::numeric AS distance_m,
        (effort->'segment'->>'climb_category_desc') AS climb_category,
        (effort->'segment'->>'distance')::numeric / (effort->>'elapsed_time')::numeric * 3.6 AS avg_speed_kmh
    FROM activities,
         jsonb_array_elements(data->'segment_efforts') AS effort
    WHERE (effort->'segment'->>'id')::bigint = :segment_id
    ORDER BY start_time DESC
    """)
    with engine.connect() as connection:
        df = pd.read_sql(query, connection, params={"segment_id": int(segment_id)})
    return df

@st.cache_data(ttl=300)
def get_polylines(before=None, after=None):
    """
    Get all decoded polylines for heatmap as [[lat, lng], ...].
    
    Parameters
    ----------
    before : datetime | None
        Include activities with start_time <= before
    after : datetime | None
        Include activities with start_time >= after
    """
    logger.debug(f"get_polylines before={before}, after={after} ")
    engine = get_db_engine()

    base_query = """
    SELECT 
        data->'map'->>'polyline' AS polyline,
        (data->>'start_date_local')::timestamp AS start_time
    FROM
        activities
    WHERE 
        data->'map'->>'polyline' IS NOT NULL
    """

    conditions = []
    bind_params = {}
    if before is not None:
        conditions.append("(data->>'start_date_local')::timestamp <= :before")
        bind_params["before"] = before
    if after is not None:
        conditions.append("(data->>'start_date_local')::timestamp >= :after")
        bind_params["after"] = after

    if conditions:
        base_query += " AND " + " AND ".join(conditions)

    allcoords = []
    with engine.connect() as conn:
        result = conn.execute(text(base_query), bind_params)
        for row in result:
            poly = row[0]
            if not poly or not isinstance(poly, str):
                continue
            try:
                coords = polyline.decode(poly)
                allcoords.extend(coords)
            except Exception as e:
                st.warning(f"Failed to decode a polyline: {e}")
                logger.warning(f"Failed to decode polyline: {e}")
                continue

    return allcoords

def segment_efforts_dashboard():
    
    # Get segment list from the database
    try:
        segments_df = get_segments()
    except Exception as e:
        st.error(f"Error fetching segment data. Please ensure the database is running: {e}")
        return
        
    if segments_df.empty:
        st.warning("No segment data found in the database. Please download activities from the sidebar.")
        return
        
    # Select segment
    selected_segment_name = st.selectbox(
        "Select a segment to analyze:",
        segments_df['segment_name'],
        index=0
    )
    
    
    selected_segment = segments_df[segments_df['segment_name'] == selected_segment_name].iloc[0]
    
    # Get segment data
    segment_data = get_segment_data(selected_segment['segment_id'])
    
    if segment_data.empty:
        st.warning("No data found for the selected segment.")
        return
        
    st.subheader(f"{selected_segment_name}")
    
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        st.metric("Fastest Time", format_time(segment_data['elapsed_time_sec'].min()))
    with col2:
        st.metric("Average Time", format_time(segment_data['elapsed_time_sec'].mean()))
    with col3:
        st.metric("Average Heart Rate", f"{segment_data['avg_heartrate'].mean():.1f} bpm")
    with col4:
        st.metric("Average Speed", f"{segment_data['avg_speed_kmh'].mean():.1f} km/h")
    with col5:
        st.metric("Average Cadence", f"{segment_data['avg_cadence'].mean():.1f} rpm")
    with col6:
        st.metric("Total Efforts", f"{len(segment_data)}")
    
    # Charts    
    st.subheader("Charts")   
    chart_data = segment_data.sort_values('start_time')

    charts_to_display = {
        "elapsed_time_sec": "Elapsed Time (seconds)",
        "avg_cadence": "Average Cadence (RPM)",
        "avg_speed_kmh": "Average Speed (km/h)",
        "avg_heartrate": "Average Heart Rate (bpm)",
    }

    for y_axis, title in charts_to_display.items():
        st.subheader(title)
        chart_df = pd.DataFrame({
            "start_time": chart_data['start_time'],
            y_axis: chart_data[y_axis]
        })
        st.line_chart(chart_df, x="start_time", y=y_axis)
    
    # Statistics
    st.subheader("Detailed Statistics")
    col1, col2 = st.columns(2)
    with col1:
        st.write("#### All Performance Data")
        st.dataframe(segment_data[['start_time', 'elapsed_time_sec', 'avg_heartrate', 'avg_cadence', 'avg_speed_kmh']].set_index('start_time').sort_index(ascending=False))
    
    with col2:
        st.write("#### Monthly Statistics")
        segment_data['year_month'] = segment_data['start_time'].dt.to_period('M')
        monthly_stats = segment_data.groupby('year_month').agg({
            'elapsed_time_sec': ['count', 'mean', 'min'],
            'avg_heartrate': 'mean',
            'avg_cadence': 'mean',
            'avg_speed_kmh': 'mean'
        }).round(1)
        st.dataframe(monthly_stats)

@st.cache_data(ttl=3600)
def generate_heatmap_html(coords):

    if not coords:
        return None

    center_lat = sum(p[0] for p in coords) / len(coords)
    center_lon = sum(p[1] for p in coords) / len(coords)

    m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
    HeatMap(coords, radius=8, blur=5, min_opacity=0.2).add_to(m)
    
    return m._repr_html_()

def heatmap_dashboard(before=None, after=None):
    
    logger.debug(f"heatmap_dashboard before={before}, after={after} ")
    
    st.subheader("Personal Heatmap")
    st.info(f"Fetching coordinates...")
    coords = get_polylines(before=before, after=after)
    st.info(f"Fetched {len(coords)} coordinates.")
                    
    if coords:
        # center_lat = sum(p[0] for p in coords) / len(coords)
        # center_lon = sum(p[1] for p in coords) / len(coords)
    
        # m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
        # HeatMap(coords, radius=8, blur=5, min_opacity=0.2).add_to(m)
        # st_folium(m, use_container_width=True)
        map_html = generate_heatmap_html(coords)
        if map_html:
            components.html(map_html, height=500)
    else:
        st.warning("No coordinates to display for the selected date range.")
        
    if st.button("Segment Efforts Dashboard"):
        st.session_state['dashboard'] = 'segment_efforts'
        st.rerun()
    
# Main application
def main():
    st.title("My Dashboard")

    # Authentication flow
    authenticate_strava()

    # Dashboard display after successful authentication
    if 'access_token' in st.session_state:
        st.sidebar.header("Settings")
        
        # Activity download UI
        with st.sidebar.expander("🚴‍♀️ Download Activities"):
            st.info("Fetch new data and update the database.")
            before_date = st.date_input("End Date (Before)", None, key="download_before")
            after_date = st.date_input("Start Date (After)", datetime.now().date() - timedelta(days=10), key="download_after")
            limit = st.number_input("Number of Activities", min_value=1, value=10, step=1)
            
            if st.button("Execute Download"):
                if after_date and before_date and after_date > before_date:
                    st.warning("Start date must be before the end date.")
                else:
                    local_tz = datetime.now().astimezone().tzinfo
                    before_utc = datetime.combine(before_date, time.min, tzinfo=local_tz).astimezone(timezone.utc) if before_date else None
                    after_utc = datetime.combine(after_date, time.min, tzinfo=local_tz).astimezone(timezone.utc) if after_date else None
                    save_activities_to_db(
                        before=before_utc,
                        after=after_utc,
                        limit=limit
                    )
        
        # Personal Heatmap UI
        with st.sidebar.expander("🗺️ Personal Heatmap"):
            st.info("Create a personal heatmap from your activities.")
            heatmap_before_date = st.date_input("End Date (Before)", None, key="heatmap_before")
            heatmap_after_date = st.date_input("Start Date (After)", None, key="heatmap_after")

            if st.button("Create Heatmap"):
                if heatmap_after_date and heatmap_before_date and heatmap_after_date > heatmap_before_date:
                    st.warning("Start date must be before the end date.")
                else:
                    st.session_state['dashboard'] = 'heatmap'
                    st.rerun()

        if st.session_state.get('dashboard') == 'heatmap':
            local_tz = datetime.now().astimezone().tzinfo
            heatmap_before_date = st.session_state.get('heatmap_before', None)
            heatmap_after_date = st.session_state.get('heatmap_after', None)
            heatmap_before_datetime_lc = datetime.combine(heatmap_before_date, time.min, tzinfo=local_tz) if heatmap_before_date else None
            heatmap_after_datetime_lc  = datetime.combine(heatmap_after_date, time.min, tzinfo=local_tz) if heatmap_after_date else None
            heatmap_dashboard(before=heatmap_before_datetime_lc, after=heatmap_after_datetime_lc)
        else:
            segment_efforts_dashboard()
        
# Start the application
if __name__ == "__main__":
    main()