# Stage 1: Builder
# Pinning to specific golang version for stability and security (x/crypto requires 1.24+)
FROM golang:1.24-alpine3.21 AS builder

# Install build dependencies
RUN apk add --no-cache git bash openssl-dev gcc musl-dev

# Clone and build gocryptfs from source to fix x/crypto CVEs
WORKDIR /build
RUN git clone https://github.com/rfjakob/gocryptfs.git . && \
    git checkout v2.5.4 && \
    go get -u golang.org/x/crypto && \
    go build -tags openssl -o gocryptfs .

# Stage 2: Runtime
# Pinning to alpine 3.21 for predictable security updates
FROM alpine:3.21

# Install runtime dependencies
# exclude gocryptfs package as we copy our own
RUN apk add --no-cache \
    openssh \
    openrc \
    python3 \
    py3-pip \
    sudo \
    fuse \
    rsync \
    openssl

# Copy patched gocryptfs
COPY --from=builder /build/gocryptfs /usr/local/bin/gocryptfs

# Upgrade pip to fix CVE-2025-8869
RUN pip install --upgrade pip --break-system-packages

# Configure SSH
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config && \
    sed -i 's/#StrictModes yes/StrictModes no/' /etc/ssh/sshd_config && \
    sed -i 's/Subsystem.*sftp.*internal-sftp/Subsystem sftp \/usr\/lib\/ssh\/sftp-server/' /etc/ssh/sshd_config && \
    echo "ClientAliveInterval 30" >> /etc/ssh/sshd_config && \
    echo "ClientAliveCountMax 3" >> /etc/ssh/sshd_config && \
    echo "TCPKeepAlive yes" >> /etc/ssh/sshd_config && \
    echo "PermitUserEnvironment yes" >> /etc/ssh/sshd_config

# Create enc group and admin user
# Force secure shell for admin
RUN addgroup enc && \
    adduser -D -s /usr/local/bin/enc-shell -G enc admin && \
    echo "admin ALL=(root) NOPASSWD: /usr/sbin/adduser, /usr/sbin/deluser, /usr/sbin/chpasswd, /bin/mkdir, /bin/chmod, /bin/chown, /usr/bin/tee, /bin/cp, /bin/grep, /usr/bin/find" > /etc/sudoers.d/admin && \
    chmod 0440 /etc/sudoers.d/admin

# Install ENC tool (from server source)
WORKDIR /app
# Copy the entire server directory to /app
COPY enc-server/ /app/
ENV BUILD_DATE=20241226_HARDENED
RUN pip install . --break-system-packages

# Copy Restricted Shell (now in src)
# shell.py location is at /app/src/enc_server/shell.py
# But we copy it to bin for easy access as simple script
COPY enc-server/src/enc_server/shell.py /usr/local/bin/enc-shell
COPY enc-server/config/policy.json /etc/enc/policy.json
RUN chmod +x /usr/local/bin/enc-shell && \
    chown root:enc /etc/enc/policy.json && \
    chmod 664 /etc/enc/policy.json
ENV ENC_MODE=SERVER

# Setup Entrypoint
COPY enc-server/scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22

# Healthcheck to ensure SSHD is listening
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD nc -z 127.0.0.1 22 || exit 1

ENTRYPOINT ["/entrypoint.sh"]
