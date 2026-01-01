
import sys
import time
import traceback
from enc_server.backup_manager import BackupManager
from enc_server.debug import debug_log

def main():
    if len(sys.argv) < 4:
        debug_log("BackgroundSync: Missing arguments (username, handler, source)")
        sys.exit(1)

    username = sys.argv[1]
    handler_name = sys.argv[2]
    source_file = sys.argv[3]

    # Initialize BackupManager for the user (to load config/handlers)
    # We need to context switch or just instantiate? 
    # BackupManager takes 'username'.
    bm = BackupManager(username)
    
    debug_log(f"BackgroundSync: Starting detached sync for {username} -> {handler_name}")
    
    # We can reuse the worker logic if we access it, 
    # but _background_sync_worker is instance method.
    # Let's just call it. It might update status.json which is what we want.
    
    # We need to simulate the worker logic here or call the method.
    # Calling the method on the instance should work.
    
    try:
        bm._background_sync_worker(handler_name, source_file)
    except Exception as e:
         debug_log(f"BackgroundSync CRITICAL: {e}")
         traceback.print_exc()

if __name__ == "__main__":
    main()
