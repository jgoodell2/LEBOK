#!/bin/bash
set -e # Exit immediately if any command fails

# User and path definitions
SERVICE_USER="lebok"
SERVICE_NAME="lebok-microservice"
DEV_REPO_PATH="/home/natou/LEBOK" # <-- !! Set this to the path where you cloned the repo
PROD_PATH="/opt/lebok-microservice"
VENV_PATH="$PROD_PATH/lebok-env"
SERVICE_FILE_SOURCE="$PROD_PATH/$SERVICE_NAME.service"
SERVICE_FILE_DEST="/etc/systemd/system/$SERVICE_NAME.service"

echo ">>> Checking for system user '$SERVICE_USER'..."
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
    echo "    -> User not found. Creating system user '$SERVICE_USER'..."
    sudo adduser lebok --system
    echo "    -> User created."
else
    echo "    -> User already exists."
fi

echo ">>> Ensuring production directory exists..."
sudo mkdir -p "$PROD_PATH"
# Set ownership on the main dir so rsync can write
sudo chown "$SERVICE_USER": "$PROD_PATH"

echo ">>> Pulling latest code into $DEV_REPO_PATH..."
cd $DEV_REPO_PATH
git pull

echo ">>> Syncing files to production..."

# Sync the microservice, deleting old files within this dir
sudo rsync -av --exclude='.env' \
    "$DEV_REPO_PATH/gql_microservice/" \
    "$PROD_PATH/"

# Sync the queries, deleting old files within this dir
sudo rsync -av --delete \
    "$DEV_REPO_PATH/queries/" \
    "$PROD_PATH/queries/"

# Sync the requirements file
sudo rsync -av \
    "$DEV_REPO_PATH/requirements.txt" \
    "$PROD_PATH/requirements.txt"

# Ensure 'lebok' still owns all the new/updated files
sudo chown -R lebok: "$PROD_PATH/"

echo ">>> Installing systemd service..."
# Force-create the symlink from the repo file to the systemd directory
sudo ln -sf "$SERVICE_FILE_SOURCE" "$SERVICE_FILE_DEST"

# Reload systemd
echo "    -> Reloading systemd daemon..."
sudo systemctl daemon-reload

echo ">>> Checking for virtual environment..."
if [ ! -d "$VENV_PATH" ]; then
    echo "    -> Virtual environment not found. Creating..."
    sudo -u lebok /usr/bin/python3 -m venv "$VENV_PATH"
    echo "    -> venv created."
else
    echo "    -> Virtual environment found."
fi

echo ">>> Installing/checking dependencies..."
# Run pip install as the lebok user
sudo -u lebok "$PROD_PATH/lebok-env/bin/pip" install -r "$PROD_PATH/requirements.txt"

echo ">>> Restarting the service..."
sudo systemctl restart lebok-microservice

echo ">>> Done. Checking status:"
sudo systemctl status lebok-microservice --no-pager
