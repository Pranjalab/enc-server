import uuid
import datetime
import json
import os
from pathlib import Path
from typing import Dict, Any

class Session:
    def __init__(self):
        self.enc_root = Path.home() / ".enc"
        self.config_file = self.enc_root / "config.json"
        self.session_dir = self.enc_root / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from config.json."""
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}

    def save_config(self, config: Dict[str, Any]):
        """Save configuration to config.json."""
        self.enc_root.mkdir(parents=True, exist_ok=True)
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
            return json.load(f)

    def save_session(self, session_data):
        """Save session data to file."""
        session_id = session_data.get("session_id")
        session_file = self.session_dir / f"{session_id}.json"
        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=4)
        return True

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
        self.session_monitoring = True

    def stop_session_monitoring(self):
        """Stop monitoring the session."""
        self.session_monitoring = False

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
