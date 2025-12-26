# ENC Server Documentation

> **Part of the [ENC Ecosystem](https://github.com/Pranjalab/enc)**
>
> 📚 **[Read the Full Documentation](https://pranjalab.github.io/enc)**

The **ENC Server** is the hardened core of the ecosystem. It provides the secure execution environment, project storage, and SSH access control.

## 🏗️ Architecture

The server creates a security boundary around your code:

1.  **Encrypted Storage**: Projects are stored as encrypted ciphertexts using `gocryptfs`. Keys are never persisted in plaintext on the server disk.
2.  **SSH Bastion**: Access is strictly controlled via an OpenSSH server running on a non-standard port (`2222`).
3.  **Restricted Shell**: Users are confined to a custom `enc-shell`, preventing unauthorized traversal of the host OS.
4.  **Ephemeral Runtime**: Code execution happens in a memory-safe buffer, wiped immediately after use.

---

## 🛠️ Deployment Guide

### Prerequisites
*   Docker & Docker Compose installed on the host machine.
*   Port `2222` free on the host (or configurable in `docker-compose.yml`).

### 1. Build and Launch
Navigate to the `server` directory and start the container:

```bash
cd enc-server
./deploy.sh
# Or manually: docker compose up -d --build
```

### 2. Verify Installation
Check that the container is running:
```bash
docker ps
# You should see 'enc_server' listening on 0.0.0.0:2222
```

---

## 🔑 Admin Management

The server uses a **local policy file** and **SSH authorized keys** to manage users.

### Connecting as Admin
The default `admin` user is configured during the build. To connect manually (for debugging):
```bash
ssh -p 2222 admin@localhost
```

### Adding a New User
You manage users through the ENC CLI (connected as an admin) or by manually editing the server state if you have root access to the container.

**Using CLI (Recommended):**
```bash
# Connect with your local CLI
enc login
# Create a new user
enc user create new_dev --role user
```

**Manual / Emergency Access:**
Access the running container to manage users directly:
```bash
docker exec -it enc_ssh_server /bin/bash
# Inside the container, you can check logs or inspect storage
ls /home
```

---

## 📂 Project Storage Structure

All user data is stored in the persistent volume mapped to `/home`.

*   `/home/<user>/.enc/config.json`: User-specific configuration and project list.
*   `/home/<user>/.enc/vault/`: Encrypted ciphertext folders for each project.
*   `/home/<user>/.enc/run/`: Active mount points (empty when not in session).

---

## 🔒 Security Constraints

*   **No Root Access**: Regular users cannot `sudo` or access other users' directories.
*   **Locked Down Network**: The container should be firewalled to only allow inbound traffic on port `2222`.
*   **Policy Enforcement**: The `policy.json` file (internal) defines global roles and permissions.

---

## ⏱️ Session Monitoring Protocol

The ENC Server implements strict session management to ensure security.

### Server-Side Monitoring
*   **Inactivity Timeout**: Sessions are automatically closed if no commands are executed for **10 minutes** (600 seconds).
*   **Mount Activity Keep-Alive**: Active file modifications in a mounted project will refresh the session timer, keeping it alive during coding sessions.
*   **Closure Conditions**:
    1.  **Command Timeout**: User is idle (no CLI commands) > 10 mins.
    2.  **Mount Timeout**: User stops editing files in a mounted project > 10 mins.
    3.  **Explicit Logout**: User runs `enc logout`.

### Client-Side Behavior
*   The CLI (`enc-client`) validates the session ID with the server before every critical command.
*   If the server reports the session as expired ("Please login first"), the CLI will prompt the user to re-authenticate.

---

## 🚑 Troubleshooting

**Log Analysis**
If connections are failing, check the container logs:
```bash
docker logs -f enc_ssh_server
```

**"Permission Denied" (publickey)**
*   Ensure the user's public key is correctly added to `/home/<user>/.ssh/authorized_keys`.
*   Check permissions: `.ssh` must be `700`, `authorized_keys` must be `600`, and owned by the user.

**"Device not configured" (Zombie Mounts)**
If the server crashes while a project is mounted, you might see stale mount points.
*   Restart the container: `docker restart enc_ssh_server`
*   The ENC system now includes auto-cleanup on startup and logout to mitigate this.
