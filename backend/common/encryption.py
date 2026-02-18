"""AES encryption helpers for storing API keys at rest.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
Keys are encrypted before being written to the database and
decrypted only in-memory when making Kalshi API calls.

Usage:
    from backend.common.encryption import encrypt_api_key, decrypt_api_key

    # During onboarding — encrypt and store
    encrypted = encrypt_api_key(raw_private_key)
    user.encrypted_private_key = encrypted

    # When making API call — decrypt in memory
    private_key = decrypt_api_key(user.encrypted_private_key)
"""

from __future__ import annotations

from cryptography.fernet import Fernet

from backend.common.config import get_settings


def _get_fernet() -> Fernet:
    """Create a Fernet instance from the app encryption key."""
    settings = get_settings()
    return Fernet(settings.encryption_key.encode())


def encrypt_api_key(plaintext: str) -> str:
    """Encrypt an API key or private key for database storage.

    Args:
        plaintext: The raw API key or PEM private key string.

    Returns:
        Base64-encoded encrypted string (safe for database VARCHAR storage).
    """
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    """Decrypt an API key or private key from database storage.

    Args:
        ciphertext: The encrypted string from the database.

    Returns:
        The original plaintext API key or PEM private key.

    Raises:
        cryptography.fernet.InvalidToken: If the ciphertext is invalid or
            was encrypted with a different key.
    """
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()
