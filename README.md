### How to Run the Updated App
1.  Prepare your Strava API application.  
    To use the Strava API, you will need to obtain an API key and other credentials from Strava.  

2.  Start your PostgreSQL database using `docker-compose`.
    ```bash
    docker-compose up -d
    ```

3.  Create the tables on your PostgreSQL database.
    ```
    docker exec -it strava_postgres bash
    cd /workspace
    psql -U postgres -d strava -f create_tables.sql
    ```

4.  Set the required environment variables.
    ```bash
    export STRAVA_CLIENT_ID=your_client_id
    export STRAVA_CLIENT_SECRET=your_client_secret
    export STRAVA_REDIRECT_URI=http://localhost:8501
    ```

4.  Run the Streamlit app.
    ```bash
    streamlit run strava_segment_efforts.py