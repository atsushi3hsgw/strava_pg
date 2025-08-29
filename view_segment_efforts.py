import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime
import os
from sqlalchemy import create_engine

# ページ設定
st.set_page_config(
    page_title="STRAVA セグメント分析",
    page_icon="🚴",
    layout="wide"
)

# データベース接続設定
@st.cache_resource
def get_db_engine():
    """SQLAlchemyエンジンを取得"""
    db_url = f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', 'postgres')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'strava')}"
    return create_engine(db_url)

# セグメント一覧を取得
@st.cache_data(ttl=300)  # 5分間キャッシュ
def get_segments():
    """利用可能なセグメント一覧を取得"""
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
    ORDER BY effort_count DESC, segment_name
    """
    df = pd.read_sql(query, engine)
    return df

# セグメントデータを取得
@st.cache_data(ttl=60)  # 1分間キャッシュ
def get_segment_data(segment_id):
    """指定セグメントのデータを取得"""
    engine = get_db_engine()
    query = """
    SELECT 
        (effort->>'start_date_local')::timestamp AS start_time,
        (effort->>'elapsed_time')::int AS elapsed_time_sec,
        (effort->>'average_heartrate')::numeric AS avg_heartrate,
        (effort->>'average_cadence')::numeric AS avg_cadence,
        (effort->>'distance')::numeric AS distance_m,
        data->>'name' AS activity_name,
        data->>'type' AS activity_type
    FROM activities,
         jsonb_array_elements(data->'segment_efforts') AS effort
    WHERE (effort->'segment'->>'id')::bigint = %(segment_id)s
      AND effort->>'elapsed_time' IS NOT NULL
    ORDER BY start_time DESC
    """
    df = pd.read_sql(query, engine, params={'segment_id': int(segment_id)})
    
    if not df.empty:
        # 時間を分:秒形式に変換
        df['elapsed_time_formatted'] = df['elapsed_time_sec'].apply(
            lambda x: f"{x//60}:{x%60:02d}" if pd.notnull(x) else "N/A"
        )
        # 平均速度を計算 (km/h)
        df['avg_speed_kmh'] = df.apply(
            lambda row: (row['distance_m'] / 1000) / (row['elapsed_time_sec'] / 3600) 
            if pd.notnull(row['distance_m']) and pd.notnull(row['elapsed_time_sec']) and row['elapsed_time_sec'] > 0
            else None, axis=1
        )
        # 日付フォーマット
        df['date'] = df['start_time'].dt.date
    
    return df

# メインアプリケーション
def main():
    st.title("🚴 STRAVA セグメント分析")
    st.markdown("---")
    
    try:
        # セグメント一覧を取得
        segments_df = get_segments()
        
        if segments_df.empty:
            st.warning("セグメントデータが見つかりません。アクティビティデータを確認してください。")
            return
        
        # サイドバーでセグメント選択
        with st.sidebar:
            st.header("セグメント選択")
            
            # セグメント選択ボックス
            segment_options = [
                f"{row['segment_name']} ({row['effort_count']}回)"
                for _, row in segments_df.iterrows()
            ]
            
            selected_option = st.selectbox(
                "分析するセグメントを選択:",
                segment_options
            )
            
            # 選択されたセグメントIDを取得
            selected_idx = segment_options.index(selected_option)
            selected_segment_id = int(segments_df.iloc[selected_idx]['segment_id'])  # int()で変換
            selected_segment_name = segments_df.iloc[selected_idx]['segment_name']
        
        # 選択されたセグメントの情報を表示
        st.header(f"📊 {selected_segment_name}")
        
        # セグメントデータを取得
        segment_data = get_segment_data(selected_segment_id)
        
        if segment_data.empty:
            st.warning("このセグメントのデータが見つかりません。")
            return
        
        # 統計情報を表示
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        
        with col1:
            st.metric("総実施回数", len(segment_data))
        
        with col2:
            best_time = segment_data['elapsed_time_sec'].min()
            st.metric("ベストタイム", f"{best_time//60}:{best_time%60:02d}")
        
        with col3:
            avg_time = segment_data['elapsed_time_sec'].mean()
            st.metric("平均タイム", f"{avg_time//60:.0f}:{avg_time%60:02.0f}")
        
        with col4:
            if segment_data['avg_heartrate'].notna().any():
                avg_hr = segment_data['avg_heartrate'].mean()
                st.metric("平均心拍数", f"{avg_hr:.0f} bpm")
            else:
                st.metric("平均心拍数", "N/A")
        
        with col5:
            if segment_data['avg_cadence'].notna().any():
                avg_cadence = segment_data['avg_cadence'].mean()
                st.metric("平均ケイデンス", f"{avg_cadence:.0f} rpm")
            else:
                st.metric("平均ケイデンス", "N/A")
        
        with col6:
            if segment_data['avg_speed_kmh'].notna().any():
                avg_speed = segment_data['avg_speed_kmh'].mean()
                st.metric("平均速度", f"{avg_speed:.1f} km/h")
            else:
                st.metric("平均速度", "N/A")
        
        st.markdown("---")
        
        # タブで表示を切り替え
        tab1, tab2, tab3 = st.tabs(["📈 グラフ表示", "📋 データ表", "📊 統計"])
        
        with tab1:
            # グラフ表示
            st.subheader("時系列グラフ")
            
            # タイムグラフ
            st.write("**タイムの推移**")
            chart_data = segment_data.set_index('start_time')[['elapsed_time_sec']]
            st.line_chart(chart_data)
            
            # 心拍数グラフ（データがある場合のみ）
            if segment_data['avg_heartrate'].notna().any():
                st.write("**平均心拍数の推移**")
                hr_data = segment_data.dropna(subset=['avg_heartrate']).set_index('start_time')[['avg_heartrate']]
                st.line_chart(hr_data)
            
            # ケイデンスグラフ（データがある場合のみ）
            if segment_data['avg_cadence'].notna().any():
                st.write("**平均ケイデンスの推移**")
                cadence_data = segment_data.dropna(subset=['avg_cadence']).set_index('start_time')[['avg_cadence']]
                st.line_chart(cadence_data)
            
            # 速度グラフ（データがある場合のみ）
            if segment_data['avg_speed_kmh'].notna().any():
                st.write("**平均速度の推移**")
                speed_data = segment_data.dropna(subset=['avg_speed_kmh']).set_index('start_time')[['avg_speed_kmh']]
                st.line_chart(speed_data)
            
            # 散布図（タイム vs 心拍数）
            if segment_data['avg_heartrate'].notna().any():
                st.write("**心拍数 vs タイムの関係**")
                scatter_data = segment_data.dropna(subset=['avg_heartrate'])
                st.scatter_chart(
                    data=scatter_data,
                    x='avg_heartrate',
                    y='elapsed_time_sec'
                )
        
        with tab2:
            # データ表示
            st.subheader("詳細データ")
            
            # 表示用データフレームを準備
            display_df = segment_data.copy()
            display_df = display_df[[
                'date', 'elapsed_time_formatted', 'avg_heartrate', 'avg_cadence', 'avg_speed_kmh',
                'activity_name', 'activity_type'
            ]]
            display_df.columns = [
                '日付', 'タイム', '平均心拍数', '平均ケイデンス', '平均速度(km/h)', 'アクティビティ名', 'タイプ'
            ]
            
            # データフィルター
            st.write("**フィルター:**")
            col1, col2 = st.columns(2)
            
            with col1:
                date_range = st.date_input(
                    "日付範囲",
                    value=(segment_data['date'].min(), segment_data['date'].max()),
                    min_value=segment_data['date'].min(),
                    max_value=segment_data['date'].max()
                )
            
            with col2:
                activity_types = segment_data['activity_type'].unique().tolist()
                selected_types = st.multiselect(
                    "アクティビティタイプ",
                    activity_types,
                    default=activity_types
                )
            
            # フィルターを適用
            if len(date_range) == 2:
                filtered_data = segment_data[
                    (segment_data['date'] >= date_range[0]) &
                    (segment_data['date'] <= date_range[1]) &
                    (segment_data['activity_type'].isin(selected_types))
                ]
                
                filtered_display = filtered_data[[
                    'date', 'elapsed_time_formatted', 'avg_heartrate', 'avg_cadence', 'avg_speed_kmh',
                    'activity_name', 'activity_type'
                ]].copy()
                filtered_display.columns = [
                    '日付', 'タイム', '平均心拍数', '平均ケイデンス', '平均速度(km/h)', 'アクティビティ名', 'タイプ'
                ]
                
                st.dataframe(filtered_display, use_container_width=True)
                
                # CSVダウンロード
                csv = filtered_display.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 CSVでダウンロード",
                    data=csv,
                    file_name=f"{selected_segment_name}_data.csv",
                    mime="text/csv"
                )
        
        with tab3:
            # 統計情報
            st.subheader("詳細統計")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.write("**タイム統計**")
                time_stats = segment_data['elapsed_time_sec'].describe()
                for stat, value in time_stats.items():
                    if stat == 'count':
                        st.write(f"- {stat}: {value:.0f}")
                    else:
                        st.write(f"- {stat}: {value//60:.0f}:{value%60:02.0f}")
            
            with col2:
                if segment_data['avg_heartrate'].notna().any():
                    st.write("**心拍数統計**")
                    hr_stats = segment_data['avg_heartrate'].describe()
                    for stat, value in hr_stats.items():
                        if stat == 'count':
                            st.write(f"- {stat}: {value:.0f}")
                        else:
                            st.write(f"- {stat}: {value:.1f} bpm")
            
            with col3:
                if segment_data['avg_cadence'].notna().any():
                    st.write("**ケイデンス統計**")
                    cadence_stats = segment_data['avg_cadence'].describe()
                    for stat, value in cadence_stats.items():
                        if stat == 'count':
                            st.write(f"- {stat}: {value:.0f}")
                        else:
                            st.write(f"- {stat}: {value:.1f} rpm")
            
            with col4:
                if segment_data['avg_speed_kmh'].notna().any():
                    st.write("**速度統計**")
                    speed_stats = segment_data['avg_speed_kmh'].describe()
                    for stat, value in speed_stats.items():
                        if stat == 'count':
                            st.write(f"- {stat}: {value:.0f}")
                        else:
                            st.write(f"- {stat}: {value:.1f} km/h")
            
            # 月別統計
            if len(segment_data) > 1:
                st.write("**月別パフォーマンス**")
                segment_data['year_month'] = segment_data['start_time'].dt.to_period('M')
                monthly_stats = segment_data.groupby('year_month').agg({
                    'elapsed_time_sec': ['count', 'mean', 'min'],
                    'avg_heartrate': 'mean',
                    'avg_cadence': 'mean',
                    'avg_speed_kmh': 'mean'
                }).round(1)
                st.dataframe(monthly_stats)
    
    except Exception as e:
        st.error(f"エラーが発生しました: {str(e)}")
        st.write("データベース接続設定を確認してください。")

if __name__ == "__main__":
    # 環境変数の設定例を表示
    with st.sidebar.expander("🔧 データベース設定"):
        st.write("""
        環境変数で設定してください:
        - DB_HOST (default: localhost)
        - DB_NAME (default: strava) 
        - DB_USER (default: postgres)
        - DB_PASSWORD (default: postgres)
        - DB_PORT (default: 5432)
        """)
    
    main()