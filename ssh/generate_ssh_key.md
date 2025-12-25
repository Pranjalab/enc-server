# 🔑 SSH Key Generation & Management Guide

This guide explains how to generate, manage, and use secure SSH keys for accessing the **ENC Server**.

## 1. Why SSH Keys?
SSH keys provide a more secure way to log in than passwords alone. They are not susceptible to common brute-force attacks and allow for automated, password-less authentication.

## 2. Generating an SSH Key Pair

You can generate a new SSH key pair on your local machine using the `ssh-keygen` command.

### Step-by-Step Generation

1.  **Open your terminal.**
2.  **Run the generation command:**
    We recommend using the **Ed25519** algorithm for security and performance.
    
    ```bash
    ssh-keygen -t ed25519 -f ~/.ssh/enc_key -C "your_email@enc.com"
    ```

3.  **Choose a location:**
    The `-f ~/.ssh/enc_key` flag above ensures it's saved as `enc_key` to avoid overwriting your default keys.

4.  **Set a Passphrase (Recommended):**
    Enter a secure passphrase to encrypt the private key on your disk. This adds a second factor of security.

## 3. Understanding Your Keys

After generation, you will have two files:

*   **Private Key** (`enc_key`): **NEVER SHARE THIS.** This stays on your computer. It is your secret identity.
*   **Public Key** (`enc_key.pub`): **SHARE THIS FREELY.** You place this on the server you want to access.

## 4. Granting Admin Access to ENC Server

To access the ENC Server as the `admin` user via SSH keys:

1.  **Locate your Public Key:**
    ```bash
    cat ~/.ssh/enc_key.pub
    ```
    *Copy the output (it starts with `ssh-ed25519 ...`).*

2.  **Add to Server:**
    Navigate to the `ssh` directory in your server project:
    ```bash
    # From the root of the enc project
    cd enc-server/ssh
    ```

3.  **Update `authorized_keys`:**
    Paste your public key into the `authorized_keys` file in this directory.
    
    ```bash
    # Example appending your key
    echo "ssh-ed25519 AAAAC3NzaC1lZDI1N... your_email@example.com" >> authorized_keys
    ```

4.  **Connect:**
    The server automatically mounts this file. You can now connect:
    ```bash
    ssh -i ~/.ssh/enc_key -p 2222 admin@localhost
    ```

## 5. Security Best Practices
- **Rotate Keys:** Change your keys periodically.
- **Use Passphrases:** Always encrypt your private key.
- **Audit Access:** Regularly check `server/ssh/authorized_keys` to remove unauthorized keys.

## 6. Using with ENC Client
To let `enc-cli` and other tools use this key automatically, add it to your SSH Agent:

```bash
ssh-add ~/.ssh/enc_key
```

Or configure `~/.ssh/config`:
```ssh
Host localhost
    Port 2222
    User admin
    IdentityFile ~/.ssh/enc_key
```

## 7. Troubleshooting
### Host Key Verification Failed
If you see `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!` when connecting:
This happens because the Docker container was rebuilt, creating a new server fingerprint.
**Fix**: Remove the old key:
```bash
ssh-keygen -R "[localhost]:2222"
```
