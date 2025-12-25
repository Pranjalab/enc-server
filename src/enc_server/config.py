from pathlib import Path
import os
import json
from typing import Dict, Any

# Base directory for ENC metadata in the user's home
ENC_DIR = Path.home() / ".enc"
ENC_CONFIG_FILE = ENC_DIR / "config.json"
ENC_KEYS_FILE = ENC_DIR / "keys.enc"

# Per-project directory name
PROJECT_ENC_DIR = ".enc"

def get_enc_dir() -> Path:
    """Ensure ENC directory exists and return it."""
    ENC_DIR.mkdir(parents=True, exist_ok=True)
    return ENC_DIR

def load_config() -> Dict[str, Any]:
    """Load configuration from config.json."""
    if not ENC_CONFIG_FILE.exists():
        return {}
    try:
        with open(ENC_CONFIG_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_config(config: Dict[str, Any]):
    """Save configuration to config.json."""
    get_enc_dir()
    with open(ENC_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def get_server_url() -> str:
    """Get the configured server URL."""
    config = load_config()
    return config.get("server_url", "http://localhost:8000")

