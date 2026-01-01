# ==========================================
# Stage 1: Builder
# Pinning to specific golang version for stability and security (x/crypto requires 1.24+)
# ==========================================
FROM golang:1.24-alpine3.21 AS builder

# Install build dependencies
RUN apk add --no-cache \
    git \
    bash \
    openssl-dev \
    gcc \
    musl-dev \
    shadow

# Clone and build gocryptfs from source to fix x/crypto CVEs
WORKDIR /build
RUN git clone https://github.com/rfjakob/gocryptfs.git . && \
    git checkout v2.5.4 && \
    go get -u golang.org/x/crypto && \
    go build -tags openssl -o gocryptfs .

# ==========================================
# Stage 2: Runtime
# Pinning to alpine 3.21 for predictable security updates
# ==========================================
FROM alpine:3.21

LABEL maintainer="Pranjal Bhaskare"
LABEL description="ENC Server - Secure Encrypted Storage Manager"

# Install runtime dependencies
# exclude gocryptfs package as we copy our own built version
RUN apk add --no-cache \
    openssh \
    openrc \
    python3 \
    py3-pip \
    sudo \
    fuse \
    rsync \
    openssl \
    rclone \
    bash \
    netcat-openbsd

# Copy patched gocryptfs from builder
COPY --from=builder /build/gocryptfs /usr/local/bin/gocryptfs

# Enable user_allow_other for nested mounts (Crucial for gocryptfs)
RUN sed -i 's/#user_allow_other/user_allow_other/' /etc/fuse.conf

# ------------------------------------------
# SSH Configuration & Security Hardening
# ------------------------------------------
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config && \
    sed -i 's/#StrictModes yes/StrictModes yes/' /etc/ssh/sshd_config && \
    sed -i 's/Subsystem.*sftp.*internal-sftp/Subsystem sftp \/usr\/lib\/ssh\/sftp-server/' /etc/ssh/sshd_config && \
    { \
    echo "ClientAliveInterval 30"; \
    echo "ClientAliveCountMax 3"; \
    echo "TCPKeepAlive yes"; \
    echo "PermitUserEnvironment yes"; \
    echo "MaxAuthTries 6"; \
    echo "LoginGraceTime 60"; \
    echo "X11Forwarding no"; \
    echo "AllowTcpForwarding yes"; \
    } >> /etc/ssh/sshd_config && \
    mkdir -p /etc/ssh/ssh_host_keys

# ------------------------------------------
# User & Group Configuration
# ------------------------------------------
# Create enc group and configure sudoers for administrative tasks
RUN addgroup -S enc && \
    echo "admin ALL=(root) NOPASSWD: /usr/sbin/adduser, /usr/sbin/deluser, /usr/sbin/chpasswd, /bin/mkdir, /bin/chmod, /bin/chown, /usr/bin/tee, /bin/cp, /bin/grep, /usr/bin/find" > /etc/sudoers.d/admin && \
    chmod 0440 /etc/sudoers.d/admin

# ------------------------------------------
# Python Application Setup
# ------------------------------------------
WORKDIR /app

# Upgrade pip and install dependencies first to leverage Docker layer caching
# Note: We copy setup.py first to avoid re-installing dependencies on code changes
COPY setup.py /app/
RUN pip install --upgrade pip --no-cache-dir --break-system-packages && \
    pip install . --no-cache-dir --break-system-packages || true

# Copy the rest of the application source code
COPY . /app/

# Re-run pip install to ensure the package is correctly linked with the source
RUN pip install . --no-cache-dir --break-system-packages

# Set environment variables
ENV ENC_MODE=SERVER \
    PYTHONPATH=/app/src \
    BUILD_DATE=20241226_STANDALONE

# ------------------------------------------
# Restricted Shell & Policy Configuration
# ------------------------------------------
RUN chmod +x /app/src/enc_server/shell.py && \
    ln -sf /app/src/enc_server/shell.py /usr/local/bin/enc-shell && \
    echo "/usr/local/bin/enc-shell" >> /etc/shells && \
    mkdir -p /etc/enc && \
    cp /app/config/policy.json /etc/enc/policy.json && \
    chown root:enc /etc/enc/policy.json && \
    chmod 664 /etc/enc/policy.json

# ------------------------------------------
# Entrypoint & Healthcheck
# ------------------------------------------
RUN chmod +x /app/scripts/entrypoint.sh && \
    ln -sf /app/scripts/entrypoint.sh /entrypoint.sh

EXPOSE 22

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD nc -z 127.0.0.1 22 || exit 1

ENTRYPOINT ["/entrypoint.sh"]
