"""
Symmetric encryption for OAuth tokens stored in the database.

Tokens are never stored in plaintext (User.oauth_token_encrypted /
oauth_refresh_token_encrypted). ENCRYPTION_KEY must be a Fernet key —
generate one with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

and put it in .env. It is NOT the same as SECRET_KEY (Flask's session
signing key) — rotating one must not silently invalidate the other.
"""

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


def _get_fernet() -> Fernet:
    key = current_app.config.get("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. Generate one (see app/utils/crypto.py "
            "docstring) and add it to .env."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(plaintext: str) -> str:
    if plaintext is None:
        return None
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    if ciphertext is None:
        return None
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Stored token could not be decrypted (bad key or corrupted data).") from exc
