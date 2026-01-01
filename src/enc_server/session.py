import uuid
import datetime
import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, Any
import sys
from .debug import debug_log

class Session:
    def __init__(self, persistent_root=None, transient_root=None):
        # Default persistent root
        self.persistent_root = Path(persistent_root) if persistent_root else Path.home() / ".enc" / "system"
        
        # Determine transient root dynamically
        vault_root = Path.home() / ".enc"
        if (vault_root / "system").exists():
             self.transient_root = vault_root
             debug_log(f"Session: Vault detected. Using {self.transient_root} as session storage.")
        else:
             self.transient_root = Path(transient_root) if transient_root else Path("/tmp/enc_sessions")
             debug_log(f"Session: Vault NOT detected. Using {self.transient_root} as session storage.")
            
        self.config_file = self.persistent_root / "config.json"
        self.session_dir = self.transient_root / "sessions"
        
        self.session_check_time = int(os.environ.get("ENC_SESSION_TIMEOUT", 600))  # seconds
        self.mount_check_time = 3    # seconds
        self.monitoring_active = False
        self.mount_monitoring_active = False

    def init_session_storage(self, root_path=None):
        """Initialize session directory. root_path can be inside the mounted vault."""
        if root_path:
            self.transient_root = Path(root_path)
            self.session_dir = self.transient_root / "sessions"
        
        debug_log(f"Session: Initializing session storage at {self.session_dir}")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        return self.session_dir

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from config.json."""
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
        except Exception:
            return {}

    def save_config(self, config: Dict[str, Any]):
        """Save configuration to config.json."""
        self.persistent_root.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w") as f:
            json.dump(config, f, indent=2)

    def create_session(self, username, auth_instance, projects=None):
        """Create a new session ID and file for the user."""
        session_id = str(uuid.uuid4())
        timestamp = datetime.datetime.now().isoformat()
        
        if projects is None:
            projects = []
        
        session_data = {
            "session_id": session_id,
            "username": username,
            "created_at": timestamp,
            "updated_at": timestamp,
            "context": "enc",
            "active_project": None,
            "allowed_commands": auth_instance.get_user_permissions(username),
            "projects": projects,
            "logs": {}
        }

        # adding started session log
        msg_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_key = f"[{msg_timestamp}] login"
        session_data["logs"][log_key] = "Session started"
        
        session_file = self.session_dir / f"{session_id}.json"
        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=4)
        
        # Store session ID into config file
        config = self.load_config()
        config["session_id"] = session_id
        self.save_config(config)
            
        return session_data

    def get_session(self, session_id):
        """Retrieve session data."""
        session_file = self.session_dir / f"{session_id}.json"
        if not session_file.exists():
            return None
        
        with open(session_file, 'r') as f:
            data = json.load(f)
            
        # Passive Check: Expiry
        updated_at_str = data.get("updated_at")
        if updated_at_str:
            updated_at = datetime.datetime.fromisoformat(updated_at_str)
            now = datetime.datetime.now()
            diff = (now - updated_at).total_seconds()
            
            if diff > self.session_check_time:
                # Expired
                print(f"DEBUG: Session expired. Diff: {diff}, Timeout: {self.session_check_time}", file=sys.stderr, flush=True)
                self.logout_session(session_id)
                return None
            else:
                pass
                
        return data

    def save_session(self, session_data):
        """Save session data to file."""
        session_id = session_data.get("session_id")
        session_file = self.session_dir / f"{session_id}.json"
        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=4)
        return True

    def update_time(self, session_id):
        """Update the session's updated_at timestamp."""
        session_data = self.get_session(session_id)
        if not session_data:
            return False
        
        session_data["updated_at"] = datetime.datetime.now().isoformat()
        return self.save_session(session_data)

    def update_project_info(self, session_id, project_name, mount_state=True):
        """Update project activity status in the session file."""
        session_data = self.get_session(session_id)
        if not session_data:
            return False
            
        if "active_projects" not in session_data:
            session_data["active_projects"] = []
            
        if mount_state:
            if project_name not in session_data["active_projects"]:
                session_data["active_projects"].append(project_name)
        else:
            if project_name in session_data["active_projects"]:
                session_data["active_projects"].remove(project_name)
                
        return self.save_session(session_data)

    def log_command(self, session_id, command, output):
        """Log a command and its output to the session file."""
        session_data = self.get_session(session_id)
        if not session_data:
            return False
            
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_key = f"[{timestamp}] {command}"
        session_data["logs"][log_key] = output
        return self.save_session(session_data)

    def logout_session(self, session_id):
        """Destroy a session."""
        # Stop monitoring if active
        self.stop_session_monitoring()
        self.stop_mount_monitoring()

        # remove session id from config file
        config = self.load_config()
        if config.get("session_id") == session_id:
            config["session_id"] = None
            self.save_config(config)
        session_file = self.session_dir / f"{session_id}.json"
        if session_file.exists():
            os.remove(session_file)
            return True
        return False

    def start_session_monitoring(self):
        """Start monitoring the session."""
        pass 

    def stop_session_monitoring(self):
        """Stop monitoring the session."""
        self.monitoring_active = False

    def check_session_id(self, session_id):
        """Check if the session ID matches the one in global config."""
        config = self.load_config()
        return config.get("session_id") == session_id

    def log_result(self, ctx, result_data):
        """Helper to log from Click context."""
        session_id = ctx.obj.get("session_id")
        if session_id:
            cmd_path = ctx.command_path
            self.log_command(session_id, cmd_path, result_data)

    # --- Monitoring Methods ---

    def monitor_session(self, session_id, logout_callback=None):
        """Run loop checking session inactivity."""
        self.monitoring_active = True
        
        def _monitor():
            while self.monitoring_active:
                time.sleep(1) # Check every second
                
                # Check if session file exists
                session_data = self.get_session(session_id)
                if not session_data:
                    # Session gone, stop monitoring
                    self.monitoring_active = False
                    return

                updated_at_str = session_data.get("updated_at")
                if not updated_at_str:
                    continue
                    
                updated_at = datetime.datetime.fromisoformat(updated_at_str)
                now = datetime.datetime.now()
                diff = (now - updated_at).total_seconds()
                
                if diff > self.session_check_time:
                    # Session expired
                    print(f"Session {session_id} expired (inactive {diff}s). Logging out.")
                    self.logout_session(session_id)
                    self.monitoring_active = False
                    self.mount_monitoring_active = False # Also stop mount monitoring
                    return

        t = threading.Thread(target=_monitor, daemon=True)
        t.start()

    def stop_mount_monitoring(self):
        self.mount_monitoring_active = False

    def monitor_mount(self, session_id, project_name, project_path=None):
        """Run loop checking for file activity in project vault."""
        self.mount_monitoring_active = True
        
        # If path not provided, use legacy default (not recommended for new deployments)
        if not project_path:
            project_path = self.persistent_root / "vault" / "master" / project_name
        
        # Ensure it's a Path object
        project_path = Path(project_path)
        
        def _monitor():
            while self.mount_monitoring_active:
                time.sleep(self.mount_check_time)
                
                if not self.monitoring_active: # If session monitoring stops, this should too
                   return

                if not project_path.exists():
                     continue

                # Check for activity
                if self._check_mount_activity(project_path):
                    self.update_time(session_id)

        t = threading.Thread(target=_monitor, daemon=True)
        t.start()

    def _check_mount_activity(self, path: Path) -> bool:
        """Check if any file in path has been modified recently."""
        # Check if modified within last check_time + buffer
        threshold = datetime.datetime.now().timestamp() - self.mount_check_time - 1
        
        try:
            for root, dirs, files in os.walk(path):
                for f in files:
                    full_path = Path(root) / f
                    if full_path.stat().st_mtime > threshold:
                        return True
        except Exception as e:
            print(f"Error checking mount activity: {e}")
        return False
