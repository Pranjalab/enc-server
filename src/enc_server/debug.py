import datetime
import os
import sys

def debug_log(msg):
    """Log debug message to /tmp/enc_debug.log."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}\n"
    # Write to file
    try:
        with open("/tmp/enc_debug.log", "a") as f:
            f.write(formatted_msg)
    except:
        pass
    # Also write to stderr for docker logs
    sys.stderr.write(formatted_msg)
    sys.stderr.flush()
