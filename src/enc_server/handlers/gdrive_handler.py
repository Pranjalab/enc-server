import subprocess
import os
import sys
from .base_handler import BaseHandler

class GDriveHandler(BaseHandler):
    def verify(self) -> bool:
        env = self._setup_rclone_config()
        try:
            # Check if we can list the remote
            subprocess.run(["rclone", "lsd", "enc_gdrive:"], env=env, check=True, capture_output=True)
            return True
        except Exception:
            return False

    def _setup_rclone_config(self):
        env = os.environ.copy()
        env["RCLONE_CONFIG_ENC_GDRIVE_TYPE"] = "drive"
        
        creds = self.config.get("credentials")
        if creds:
             env["RCLONE_CONFIG_ENC_GDRIVE_SERVICE_ACCOUNT_FILE"] = creds
             
        folder_id = self.config.get("FOLDER_ID")
        if folder_id:
            env["RCLONE_CONFIG_ENC_GDRIVE_ROOT_FOLDER_ID"] = folder_id

        return env

    def push(self, source_file: str) -> bool:
        env = self._setup_rclone_config()
        dest = "enc_gdrive:"
        
        from enc_server.debug import debug_log # Absolute import
        debug_log(f"GDriveHandler: Pushing {source_file} to GDrive...")
        try:
            cmd = ["rclone", "copyto", source_file, dest + "user_backup.enc"]
            res = subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
            debug_log("GDriveHandler: Upload Successful.")
            return True
        except subprocess.CalledProcessError as e:
            msg = f"{e.stdout} {e.stderr}"
            debug_log(f"GDriveHandler: Upload Failed: {msg}")
            raise Exception(msg)

    def pull(self, dest_file: str) -> bool:
        env = self._setup_rclone_config()
        source = "enc_gdrive:user_backup.enc"
        
        print("Pulling backup from Google Drive...", file=sys.stderr)
        try:
            cmd = ["rclone", "copyto", source, dest_file]
            subprocess.run(cmd, env=env, check=True)
            if os.path.exists(dest_file):
                print("GDrive Download Successful.", file=sys.stderr)
                return True
            else:
                print("GDrive Download finished but file missing.", file=sys.stderr)
                return False
        except subprocess.CalledProcessError as e:
            print(f"GDrive Download Failed: {e}", file=sys.stderr)
            return False
