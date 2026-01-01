#!/bin/sh
set -e

# ==============================================================================
# Helper Functions
# ==============================================================================

log() {
    echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] [INFO] $*"
}

error() {
    echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] [ERROR] $*" >&2
    exit 1
}

# ==============================================================================
# Setup Stages
# ==============================================================================

setup_fuse() {
    log "Initializing FUSE..."
    if [ ! -e /dev/fuse ]; then
        log "Creating /dev/fuse device node..."
        mknod -m 666 /dev/fuse c 10 229 || error "Failed to create /dev/fuse"
    fi
    chmod 666 /dev/fuse || error "Failed to set permissions on /dev/fuse"
}

init_app_users() {
    log "Initializing system users (Admin & others)..."
    python3 -u /app/src/enc_server/init_users.py || error "User initialization failed"
    
    # Ensure correct permissions for admin home (admin is created by init_users.py)
    if id "admin" >/dev/null 2>&1; then
        chown -R admin /home/admin
    else
        log "Warning: 'admin' user not found after initialization."
    fi
}

setup_ssh_environment() {
    log "Configuring SSH environment for admin..."
    if id "admin" >/dev/null 2>&1; then
        mkdir -p /home/admin/.ssh
        {
            echo "ENC_SESSION_TIMEOUT=${ENC_SESSION_TIMEOUT:-600}"
            echo "PYTHONPATH=/app/src"
        } > /home/admin/.ssh/environment
        chown -R admin:enc /home/admin/.ssh
        chmod 600 /home/admin/.ssh/environment
    fi
}

provision_host_keys() {
    log "Checking SSH host keys..."
    mkdir -p /etc/ssh/ssh_host_keys
    if [ ! -f /etc/ssh/ssh_host_keys/ssh_host_ed25519_key ]; then
        log "Generating new host keys..."
        ssh-keygen -A
        cp /etc/ssh/ssh_host_*_key /etc/ssh/ssh_host_keys/
        cp /etc/ssh/ssh_host_*_key.pub /etc/ssh/ssh_host_keys/
    fi
    chmod 600 /etc/ssh/ssh_host_keys/*_key
}

setup_persistence_dirs() {
    log "Configuring persistence directories..."
    
    # Debug log setup
    touch /tmp/enc_debug.log
    chmod 666 /tmp/enc_debug.log
    
    # Backup directory setup
    mkdir -p /app/backups
    chown root:enc /app/backups
    chmod 775 /app/backups
    
    # Status file initialization
    if [ ! -f /app/backups/status.json ]; then
        echo "{}" > /app/backups/status.json
        if id "admin" >/dev/null 2>&1; then
            chown admin:enc /app/backups/status.json
        fi
        chmod 664 /app/backups/status.json
    fi
}

# ==============================================================================
# Main Execution
# ==============================================================================

log "Starting ENC Server initialization..."

setup_fuse
init_app_users
setup_ssh_environment
provision_host_keys
setup_persistence_dirs

log "Starting SSH Server..."
exec /usr/sbin/sshd -D -e \
    -h /etc/ssh/ssh_host_keys/ssh_host_ed25519_key \
    -h /etc/ssh/ssh_host_keys/ssh_host_rsa_key \
    -h /etc/ssh/ssh_host_keys/ssh_host_ecdsa_key
