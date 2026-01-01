#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Starting Verification of Admin Password Login and SSH Key Setup...${NC}"

# 1. Clean and Rebuild Server
echo "Step 1: Rebuilding Server..."
# Robustly find directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# We expect script to be in enc-server/tests
cd "$DIR/.." # Go to enc-server directory
echo "Working Directory: $(pwd)"
export ADMIN_PASSWORD=secure_admin_pass

echo "Stopping existing containers..."
docker compose down -v 2>/dev/null || true

echo "Building..."
docker compose build --no-cache

echo "Starting..."
docker compose up -d

echo "Waiting 15s for server to initialize..."
sleep 15

# 2. Configure Client (Assuming 'enc' is in PATH)
# Using a temporary config context/dir?
# 'enc init' writes to ~/.enc or ./.enc
# We'll use local config in the current test dir to avoid messing with user's global config.
# Wait, 'enc' uses CWD to find .enc?
# cli.py init: "Initialize Global (~/.enc) or Local (./.enc)".
# Enc class loads local precedence.
# I will run 'enc init' locally in tests dir.

cd tests
mkdir -p verification_env
cd verification_env

echo "Step 2: Initializing Local Client Config..."
# We can't easily auto-run 'enc init' because it uses Prompt.ask which might not support flags for everything?
# cli.py Step 184: init arg is path. Default ".".
# But it PROMPTS for global/local.
# And URL/User.
# I will use 'enc set-url' etc which works on the loaded config?
# But if no config exists, set-url might fail or default to global?
# enc.py Enc() init loads config.
# If I want to force local, I need to create the file first?
# Or use tools to write config.json?
# Let's try to write .enc/config.json manually to force local context.

mkdir -p .enc
cat <<EOF > .enc/config.json
{
    "url": "http://localhost:2222",
    "username": "admin",
    "ssh_key": "", 
    "session_id": null
}
EOF

echo "Config created at $(pwd)/.enc/config.json"
cat .enc/config.json

# 3. Test Password Login
echo "Step 3: Testing Login with Password..."
# We need to run enc from THIS directory so it picks up .enc
# Ensure checking connection first
enc check-connection || echo "Connection check failed (expected if auth required? No, checks reachability)"

if enc login --password "secure_admin_pass"; then
    echo -e "${GREEN}Login Successful!${NC}"
else
    echo -e "${RED}Login Failed!${NC}"
    exit 1
fi

# 4. Setup SSH Key
echo "Step 4: Setting up SSH Key..."
# This should generate key in .enc/ssh/... and upload it
if enc setup ssh-key --password "secure_admin_pass"; then
     echo -e "${GREEN}SSH Key Setup Successful!${NC}"
else
     echo -e "${RED}SSH Key Setup Failed!${NC}"
     exit 1
fi

# 5. Verify Key Auth (Logout and Login without password)
echo "Step 5: Verifying Key Authentication..."
enc logout

echo "Logging in (should use new key)..."
if enc login; then
    echo -e "${GREEN}Key Authentication Successful!${NC}"
else
    echo -e "${RED}Key Authentication Failed!${NC}"
    exit 1
fi

echo -e "${GREEN}ALL TESTS PASSED!${NC}"
