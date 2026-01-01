#!/bin/bash
set -e

# Configuration
ENC_URL="http://localhost:2222"
ADMIN_USER="admin"
ADMIN_PASS="VPASS123!"
PROJ_PASS="PROJPASS123!"
HOME_TEST="/tmp/enc_test_home"

# Helper for logging
log() {
    echo -e "\033[1;34m[$(date +'%Y-%m-%d %H:%M:%S')] $1\033[0m"
}

# 0. Setup Local Env
log "--- Backup Verification Started ---"
rm -rf "$HOME_TEST"
mkdir -p "$HOME_TEST"

# Step 1: Installing ENC CLI Locally
log "Step 1: Installing ENC CLI Locally..."
pip install -e enc-cli --break-system-packages > /dev/null 2>&1 || pip install -e enc-cli > /dev/null 2>&1

log "Step 2: Rebuilding and Starting Server..."
# Set password for init_users.py
export ADMIN_PASSWORD="$ADMIN_PASS"
cd enc-server
# Force reset volumes and build to ensure all latest code is in image layers
docker compose down -v
docker compose build
docker compose up -d
cd ..
log "Waiting 15s for server to initialize..."
sleep 15

log "Step 3: Initializing ENC CLI Config..."
export HOME="$HOME_TEST"

# Use non-interactive CLI configuration
enc set-url "$ENC_URL"
enc set-username "$ADMIN_USER"

log "Step 4: Login via ENC CLI..."
# Using same password for system and vault
LOGIN_RES=$(enc login --password "$ADMIN_PASS" --vault-password "$ADMIN_PASS")
log "$LOGIN_RES"

# Capture session ID
SESSION_ID=$(echo "$LOGIN_RES" | grep -oE '[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}')
if [ -z "$SESSION_ID" ]; then
    log "FAILURE: Login failed, no session ID found."
    exit 1
fi
log "Login Success! Session ID: $SESSION_ID"

log "Step 5: Setting up SSH Key (bootstrap)..."
enc setup ssh-key --password "$ADMIN_PASS"

log "Step 6: Creating Project and Data..."
# Non-interactive project init
enc project init testproj --password "$PROJ_PASS"

# Create some test data in the project
enc project run testproj "echo 'Persistence Test Data' > test_data.txt"

# Verify data created (remote check via project run)
VERIFY_DATA=$(enc project run testproj "cat test_data.txt")
if [[ "$VERIFY_DATA" == *"Persistence Test Data"* ]]; then
    log "Data created and verified in remote project."
else
    log "FAILURE: Pre-backup verification failed!"
    echo "Got: $VERIFY_DATA"
    exit 1
fi

log "DEBUG: Server-side state BEFORE logout:"
docker exec -u admin enc_ssh_server ls -la /home/admin/.enc/vaults || log "DEBUG: .enc/vaults missing!"
docker exec -u admin enc_ssh_server cat /home/admin/.enc/system/config.json || log "DEBUG: config.json missing!"

log "Step 7: Unmounting and Logout (Triggering Backup)..."
# Just logout, server-side logout_session handles unmount and backup
enc logout

log "Logout complete."

log "Step 8: Verifying Backup File on Server..."
# Path in users.yaml is now /app/backups
if docker exec enc_ssh_server ls /app/backups/user_backup.enc > /dev/null 2>&1; then
    log "Backup file found at /app/backups/user_backup.enc"
else
    log "FAILURE: Backup file not found!"
    docker exec enc_ssh_server ls -la /app/backups
    exit 1
fi

log "Step 9: Killing Server and Cleaning Local State..."
cd enc-server
docker compose down -v
cd ..

log "Step 10: Restore via ENC CLI Login..."
cd enc-server
docker compose up -d
cd ..
log "Waiting 15s for server to reboot..."
sleep 15

# Re-login (Trigger restore)
RESTORE_RES=$(enc login --password "$ADMIN_PASS" --vault-password "$ADMIN_PASS")
log "$RESTORE_RES"

# Capture new session ID
NEW_SESSION_ID=$(echo "$RESTORE_RES" | grep -oE '[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}')
if [ -z "$NEW_SESSION_ID" ]; then
    log "FAILURE: Restore Login failed!"
    exit 1
fi
log "Login Success! Session ID: $NEW_SESSION_ID"

log "DEBUG: Server-side state after restore:"
docker exec -u admin enc_ssh_server ls -la /home/admin/.enc_cipher || log "DEBUG: .enc_cipher missing!"
docker exec -u admin enc_ssh_server ls -la /home/admin/.enc/vaults || log "DEBUG: .enc/vaults missing!"
docker exec -u admin enc_ssh_server cat /home/admin/.enc/system/config.json || log "DEBUG: config.json missing!"
docker exec enc_ssh_server mount | grep -q "/home/admin/.enc type fuse" || log "DEBUG: nothing mounted at .enc!"

log "Step 11: Verifying Data Restoration..."
# Create a fresh local dir for mounting
mkdir -p /tmp/enc_restore_local
# Use new session to mount project
enc project mount testproj /tmp/enc_restore_local --password "$PROJ_PASS" || {
    log "Mount failed."
}

if grep -q "Persistence Test Data" /tmp/enc_restore_local/test_data.txt 2>/dev/null; then
    log "SUCCESS: Data restored and verified!"
else
    log "FAILURE: Restored data mismatch or file missing!"
    ls -la /tmp/enc_restore_local 2>/dev/null || log "Local mount point empty."
    # Inspect server logs for errors
    log "--- Server Debug Log ---"
    docker exec enc_ssh_server cat /tmp/enc_debug.log
    exit 1
fi

# Cleanup
enc logout
log "--- Backup Verification Completed Successfully ---"
