import hashlib
import hmac
import secrets

N, R, P, KEY_LENGTH = 16384, 8, 1, 64


def derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=N, r=R, p=P,
                          dklen=KEY_LENGTH, maxmem=64 * 1024 * 1024)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = derive(password, salt)
    return f'scrypt${N}${R}${P}${salt.hex()}${digest.hex()}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = encoded.split('$')
        # Never execute arbitrary work factors from a malformed database value.
        if (algorithm, n, r, p) != ('scrypt', str(N), str(R), str(P)):
            return False
        salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
        if len(salt) != 16 or len(expected) != KEY_LENGTH:
            return False
        actual = derive(password, salt)
        return hmac.compare_digest(actual, expected)
    except (ValueError, UnicodeError):
        return False


# Unknown accounts still take a real password-hash verification path.
DUMMY_HASH = hash_password(secrets.token_urlsafe(32))
