import os
import shutil
import yaml
import getpass
import sys
import json
import subprocess
import threading
import time
from pathlib import Path
from .backup_packer import BackupPacker
from .handlers.local_handler import LocalHandler
from .handlers.gdrive_handler import GDriveHandler
from .debug import debug_log
from argon2 import PasswordHasher, low_level
import hashlib

class BackupManager:
    CIPHER_DIR_NAME = ".enc_cipher"
    MOUNT_POINT_NAME = ".enc"
    
    def log(self, msg):
        """Log message and use shared debug_log."""
        debug_log(f"BackupManager: {msg}")

    def _update_status(self, handler_name, available=None, status=None):
        """Update persistent status in /app/backups/status.json."""
        status_file = Path("/app/backups/status.json")
        try:
            data = {}
            if status_file.exists():
                with open(status_file, 'r') as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
            
            user_data = data.get(self.username, {})
            handler_data = user_data.get(handler_name, {"available": False, "status": "None"})
            
            if available is not None:
                handler_data["available"] = available
            if status is not None:
                handler_data["status"] = status
            
            user_data[handler_name] = handler_data
            data[self.username] = user_data
            
            # Atomic save
            temp_file = status_file.with_suffix(".tmp")
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            temp_file.replace(status_file)
        except Exception as e:
            self.log(f"Error updating status.json: {e}")
    
    def __init__(self, username):
        self.username = username
        self.home = Path(f"/home/{username}")
        self.enc_mount = self.home / self.MOUNT_POINT_NAME
        self.enc_cipher = self.home / self.CIPHER_DIR_NAME
        self.config_dir = self.home / ".enc_config"
        self.user_config_file = self.config_dir / "user.yml"
        
        self.packer = BackupPacker()
        self.backup_configs = self._get_backup_config() or {}
        self.handlers = {}
        self.handler_statuses = {}
        
        # Initialize configured handlers
        for key, config in self.backup_configs.items():
            if key == "local":
                self.handlers[key] = LocalHandler(config)
            elif key == "gdrive":
                self.handlers[key] = GDriveHandler(config)
            
            if key in self.handlers:
                is_ok = self.handlers[key].verify()
                self.handler_statuses[key] = "connected" if is_ok else "disconnected"
                self._update_status(key, available=is_ok) # Persist availability
                if not is_ok:
                    self.log(f"Warning: Backup handler '{key}' is disconnected or inaccessible.")
                else:
                    self.log(f"Backup handler '{key}' connected.")

    def _get_backup_config(self):
        if self.user_config_file.exists():
            with open(self.user_config_file) as f:
                cfg = yaml.safe_load(f)
                return cfg.get("backup")
        return None

    def _get_handler(self, backup_config):
        for key in ["local", "gdrive"]:
             if key in backup_config:
                 return self.handlers.get(key), backup_config[key]
        return None, None

    def perform_restore_and_mount(self, system_password):
        """Restore backup and mount vault. Prioritize local, then remote."""
        self.log(f"Attempting restore for user {self.username}...")
        
        if not self.backup_configs:
            self.log("No backup configuration found. Initializing fresh.")
            self._init_fresh_enc(system_password)
            return {
                "status": "success", 
                "source": "none", 
                "handler_statuses": self.handler_statuses,
                "message": "Initialized fresh environment"
            }

        user_backup_file = self.home / "user_backup.enc"
        restored = False
        source = "none"

        # 1. Try Local First
        if "local" in self.handlers and self.handler_statuses["local"] == "connected":
            handler = self.handlers["local"]
            if handler.pull(str(user_backup_file)):
                self.log("Backup pulled from local storage.")
                restored = True
                source = "local"

        # 2. Try GDrive if local failed
        if not restored and "gdrive" in self.handlers and self.handler_statuses["gdrive"] == "connected":
            handler = self.handlers["gdrive"]
            if handler.pull(str(user_backup_file)):
                self.log("Backup pulled from Google Drive.")
                restored = True
                source = "gdrive"

        if restored:
             if not system_password:
                 self.log("ERROR: Backup found but no password provided for restoration.")
                 raise ValueError("Backup restoration requires a password.")
             
             try:
                 # Ensure no stale state exists
                 if os.path.ismount(str(self.enc_mount)):
                     self.log("Stale mount detected. Unmounting...")
                     subprocess.run(["fusermount", "-u", str(self.enc_mount)], check=False)

                 if self.enc_cipher.exists():
                     self.log(f"Cleaning up existing cipher directory {self.enc_cipher}...")
                     shutil.rmtree(self.enc_cipher, ignore_errors=True)

                 # Decrypt/Unpack
                 self.packer.unpack(str(user_backup_file), str(self.home), self._derive_system_password(system_password))
                 self.log("Decrypted and unpacked successfully.")
                 
                 # Now Mount
                 self._mount_enc(system_password) # _mount_enc will handle derivation
                 
                 # Save derived password to secure token file inside the mounted vault
                 self._cache_vault_token(system_password)

                 # Update status to mounted for all configured handlers
                 for key in self.handlers:
                     self._update_status(key, status="mounted")

                 # Cleanup temporary backup file after successful mount
                 if os.path.exists(user_backup_file):
                    os.remove(user_backup_file)
                 
                 return {
                     "status": "success", 
                     "source": source,
                     "handler_statuses": self.handler_statuses
                 }

             except Exception as e:
                 self.log(f"Restore Error: {e}")
                 raise
        else:
            self.log("No backup found or handlers disconnected. Trying fresh init.")
            self._init_fresh_enc(system_password)
            return {
                "status": "success", 
                "source": "none", 
                "handler_statuses": self.handler_statuses,
                "message": "No backup found or disconnected, initialized fresh"
            }

    def perform_backup_and_unmount(self, system_password=None):
        """Unmount and backup vault. Prioritize local, then background remote."""
        
        # Try to retrieve cached password if not provided
        if not system_password:
             try:
                 token_file = self.enc_mount / "system" / ".vault_token"
                 if token_file.exists():
                     with open(token_file, "r") as f:
                         system_password = f.read().strip()
                     self.log("Retrieved vault password token from secure cache.")
                 else:
                     self.log("Vault token not found in cache.")
             except Exception as e:
                 self.log(f"Warning: Failed to read cached password: {e}")
        else:
            # If provided raw, derive it
            system_password = self._derive_system_password(system_password)

        self.log(f"Attempting backup for user {self.username}...")
        results = {"local": "skipped", "gdrive": "skipped"}
        
        # 1. Unmount
        if os.path.ismount(str(self.enc_mount)):
            self.log("Unmounting .enc...")
            try:
                subprocess.run(["fusermount", "-u", str(self.enc_mount)], check=True)
            except subprocess.CalledProcessError as e:
                self.log(f"Unmount failed: {e}. Cannot backup safely.")
                return {
                    "status": "error", 
                    "message": f"Unmount failed: {e}", 
                    "backups": results,
                    "handler_statuses": self.handler_statuses
                }

        if not self.backup_configs:
            self.log("No backup config. Persistence only local.")
            return {
                "status": "success", 
                "message": "No backup config, kept local", 
                "backups": results,
                "handler_statuses": self.handler_statuses
            }

        if not self.enc_cipher.exists():
            self.log(".enc_cipher missing! Cannot backup.")
            return {
                "status": "error", 
                "message": ".enc_cipher missing", 
                "backups": results,
                "handler_statuses": self.handler_statuses
            }

        user_backup_file = self.home / "user_backup.enc"
        
        try:
             # 2. Pack
             self.log("Packing .enc_cipher...")
             if not system_password:
                 self.log("Error: No password provided for backup encryption via CLI or cache.")
                 return {
                    "status": "error",
                    "message": "Password required for backup encryption",
                     "backups": results,
                     "handler_statuses": self.handler_statuses
                 }
             self.packer.pack(str(self.enc_cipher), str(user_backup_file), system_password)
             
             # 3. Local Backup (High Priority)
             local_success = False
             local_backup_path = None
             if "local" in self.handlers and self.handler_statuses["local"] == "connected":
                 handler = self.handlers["local"]
                 self.log("Pushing to local backup...")
                 if handler.push(str(user_backup_file)):
                     self.log("Local backup successful.")
                     local_success = True
                     results["local"] = "success"
                     self._update_status("local", status="backuped")
                     # Determine the path for background threads to use
                     dest_path = os.path.expanduser(handler.config.get("path", ""))
                     local_backup_path = os.path.join(dest_path, "user_backup.enc")
                 else:
                     self.log("Local backup failed!")
                     results["local"] = "failed"
                     self._update_status("local", status="Failed")
             elif "local" in self.backup_configs:
                 results["local"] = "disconnected"

             # 4. Security Cleanup (Clean enc_cipher and temp backup file ONLY if local succeeded)
             if local_success:
                 self.log("Cleaning up .enc_cipher and temporary backup file.")
                 shutil.rmtree(self.enc_cipher)
                 if os.path.exists(user_backup_file):
                     os.remove(user_backup_file)
             
             # 5. Background Remote Backup (e.g. GDrive)
             if "gdrive" in self.handlers and self.handler_statuses["gdrive"] == "connected":
                 source_for_remote = local_backup_path if local_success else str(user_backup_file)
                 self.log(f"Starting background GDrive sync from {source_for_remote}...")
                 results["gdrive"] = "pending"
                 self._update_status("gdrive", status="syncing")
                 
                 # Use subprocess.Popen to detach from the dying parent process
                 import sys
                 cmd = [
                     sys.executable, "-m", "enc_server.background_sync",
                     self.username, "gdrive", source_for_remote
                 ]
                 subprocess.Popen(
                     cmd, 
                     start_new_session=True, # Detach
                     stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL,
                     close_fds=True,
                     env=os.environ.copy() # Pass env for rclone config
                 )
             elif "gdrive" in self.backup_configs:
                 results["gdrive"] = "disconnected"

             return {
                 "status": "success", 
                 "backups": results,
                 "handler_statuses": self.handler_statuses
             }

        except Exception as e:
            self.log(f"Backup Error: {e}")
            return {
                "status": "error", 
                "message": str(e), 
                "backups": results,
                "handler_statuses": self.handler_statuses
            }

    def _background_sync_worker(self, handler_name, source_file):
        """Worker thread for background remote sync with retry logic."""
        handler = self.handlers.get(handler_name)
        try:
            if not handler:
                debug_log(f"SyncWorker: Handler {handler_name} not found.")
                return

            max_retries = 10
            delay = 5 # Start with 5 seconds
            
            for i in range(max_retries):
                debug_log(f"SyncWorker: Attempt {i+1} for {handler_name}...")
                try:
                    if handler.push(source_file):
                        debug_log(f"SyncWorker: {handler_name} sync successful.")
                        self._update_status(handler_name, status="backuped")
                        return
                except Exception as e:
                    # Assuming handler.push might raise a specific exception for quota issues
                    # Or, if handler.push returns False, it might set an internal flag or log a specific message
                    # For now, we'll check the exception message if it's propagated.
                    debug_log(f"SyncWorker: {handler_name} push failed with exception: {e}")
                    if "storageQuotaExceeded" in str(e): # Placeholder for actual error detection
                        debug_log(f"SyncWorker: {handler_name} storage quota exceeded. Aborting retries.")
                        self._update_status(handler_name, status="Failed: Quota Exceeded")
                        return # Abort immediately
                
                debug_log(f"SyncWorker: {handler_name} sync failed. Retrying in {delay}s...")
                time.sleep(delay)
                delay = min(delay * 2, 300) # Exponential backoff up to 5 mins

            debug_log(f"SyncWorker: {handler_name} sync failed after {max_retries} attempts.")
            self._update_status(handler_name, status="Failed")
        except Exception as e:
            debug_log(f"SyncWorker CRITICAL ERROR: {e}")
            import traceback
            debug_log(traceback.format_exc())

    def _init_fresh_enc(self, password=None):
        """Initialize a fresh encrypted environment if missing, then mount."""
        if not self.enc_cipher.exists():
            self.log("Initializing fresh encrypted vault...")
            self.enc_cipher.mkdir(mode=0o700, parents=True)
            p = password if password else getpass.getpass("Set vault password: ")
            
            derived_p = self._derive_system_password(p)
            self.log("Running gocryptfs -init...")
            subprocess.run(["gocryptfs", "-init", "-quiet", "-scryptn", "10", str(self.enc_cipher)], 
                           input=derived_p.encode(), check=True)
            self._mount_enc(p)
            self._cache_vault_token(p)
        else:
            self.log("Cipher directory exists. Ensuring it's mounted.")
            self._mount_enc(password)
            self._cache_vault_token(password)

    def _mount_enc(self, password):
        """Mount the encrypted vault at ~/.enc."""
        self.log(f"Mounting {self.enc_cipher} to {self.enc_mount}...")
        self.enc_mount.mkdir(parents=True, exist_ok=True)
        
        # Check if already mounted
        if os.path.ismount(str(self.enc_mount)):
             self.log("Already mounted.")
             return

        if not password:
             self.log("ERROR: No password provided for mount.")
             raise ValueError("Password required for mount")

        # Derive system password
        derived_password = self._derive_system_password(password)

        try:
            # Capture output for debugging
            res = subprocess.run(["gocryptfs", "-quiet", "-allow_other", str(self.enc_cipher), str(self.enc_mount)], 
                               input=derived_password, check=True, capture_output=True, text=True)
            self.log("Vault mounted successfully at ~/.enc")
        except subprocess.CalledProcessError as e:
            self.log(f"Mount failed with code {e.returncode}")
            self.log(f"STDOUT: {e.stdout}")
            self.log(f"STDERR: {e.stderr}")
            raise

    def _derive_system_password(self, password):
        """Derive a deterministic high-entropy system password using Argon2id."""
        if not password:
            return None
            
        # If already a hash (64 chars hex), assume already derived
        if len(password) == 64 and all(c in "0123456789abcdefABCDEF" for c in password):
            return password

        # Use argon2 low_level for deterministic hashing
        # Salt must be at least 8 bytes. We'll use a deterministic salt based on username.
        salt = hashlib.sha256(self.username.encode()).digest()[:16]
        
        hash_bytes = low_level.hash_secret_raw(
            secret=password.encode(),
            salt=salt,
            time_cost=4,
            memory_cost=65536,
            parallelism=2,
            hash_len=32,
            type=low_level.Type.ID
        )
        return hash_bytes.hex()

    def _cache_vault_token(self, password):
        """Store the derived vault token in the mounted vault for seamless logout."""
        if not password:
            return
            
        try:
            token_file = self.enc_mount / "system" / ".vault_token"
            os.makedirs(token_file.parent, exist_ok=True)
            
            derived_p = self._derive_system_password(password)
            
            # Write with restricted permissions
            with open(token_file, "w") as f:
                f.write(derived_p)
            os.chmod(token_file, 0o600)
            self.log("Vault password token cached securely in .enc/system/.vault_token")
        except Exception as e:
            self.log(f"Warning: Failed to cache vault password: {e}")
