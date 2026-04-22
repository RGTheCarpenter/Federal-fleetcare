import hashlib
import hmac
import os
import secrets
from pathlib import Path


SECRET_FILE = Path(__file__).resolve().parent.parent / ".fleetcare-secret"


def load_secret_key():
    env_secret = os.environ.get("SECRET_KEY", "").strip()
    if env_secret:
        return env_secret.encode("utf-8")

    if SECRET_FILE.exists():
        return SECRET_FILE.read_text(encoding="utf-8").strip().encode("utf-8")

    secret = secrets.token_hex(32)
    SECRET_FILE.write_text(secret, encoding="utf-8")
    return secret.encode("utf-8")


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        200000,
    )
    return f"{salt}${digest.hex()}"


def verify_password(password, stored_value):
    try:
        salt, expected = stored_value.split("$", 1)
    except ValueError:
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        200000,
    )
    return hmac.compare_digest(digest.hex(), expected)


def sign_session(user_id, secret_key):
    payload = str(user_id).encode("utf-8")
    signature = hmac.new(secret_key, payload, hashlib.sha256).hexdigest()
    return f"{user_id}.{signature}"


def read_session(cookie_value, secret_key):
    if not cookie_value or "." not in cookie_value:
        return None

    user_id, signature = cookie_value.split(".", 1)
    expected = hmac.new(secret_key, user_id.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        return int(user_id)
    except ValueError:
        return None
