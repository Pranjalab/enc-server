import shutil
import os
import sys
from .base_handler import BaseHandler

class LocalHandler(BaseHandler):
    def verify(self) -> bool:
        dest_path = self.config.get("path")
        if not dest_path:
            return False
        
        dest_path = os.path.expanduser(dest_path)
        try:
            if not os.path.exists(dest_path):
                os.makedirs(dest_path, exist_ok=True)
            # Check writability
            test_file = os.path.join(dest_path, ".write_test")
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            return True
        except Exception:
            return False

    def push(self, source_file: str) -> bool:
        dest_path = self.config.get("path")
        if not dest_path:
            print("Error: Local backup path not configured.", file=sys.stderr)
            return False
        
        dest_path = os.path.expanduser(dest_path)
        
        try:
            os.makedirs(dest_path, exist_ok=True)
            shutil.copy2(source_file, dest_path)
            print(f"Backup saved locally to {dest_path}", file=sys.stderr)
            return True
        except Exception as e:
            print(f"Local Backup Failed: {e}", file=sys.stderr)
            return False

    def pull(self, dest_file: str) -> bool:
        source_path = self.config.get("path")
        if not source_path:
            return False
            
        source_path = os.path.expanduser(source_path)
        backup_file = os.path.join(source_path, "user_backup.enc")
        
        if not os.path.exists(backup_file):
            print(f"No backup file found at {backup_file}", file=sys.stderr)
            return False
            
        try:
            shutil.copy2(backup_file, dest_file)
            return True
        except Exception as e:
             print(f"Local Restore Failed: {e}", file=sys.stderr)
             return False
