"""
pw_crypto.py — WASM encrypt/decrypt via Node subprocess.
"""

import json
import subprocess
from pathlib import Path
from typing import Any

_BASE_DIR = Path(__file__).parent.resolve()
_CRYPTO_JS = _BASE_DIR / "crypto.js"
_WASM = _BASE_DIR / "pw_raze.wasm"


class PWCryptoError(Exception):
    pass


def _check():
    if not _CRYPTO_JS.exists():
        raise PWCryptoError(f"crypto.js not found: {_CRYPTO_JS}")
    if not _WASM.exists():
        raise PWCryptoError(f"pw_raze.wasm not found: {_WASM}")


def _call(op: str, jti: str, uid: str, data) -> dict:
    _check()
    payload = json.dumps({"op": op, "jti": jti, "uid": uid, "data": data})
    try:
        proc = subprocess.run(
            ["node", str(_CRYPTO_JS)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(_BASE_DIR),
        )
    except FileNotFoundError:
        raise PWCryptoError("node not found on system")
    except subprocess.TimeoutExpired:
        raise PWCryptoError("crypto timeout (30s)")

    if proc.returncode != 0:
        raise PWCryptoError(f"crypto.js exit {proc.returncode}: {proc.stderr[:300]}")

    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise PWCryptoError(f"invalid output: {proc.stdout[:200]}")

    if not out.get("ok"):
        raise PWCryptoError(f"crypto error: {out.get('error')}")

    return out["result"]


def encrypt(jti: str, uid: str, data) -> dict:
    result = _call("encrypt", jti, uid, data)
    for k in ("iv", "ciphertext", "tag"):
        if k not in result:
            raise PWCryptoError(f"missing {k}")
    return result


def decrypt(jti: str, uid: str, data: Any):
    if isinstance(data, str):
        data = json.loads(data)
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
        inner = data["data"]
        if "iv" in inner and "ciphertext" in inner:
            data = inner
    for k in ("iv", "ciphertext", "tag"):
        if k not in data:
            raise PWCryptoError(f"missing {k}")
    return _call("decrypt", jti, uid, data)


def decode_jwt(token: str) -> dict:
    import base64
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    parts = token.split(".")
    if len(parts) != 3:
        raise PWCryptoError("invalid JWT")
    p = parts[1].replace("-", "+").replace("_", "/")
    p += "=" * (-len(p) % 4)
    return json.loads(base64.b64decode(p))
