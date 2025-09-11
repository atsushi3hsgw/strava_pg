#!/bin/bash -ex
#echo "#1. Clone application repository"
#git clone https://github.com/atsushi3hsgw/strava_pg.git

echo "#2. Install python3.11, create venv, and activate"
cd ~/strava_pg
sudo dnf install -y python3.11 python3.11-pip python3.11-devel gcc
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

echo "#3. Install requirements"
pip install -r requirements.txt

echo "#4. Setup postgreSQL tables"
cd /home/ec2-user/strava_pg
DbUser=$(aws ssm get-parameter --name "/streamlit-app/strava/db_user" --with-decryption --query "Parameter.Value" --output text)
DbPassword=$(aws ssm get-parameter --name "/streamlit-app/strava/db_passwd" --with-decryption --query "Parameter.Value" --output text)
PGPASSWORD="${DbPassword}" psql -h localhost -U ${DbUser} -d strava -f create_tables.sql

echo "#5. Setup nd start the service"
chmod +x aws/start_strava_segment_efforts.sh
sudo cp aws/strava_segment_efforts.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable strava_segment_efforts.service
sudo systemctl start strava_segment_efforts.service
