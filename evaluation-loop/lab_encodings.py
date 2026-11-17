"""The reversible encodings promptfoo's static strategies apply to a test's prompt (base64, hex, rot13).

The planted payload carries the literal {nonce}; a strategy that encodes the prompt at generate time
encodes the placeholder with it. To plant a fresh value per trial the provider decodes, fills and
encodes again; gate C uses decode() to check the payload survived.
"""
from __future__ import annotations

import base64
import binascii
import codecs

REVERSIBLE = ("base64", "hex", "rot13")


def encode(strategy: str, text: str) -> str:
    if strategy == "base64":
        return base64.b64encode(text.encode()).decode()
    if strategy == "hex":
        return text.encode().hex()
    if strategy == "rot13":
        return codecs.encode(text, "rot13")
    raise ValueError(f"not a reversible encoding: {strategy}")


def decode(strategy: str, text: str) -> str | None:
    """The plain text, or None if `text` is not that encoding of anything."""
    t = (text or "").strip()
    try:
        if strategy == "base64":
            return base64.b64decode(t, validate=True).decode()
        if strategy == "hex":
            return bytes.fromhex(t.replace(" ", "")).decode()
        if strategy == "rot13":
            return codecs.decode(text, "rot13")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    raise ValueError(f"not a reversible encoding: {strategy}")


def fill_encoded(strategy: str | None, text: str, nonce: str) -> str:
    """`text` with {nonce} replaced by `nonce`, under the strategy's encoding if it has one."""
    if strategy in REVERSIBLE:
        plain = decode(strategy, text)
        if plain is not None and "{nonce}" in plain:
            return encode(strategy, plain.replace("{nonce}", nonce))
    return text.replace("{nonce}", nonce)


def plain_text(strategy: str | None, text: str) -> str:
    """What the message says, for the checks: decoded when the strategy is a reversible encoding."""
    if strategy in REVERSIBLE:
        plain = decode(strategy, text)
        if plain is not None:
            return plain
    return text
