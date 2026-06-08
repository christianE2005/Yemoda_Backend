"""Field-level encryption for sensitive tokens stored at rest (e.g. GitHub OAuth tokens).

Uses Fernet (AES-128-CBC + HMAC, authenticated). The key is derived (SHA-256 → urlsafe-base64) from
TOKEN_ENCRYPTION_KEY when set, else from DJANGO_SECRET_KEY so existing deployments keep working.

IMPORTANT: set a STABLE TOKEN_ENCRYPTION_KEY in production. If the derived key ever changes
(e.g. DJANGO_SECRET_KEY is unset and a random per-process key is used), previously-encrypted
values can no longer be decrypted — the field then returns the stored ciphertext as-is, and the
affected users simply need to reconnect GitHub. Never lose data, but tokens become unusable.
"""
import base64
import functools
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


@functools.lru_cache(maxsize=1)
def _fernet() -> Fernet:
    material = (settings.TOKEN_ENCRYPTION_KEY or settings.SECRET_KEY or "").encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
    return Fernet(key)


class EncryptedField(models.TextField):
    """TextField that transparently encrypts its value at rest with Fernet.

    Writes encrypt; reads decrypt. A value that fails to decrypt — legacy plaintext written before
    this field existed, or data under a different key — is returned unchanged so the app keeps
    working and the row is re-encrypted on its next save. TextField (not CharField) because Fernet
    ciphertext is longer than the original token.
    """

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        try:
            return _fernet().decrypt(value.encode()).decode()
        except (InvalidToken, ValueError, TypeError):
            return value  # legacy plaintext / undecryptable — return unchanged

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        return _fernet().encrypt(str(value).encode()).decode()
