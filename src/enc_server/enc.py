import os
import json
import uuid
import datetime
import subprocess
from pathlib import Path
from rich.console import Console
from enc_server.authentications import Authentication
from enc_server.session import Session

console = Console()

class EncServer:
    def __init__(self):
        self.enc_root = Path.home() / ".enc"
        self.config_file = self.enc_root / "config.json"
        self.session_dir = self.enc_root / "sessions"
        self.vault_dir = self.enc_root / "vault"
        self.run_dir = self.enc_root / "run"
        
        # Ensure directories exist
        for d in [self.session_dir, self.vault_dir, self.run_dir]:
            d.mkdir(parents=True, exist_ok=True)
            
        self.auth = Authentication()
        self.session = Session()
            
    def load_config(self):
        """Load the user's local server-side config."""
        if not self.config_file.exists():
            return {}
        try:
             with open(self.config_file, 'r') as f:
                 return json.load(f)
        except Exception as e:
             console.print(f"[yellow]Warning: Failed to load user config: {e}[/yellow]")
             return {}

    def save_user_config(self, config):
        """Save the user's local server-side config."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            console.print(f"[red]Error saving config: {e}[/red]")

    def add_project_to_config(self, project_name, metadata):
        """Add or update a project in user config."""
        config = self.load_config()
        projects = config.get("projects", {})
        projects[project_name] = metadata
        config["projects"] = projects
        self.save_user_config(config)

    def remove_project_from_config(self, project_name):
        """Remove a project from user config."""
        config = self.load_config()
        projects = config.get("projects", {})
        if project_name in projects:
            del projects[project_name]
            config["projects"] = projects
            self.save_user_config(config)

    def get_user_projects_from_config(self):
        """Get all projects from user config."""
        config = self.load_config()
        return config.get("projects", {})

    def has_project_access(self, project_name):
        """Check if project exists in user config."""
        # Simple ownership check: if it's in my config, I own it.
        config = self.load_config()
        return project_name in config.get("projects", {})

    def create_session(self, username):
        """Create a new session ID and file for the user."""
        # Retrieve projects from user config
        projects = list(self.get_user_projects_from_config().keys())
        session_data = self.session.create_session(username, self.auth, projects=projects)
        
        # Start monitoring
        self.session.monitor_session(session_data["session_id"])
        
        return session_data

    def get_session(self, session_id):
        """Retrieve session data."""
        return self.session.get_session(session_id)

    def verify_session(self, session_id):
        """Verify if a session ID is valid."""
        if not session_id:
            return False, "Session ID missing."
        
        if not self.session.check_session_id(session_id):
            return False, "Session ID does not match server config."
            
        session_data = self.session.get_session(session_id)
        if not session_data:
            return False, "Session expired or invalid."
            
        return True, "Valid Session"

    def log_command(self, session_id, command, output):
        """Log a command and its output to the session file."""
        return self.session.log_command(session_id, command, output)

    def logout_session(self, session_id):
        """Destroy a session."""
        # Unmount all projects
        self.unmount_all(session_id)
        return self.session.logout_session(session_id)

    def unmount_all(self, session_id):
        """Unmount all active projects in the session."""
        session_data = self.session.get_session(session_id)
        if not session_data:
            return
            
        active_projects = session_data.get("active_projects", [])
        for project_name in list(active_projects):
            self.project_unmount(project_name, session_id)

    def project_init(self, project_name, password, session_id, project_dir):
        """Initialize encrypted project vault and manage session/access."""
        session_data = self.session.get_session(session_id)
        if not session_id or not session_data or not self.session.check_session_id(session_id):
            console.print("[bold red]Session Error:[/bold red] Invalid or expired session.")
            return False, {"status": "error", "message": "Invalid or expired session"}
            
        username = session_data.get("username")

        from enc_server.gocryptfs_handler import GocryptfsHandler
        handler = GocryptfsHandler()
        
        # Check if project exists first
        # New handler returns tuple
        is_exist, msg = handler.init_project(project_name, password) # Wait, init_project calls mount
        # Wait, the checking logic:
        # if (handler.vault_root / project_name).exists()
        # I removed that from handler? No. I changed handler.init_project to check internally.
        
        # Actually in EncServer.project_init (line 137):
        # if (handler.vault_root / project_name).exists():
        #      return False, ...
        # My handler logic ALSO checks it. Double check?
        
        # Let's remove the pre-check here and let handler do it, OR correct the return handling.
        # But wait, EncServer:137 was:
        # if (handler.vault_root / project_name).exists(): ...
        
        # I didn't change that line in EncServer yet.
        # handler.init_project logic (line 26 of handler) check exists.
        
        # So I will just unpacking the call.
        
        success, msg = handler.init_project(project_name, password)

        if success:

            # Construct paths (matching GocryptfsHandler defaults)
            vault_path = f"/home/{username}/.enc/vault/master/{project_name}"
            # ...
            
            # ...
            return True, {"status": "success", "project": project_name, "mount_point": mount_point}
        else:
            return False, {"status": "error", "message": f"Failed to init project: {msg}"}

    def project_list(self, session_id):
        """Get the merged list of projects (Server + Local Session)."""
        session_data = self.session.get_session(session_id)
        if not session_id or not session_data or not self.session.check_session_id(session_id):
            return False, {"status": "error", "message": "Invalid or expired session"}
            
        # Get from USER CONFIG
        raw_projects = self.get_user_projects_from_config()
        
        # Filter out sensitive vault_path from the response
        filtered_projects = {}
        for name, meta in raw_projects.items():
            filtered_projects[name] = {
                "mount_path": meta.get("mount_path"),
                "exec": meta.get("exec")
            }
        
        return True, {"status": "success", "projects": filtered_projects}

    def remove_project(self, project_name, session_id=None):
        """Permanently remove a project and its vault."""
        import getpass
        import shutil
        user = getpass.getuser()
        
        # 1. Access Check (Local Config)
        if not self.has_project_access(project_name):
             return False, {"status": "error", "message": "Access Denied: You do not have access to this project."}

        # 2. Unmount First (Safety)
        # Attempt unmount, but ignore errors if not mounted
        self.project_unmount(project_name, session_id)
        
        from enc_server.gocryptfs_handler import GocryptfsHandler
        handler = GocryptfsHandler()
        
        # 3. Path Calculation (Should match init logic)
        vault_path = handler.vault_root / project_name
        
        # 4. Secure Deletion
        try:
            if vault_path.exists():
                shutil.rmtree(vault_path)
            else:
                # If vault doesn't exist, we still proceed to clean up metadata
                # but might want to warn
                pass 
        except Exception as e:
            return False, {"status": "error", "message": f"Failed to delete vault: {e}"}

        # 5. Metadata Cleanup (User Config)
        self.remove_project_from_config(project_name)
        
        # 6. Session Cleanup
        if session_id:
            self.session.update_project_info(session_id, project_name, mount_state=False) 
            # Force remove from active projects if present (handled by unmount, but ensuring)
            
            self.session.log_command(session_id, f"server-project-remove {project_name}", {"status": "success"})

        return True, {"status": "success", "message": f"Project '{project_name}' removed."}

    def project_mount(self, project_name, password, session_id=None):
        """Mount an encrypted project."""
        import getpass
        user = getpass.getuser()
        
        # Access Check (Local Config)
        if not self.has_project_access(project_name):
            return False, {"status": "error", "message": "Access Denied: You do not have access to this project."}

        from enc_server.gocryptfs_handler import GocryptfsHandler
        handler = GocryptfsHandler()
        success, msg = handler.mount_project(project_name, password)
        
        res = {}
        if success:
            res = {"status": "success", "mount_point": f"/home/{user}/.enc/run/master/{project_name}"}
            if session_id:
                self.session.update_project_info(session_id, project_name, mount_state=True)
                # Start monitoring mount
                self.session.monitor_mount(session_id, project_name)
        else:
            res = {"status": "error", "message": f"Failed to mount project: {msg}"}
            
        if session_id:
            self.session.log_command(session_id, f"server-project-mount {project_name}", res)
            
        return success, res

    def project_unmount(self, project_name, session_id=None):
        """Unmount an encrypted project."""
        import getpass
        user = getpass.getuser()
        
        # Access Check (Local Config)
        if not self.has_project_access(project_name):
            return False, {"status": "error", "message": "Access Denied: You do not have access to this project."}

        from enc_server.gocryptfs_handler import GocryptfsHandler
        handler = GocryptfsHandler()
        handler.unmount_project(project_name)
        res = {"status": "success"}
        
        if session_id:
            self.session.update_project_info(session_id, project_name, mount_state=False)
            self.session.log_command(session_id, f"server-project-unmount {project_name}", res)
            
        return True, res

    def project_run(self, project_name, cmd_str, session_id=None):
        """Run a command in the project's run directory."""
        import getpass
        user = getpass.getuser()
        
        # Access Check (Local Config)
        if not self.has_project_access(project_name):
            return False, json.dumps({"status": "error", "message": "Access Denied"})

        work_dir = os.path.expanduser(f"~/.enc/run/master/{project_name}")
        try:
            # Run and capture for logging
            proc = subprocess.run(cmd_str, shell=True, cwd=work_dir, capture_output=True, text=True)
            output = f"RET: {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            if session_id:
                self.session.log_command(session_id, f"server-project-run {project_name}", output)
            return True, output
        except Exception as e:
            if session_id:
                self.session.log_command(session_id, f"server-project-run {project_name}", str(e))
            return False, str(e)

    def get_user_projects(self, username):
        """Return list of projects for a user."""
        # For listing ALL projects (admin view?), this requires access to other user's config.
        # This function was used by `server-user-list` maybe? 
        # Wait, get_all_users calls this via auth permissions? No.
        
        # Current implementation of `get_all_users` in this file doesn't call this.
        # It calls `self.auth.get_all_users()`.
        
        # But `cli.py` might call `get_user_projects`.
        # Since we moved storage to user config, we can only easily get CURRENT user projects.
        # Reading another user's config requires sudo or they aren't accessible.
        
        # For now, let's just return empty list or Implement reading /home/{username}/.enc/config.json with sudo if needed.
        # But this method is usually called for the CURRENT user in `project_list` context.
        # In `EncServer`, `project_list` calls `self.auth.get_user_project_metadata` which we removed.
        # So we don't need this unless external callers use it.
        # Let's keep it but point to config if username matches current user.
        
        import getpass
        if username == getpass.getuser():
             return list(self.get_user_projects_from_config().keys())
        
        return [] # TODO: Admin access to other users' projects

    def get_all_users(self, session_id=None):
        """Return all users for listing."""
        users = self.auth.get_all_users()
        users_data = []
        for u, record in users.items():
            role = "user"
            perms = []
            if isinstance(record, dict):
                role = record.get("role", "user")
                perms = record.get("permissions", [])
            elif isinstance(record, list):
                role = "legacy"
                perms = record
            users_data.append({"username": u, "role": role, "permissions": perms})
            
        res = {"status": "success", "users": users_data}
        if session_id:
            self.session.log_command(session_id, "user list", res)
            
        return res

    def create_user(self, username, password, role="user", ssh_key=None):
        """Create a system user and update policy."""

        # if the role is not in the list of roles, return False
        if role not in self.auth.PERMISSIONS:
            console.print(f"[red]Invalid role: {role}[/red]")
            return False
        
        # 1. System User (requires sudo)
        import subprocess
        try:
            # -D = don't set password yet, -s /bin/bash = shell
            # Check existence
            try:
                subprocess.run(["id", username], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                console.print(f"[yellow]User {username} already exists.[/yellow]")
                return False
            except subprocess.CalledProcessError:
                subprocess.run(["sudo", "adduser", "-D", "-s", "/usr/local/bin/enc-shell", "-G", "enc", username], check=True)
                # Set password
                subprocess.run(f"echo '{username}:{password}' | sudo chpasswd", shell=True, check=True)
                console.print(f"[green]System user {username} created.[/green]")
                
                # Setup SSH Key if provided
                if ssh_key:
                    try:
                        ssh_dir = f"/home/{username}/.ssh"
                        auth_keys = f"{ssh_dir}/authorized_keys"
                        
                        subprocess.run(["sudo", "mkdir", "-p", ssh_dir], check=True)
                        subprocess.run(["sudo", "chmod", "700", ssh_dir], check=True)
                        
                        # Echo key securely to temp file then move to avoid shell injection issues generally, 
                        # but simple echo into file owned by root then chown is okay.
                        # Using sh -c to handle redirection with sudo
                        cmd = f"echo '{ssh_key}' | sudo tee {auth_keys} > /dev/null"
                        subprocess.run(cmd, shell=True, check=True)
                        
                        subprocess.run(["sudo", "chmod", "600", auth_keys], check=True)
                        # Fix ownership (use username: to default to user's primary group)
                        subprocess.run(["sudo", "chown", "-R", f"{username}:", ssh_dir], check=True)
                        console.print(f"[green]SSH key configured for {username}.[/green]")
                    except Exception as e:
                        console.print(f"[red]Failed to configure SSH key: {e}[/red]")

                
        except Exception as e:
            console.print(f"[red]Failed to create system user: {e}[/red]")
            return False

        # 2. Policy Update
        self._update_policy(username, role)
        return True

    def add_ssh_key(self, username, ssh_key_content):
        """Append a public key to the user's authorized_keys file."""
        import subprocess
        import getpass
        
        try:
            current_user = getpass.getuser()
            ssh_dir = f"/home/{username}/.ssh"
            auth_keys = f"{ssh_dir}/authorized_keys"
            
            if username == current_user:
                # Self-service: Use native python operations (no sudo)
                os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
                
                # Check for duplicate
                if os.path.exists(auth_keys):
                    try:
                        with open(auth_keys, 'r') as f:
                            existing = f.read()
                            if ssh_key_content in existing:
                                return True, {"status": "success", "message": "Key already exists"}
                    except Exception:
                        pass # Ignore read errors, try appending
                
                # Append key
                with open(auth_keys, 'a') as f:
                    f.write(f"\n{ssh_key_content}\n")
                    
                os.chmod(auth_keys, 0o600)
                return True, {"status": "success", "message": "SSH key added successfully"}
                
            else:
                # Admin/Other: Use sudo
                # Ensure .ssh dir exists
                subprocess.run(["sudo", "mkdir", "-p", ssh_dir], check=True)
                subprocess.run(["sudo", "chmod", "700", ssh_dir], check=True)
                
                # Append key securely
                check_cmd = f"sudo grep -F '{ssh_key_content}' {auth_keys}"
                try:
                    subprocess.run(check_cmd, shell=True, check=True, stdout=subprocess.DEVNULL)
                    return True, {"status": "success", "message": "Key already exists"}
                except subprocess.CalledProcessError:
                    cmd = f"echo '{ssh_key_content}' | sudo tee -a {auth_keys} > /dev/null"
                    subprocess.run(cmd, shell=True, check=True)
                    
                    subprocess.run(["sudo", "chmod", "600", auth_keys], check=True)
                    subprocess.run(["sudo", "chown", "-R", f"{username}:", ssh_dir], check=True)
                    
                    return True, {"status": "success", "message": "SSH key added successfully"}
                
        except Exception as e:
            return False, {"status": "error", "message": f"Failed to add SSH key: {e}"}

    def delete_project(self, project_name, session_id):
        """Remove a project from the system (files and policy)."""
        import shutil
        
        # 1. Identify User from Session
        username = self.get_username_from_session(session_id)
        if not username:
             return {"status": "error", "message": "Invalid Session"}

        # 2. Check Access/Ownership
        # Explicit admin check OR ownership check.
        # Currently policy stores projects under users.
        # If user is admin, they can delete any project IF we passed target user.
        # BUT for now, let's assume user deletes THEIR project.
        # Admin deletion of other's projects requires different args (target_user).
        
        # For this iteration: User deletes their OWN project.
        if not self.auth.has_project_access(username, project_name):
             return {"status": "error", "message": "Access Denied"}

        # 3. Unmount if mounted
        try:
             # Check if mounted by trying to unmount or check mount result
             from enc_server.gocryptfs_handler import GocryptfsHandler
             handler = GocryptfsHandler()
             # We blindly attempt unmount; if not mounted it fails gracefully or we ignore
             handler.unmount_project(project_name)
        except Exception:
             pass 

        # 4. Remove Files
        try:
            vault_path = os.path.expanduser(f"~/.enc/vault/master/{project_name}")
            run_path = os.path.expanduser(f"~/.enc/run/master/{project_name}")
            
            if os.path.exists(vault_path):
                shutil.rmtree(vault_path)
            
            if os.path.exists(run_path):
                shutil.rmtree(run_path)
                
        except Exception as e:
            return {"status": "error", "message": f"File deletion failed: {e}"}

        # 5. Update Policy
        self.auth.remove_user_project(username, project_name)

        return {"status": "success", "message": f"Project {project_name} deleted."}

    def delete_user(self, username):
        """Remove a system user and update policy."""
        import subprocess
        try:
            # Check existence
            try:
                subprocess.run(["id", username], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except:
                console.print(f"[yellow]User {username} does not exist.[/yellow]")
                return False
                
            subprocess.run(["sudo", "deluser", "--remove-home", username], check=True)
            console.print(f"[green]System user {username} deleted.[/green]")
        except Exception as e:
            console.print(f"[red]Failed to delete system user: {e}[/red]")
            return False
            
        # Remove from policy
        self._update_policy(username, action="remove")
        return True

    def _update_policy(self, username, role="user", action="add"):
        policy_file = Path("/etc/enc/policy.json")
        try:
            if policy_file.exists():
                with open(policy_file, 'r') as f:
                    policy = json.load(f)
            else:
                 raise FileNotFoundError(f"Critical Error: Security policy file missing at {policy_file}")
            
            if action == "add":
                policy.setdefault("users", {})[username] = {
                    "role": role,
                    "permissions": self.auth.PERMISSIONS.get(role, [])
                }
            elif action == "remove":
                if username in policy.get("users", {}):
                    del policy["users"][username]
            
            # Write back requires sudo potentially if owned by root
            # But container typically runs as root? 
            # Dockerfile: USER isn't switched to admin globally, entrypoint execs sshd.
            # But the 'enc' server command runs as the logged in user (admin/tester).
            # So we usually need sudo to write to /etc.
            
            # Dump to valid temp file then sudo cp?
            tmp_path = Path("/tmp/policy.json.tmp")
            with open(tmp_path, 'w') as f:
                json.dump(policy, f, indent=4)
                
            subprocess.run(["sudo", "cp", str(tmp_path), str(policy_file)], check=True)
            subprocess.run(["sudo", "chmod", "644", str(policy_file)], check=True)
            
        except Exception as e:
            console.print(f"[red]Policy update failed: {e}[/red]")
