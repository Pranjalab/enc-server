#!/bin/sh
set -e

# Ensure FUSE device exists
if [ ! -e /dev/fuse ]; then
    echo "Creating /dev/fuse..."
    mknod -m 666 /dev/fuse c 10 229
fi

# Ensure FUSE permissions (Crucial for non-root users)
chmod 666 /dev/fuse

# Ensure correct permissions for admin home (in case of volume mounts)
chown -R admin /home/admin

# Unlock admin account (Alpine locks passwordless accounts by default)
passwd -u admin || true

# Update admin password from env var if provided
if [ -n "$ADMIN_PASSWORD" ]; then
    echo "admin:$ADMIN_PASSWORD" | chpasswd
fi

# Start SSHD
echo "Starting SSH Server..."

# Propagate environment variables to SSH sessions (requires PermitUserEnvironment yes)
mkdir -p /home/admin/.ssh
echo "ENC_SESSION_TIMEOUT=${ENC_SESSION_TIMEOUT:-600}" > /home/admin/.ssh/environment
chown -R admin:enc /home/admin/.ssh
chmod 600 /home/admin/.ssh/environment || true

# Provision host keys if missing in volume
mkdir -p /etc/ssh/ssh_host_keys
if [ ! -f /etc/ssh/ssh_host_keys/ssh_host_ed25519_key ]; then
    ssh-keygen -A
    cp /etc/ssh/ssh_host_*_key /etc/ssh/ssh_host_keys/
    cp /etc/ssh/ssh_host_*_key.pub /etc/ssh/ssh_host_keys/
fi

# Ensure permissions
chmod 600 /etc/ssh/ssh_host_keys/*_key

/usr/sbin/sshd -D -e -h /etc/ssh/ssh_host_keys/ssh_host_ed25519_key -h /etc/ssh/ssh_host_keys/ssh_host_rsa_key -h /etc/ssh/ssh_host_keys/ssh_host_ecdsa_key
