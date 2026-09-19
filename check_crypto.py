try:
    from cryptography.fernet import Fernet
    print("cryptography_available")
except Exception as exc:
    print(f"cryptography_unavailable: {exc}")
