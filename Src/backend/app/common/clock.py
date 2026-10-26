from time import time_ns


def now_ms() -> int:
    """UTC Unix milliseconds; injectable in boundary tests."""
    return time_ns() // 1_000_000
