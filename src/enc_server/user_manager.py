import yaml
import os
import subprocess
import getpass
import sys
from pathlib import Path
from enc_server.enc import EncServer
from enc_server.authentications import Authentication

class UserManager:
    def __init__(self, config_path):
        self.config_path = config_path
        self.server = EncServer()
        self.auth = Authentication()
        self.users_config = self._load_config()

    def _load_config(self):
        if not os.path.exists(self.config_path):
            print(f"Warning: Config file {self.config_path} not found.")
            return {}
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f) or {}

    def _user_exists(self, username):
        try:
            subprocess.run(["id", username], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except subprocess.CalledProcessError:
            return False

    def _create_system_user(self, username, password):
        print(f"Creating system user: {username}")
        # Create user with restricted shell
        cmd = ["sudo", "adduser", "-D", "-s", "/usr/local/bin/enc-shell", "-G", "enc", username]
        subprocess.run(cmd, check=True)
        
        # Set Password
        p = subprocess.Popen(["sudo", "chpasswd"], stdin=subprocess.PIPE, text=True)
        p.communicate(input=f"{username}:{password}")
        if p.returncode != 0:
             raise RuntimeError(f"Failed to set password for {username}")

    def _setup_ssh_key(self, username, config):
        ssh_key_path = config.get("ssh_key")
        if ssh_key_path:
            # Resolve path relative to /app (project root in container) or absolute
            real_key_path = os.path.abspath(os.path.join("/app", ssh_key_path)) if not os.path.isabs(ssh_key_path) else ssh_key_path
            
            if os.path.exists(real_key_path):
                with open(real_key_path, 'r') as f:
                    key_content = f.read().strip()
                self.server.add_ssh_key(username, key_content)
                print(f"Added SSH key for {username}")
            else:
                print(f"Warning: SSH key file {real_key_path} not found.")

    def _setup_user_config(self, username, config):
        # Store backup config in /home/<user>/.enc_config/user.yml
        backup_config = config.get("backup")
        if backup_config or config.get("url"):
            config_dir = Path(f"/home/{username}/.enc_config")
            if not config_dir.exists():
                config_dir.mkdir(parents=True, exist_ok=True)
                # Fix ownership immediately
                subprocess.run(["chown", "-R", f"{username}:enc", str(config_dir)], check=True)
                subprocess.run(["chmod", "700", str(config_dir)], check=True)
            
            user_config_path = config_dir / "user.yml"
            
            user_data = {}
            if backup_config:
                user_data["backup"] = backup_config
            if config.get("url"):
                user_data["url"] = config.get("url")

            with open(user_config_path, 'w') as f:
                yaml.dump(user_data, f)
                
            # Fix ownership of the file
            subprocess.run(["chown", f"{username}:enc", str(user_config_path)], check=True)
            print(f"User configuration saved for {username}")

    def _update_policy(self, username):
        role = "admin" if username == "admin" else "user"
        if username not in self.auth.get_all_users():
             self.auth.policy["users"][username] = {"role": role, "permissions": []}
             self.auth.save_policy()
             print(f"Policy updated for {username} as {role}")

    def init_users(self):
        print("Initializing Users...")
        
        # 1. Process users from Config
        for username, config in self.users_config.items():
            if not self._user_exists(username):
                # Check ENV first for automation
                env_pass = os.environ.get(f"{username.upper()}_PASSWORD")
                if not env_pass and username == "admin":
                    env_pass = os.environ.get("ADMIN_PASSWORD")
                
                if env_pass:
                    password = env_pass
                    print(f"Using environment password for {username}")
                else:
                    # In Docker/Automated mode, we skip if no password
                    print(f"Error: No password provided for new user '{username}' (env {username.upper()}_PASSWORD missing). Skipping.")
                    continue
                
                try:
                    self._create_system_user(username, password)
                except Exception as e:
                    print(f"Critical error creating user {username}: {e}")
                    raise 

                self._setup_ssh_key(username, config)
                self._setup_user_config(username, config)
                self._update_policy(username)
            else:
                print(f"User {username} already exists. checking config updates...")
                self._setup_ssh_key(username, config)
                self._setup_user_config(username, config)
                self._update_policy(username)

        # 2. Safety Check: Ensure 'admin' exists
        if not self._user_exists("admin"):
             print("\n[Admin Setup] 'admin' user missing.")
             admin_pass = os.environ.get("ADMIN_PASSWORD")
             if admin_pass:
                 try:
                     self._create_system_user("admin", admin_pass)
                     self._update_policy("admin")
                     print("Admin user created.")
                 except Exception as e:
                     raise RuntimeError(f"Critical: Failed to create admin user: {e}")
             else:
                 raise RuntimeError("Critical: 'admin' user is missing and no way to create it (ADMIN_PASSWORD or users.yaml missing).")
