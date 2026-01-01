import sys
from enc_server.user_manager import UserManager

def main():
    try:
        manager = UserManager("/app/config/users.yaml")
        manager.init_users()
    except Exception as e:
        print(f"FATAL: User initialization failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
