"""Tests for AES encryption helpers."""

from __future__ import annotations

import pytest
from cryptography.fernet import InvalidToken

from backend.common.encryption import decrypt_api_key, encrypt_api_key


class TestEncryption:
    """Test encrypt/decrypt roundtrip for API keys."""

    def test_roundtrip_simple_string(self):
        """Encrypt then decrypt produces the original string."""
        original = "my-secret-api-key-12345"
        encrypted = encrypt_api_key(original)
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == original

    def test_roundtrip_pem_key(self):
        """Encrypt and decrypt a multi-line PEM private key."""
        pem = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIBogIBAAJBALRiMLAHudeSA/x3hB2f+2NRkJLA\n"
            "jR+3F2p3Y3F2Q5K4R5u2U7Z5m1X8W3V4n6B9k0L1\n"
            "-----END RSA PRIVATE KEY-----"
        )
        encrypted = encrypt_api_key(pem)
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == pem

    def test_different_inputs_produce_different_ciphertexts(self):
        """Two different strings produce different encrypted outputs."""
        encrypted1 = encrypt_api_key("key-one")
        encrypted2 = encrypt_api_key("key-two")
        assert encrypted1 != encrypted2

    def test_same_input_produces_different_ciphertexts(self):
        """Fernet includes a timestamp, so same input gives different output each time."""
        encrypted1 = encrypt_api_key("same-key")
        encrypted2 = encrypt_api_key("same-key")
        assert encrypted1 != encrypted2  # Different due to timestamp/IV

    def test_encrypted_is_not_plaintext(self):
        """The encrypted string should not contain the original value."""
        original = "my-secret-key"
        encrypted = encrypt_api_key(original)
        assert original not in encrypted

    def test_empty_string_roundtrip(self):
        """Empty string can be encrypted and decrypted."""
        encrypted = encrypt_api_key("")
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == ""

    def test_decrypt_garbage_raises_error(self):
        """Decrypting invalid data raises InvalidToken."""
        with pytest.raises(InvalidToken):
            decrypt_api_key("not-a-valid-fernet-token")

    def test_decrypt_modified_ciphertext_raises_error(self):
        """Tampered ciphertext raises InvalidToken (HMAC verification fails)."""
        encrypted = encrypt_api_key("original-key")
        tampered = encrypted[:-5] + "XXXXX"
        with pytest.raises(Exception):  # InvalidToken or binascii.Error
            decrypt_api_key(tampered)
