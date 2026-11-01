#!/usr/bin/python3
"""Password storage helpers for Cloud Firefox Lite."""

import getpass
import hashlib
import hmac
import json
import os
import secrets
import sys
import tempfile

PASSWORD_FILE = os.environ.get("CFL_PASSWORD_FILE", "/etc/cloud-firefox-lite/admin.json")
SCRYPT_N = 1 << 15
SCRYPT_R = 8
SCRYPT_P = 1


def _derive(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N,
                          r=SCRYPT_R, p=SCRYPT_P, dklen=32)


def set_password(password, path=PASSWORD_FILE):
    salt = secrets.token_bytes(16)
    payload = {
        "algorithm": "scrypt",
        "n": SCRYPT_N,
        "r": SCRYPT_R,
        "p": SCRYPT_P,
        "salt": salt.hex(),
        "hash": _derive(password, salt).hex(),
    }
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o750, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".admin-", dir=directory)
    try:
        os.fchmod(fd, 0o640)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(payload, output)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_password(password, path=PASSWORD_FILE):
    try:
        with open(path, encoding="utf-8") as source:
            record = json.load(source)
        if record.get("algorithm") != "scrypt":
            return False
        salt = bytes.fromhex(record["salt"])
        expected = bytes.fromhex(record["hash"])
        actual = _derive(password, salt)
        return hmac.compare_digest(actual, expected)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False


def prompt_password():
    while True:
        password = getpass.getpass("Mat khau admin (toi thieu 12 ky tu): ")
        confirmation = getpass.getpass("Nhap lai mat khau: ")
        if password != confirmation:
            print("Hai mat khau khong khop. Vui long thu lai.", file=sys.stderr)
            continue
        if len(password) < 12:
            print("Mat khau can it nhat 12 ky tu.", file=sys.stderr)
            continue
        set_password(password)
        print("Da luu hash mat khau admin.")
        return


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "set-password":
        prompt_password()
    else:
        raise SystemExit("Usage: auth.py set-password")