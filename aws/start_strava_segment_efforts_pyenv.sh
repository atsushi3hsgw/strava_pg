#!/bin/bash
set -e

# Enable the virtual environment
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

# Force application of the project's pyenv virtual environment
# (Unnecessary if .python-version exists)
pyenv activate strava-pg-env

# Configure AWS Region (Tokyo Region)
export AWS_REGION="ap-northeast-1"

# Retrieve confidential information from the Parameter Store and set it as an environment variable
export STRAVA_CLIENT_ID=$(aws ssm get-parameter --name "/streamlit-app/strava/client_id" --with-decryption --query "Parameter.Value" --output text)
export STRAVA_CLIENT_SECRET=$(aws ssm get-parameter --name "/streamlit-app/strava/client_secret" --with-decryption --query "Parameter.Value" --output text)
export STRAVA_REDIRECT_URI=$(aws ssm get-parameter --name "/streamlit-app/strava/redirect_uri" --with-decryption --query "Parameter.Value" --output text)

# Set the database connection information in the environment variables
export DB_USER=$(aws ssm get-parameter --name "/streamlit-app/strava/db_user" --with-decryption --query "Parameter.Value" --output text)
export DB_PASSWORD=$(aws ssm get-parameter --name "/streamlit-app/strava/db_passwd" --with-decryption --query "Parameter.Value" --output text)
export DB_HOST="localhost"
export DB_NAME="strava"

# Start the Streamlit application
streamlit run strava_segment_efforts.py --server.address 0.0.0.0 --server.port 8501