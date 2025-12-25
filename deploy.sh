#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}ENC Server Deployment Script${NC}"

# Check for Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed.${NC}"
    echo "Please install Docker and Docker Compose before continuing."
    exit 1
fi

# Build and Start
echo "Building and starting ENC Server containers..."
docker compose up -d --build

# Verify
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Server deployed successfully!${NC}"
    echo "Container: enc_ssh_server"
    echo "Port: 2222"
    echo ""
    echo -e "View logs with: ${GREEN}docker logs -f enc_ssh_server${NC}"
else
    echo -e "${RED}Deployment failed.${NC}"
    exit 1
fi
