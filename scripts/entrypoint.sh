#!/bin/sh
set -e

# Ensure FUSE device exists
if [ ! -e /dev/fuse ]; then
    echo "Creating /dev/fuse..."
    mknod -m 666 /dev/fuse c 10 229
fi

# Ensure correct permissions for admin home (in case of volume mounts)
chown -R admin /home/admin

# Unlock admin account (Alpine locks passwordless accounts by default)
passwd -u admin || true

# Start SSHD
echo "Starting SSH Server..."

# Provision host keys if missing in volume
if [ ! -f /etc/ssh/ssh_host_keys/ssh_host_ed25519_key ]; then
    ssh-keygen -A
    cp /etc/ssh/ssh_host_*_key /etc/ssh/ssh_host_keys/
    cp /etc/ssh/ssh_host_*_key.pub /etc/ssh/ssh_host_keys/
fi

# Ensure permissions
chmod 600 /etc/ssh/ssh_host_keys/*_key

/usr/sbin/sshd -D -e -h /etc/ssh/ssh_host_keys/ssh_host_ed25519_key -h /etc/ssh/ssh_host_keys/ssh_host_rsa_key -h /etc/ssh/ssh_host_keys/ssh_host_ecdsa_key
