"""Bounded single-worker admission limits, before credential hashing or body parsing."""
from math import ceil
from time import monotonic


class AuthLimiter:
    # A process restart clears limits. Multiple workers are intentionally unsupported.
    RULES = {'/api/v1/auth/login': (10, 60), '/api/v1/auth/register': (5, 3600),
             '/api/v1/auth/password-reset/request': (5, 3600),
             '/api/v1/auth/password-reset/confirm': (10, 60)}

    def __init__(self, capacity=10000, clock=monotonic):
        self.buckets = {}
        self.capacity = capacity
        self.clock = clock

    def check(self, path, client):
        rule = self.RULES.get(path.rstrip('/'))
        if rule is None:
            return 0
        now = self.clock()
        # Expired entries do not make the key space grow without bound.
        self.buckets = {key: value for key, value in self.buckets.items() if value[1] > now}
        key = (path.rstrip('/'), client)
        entry = self.buckets.get(key)
        if entry is None:
            if len(self.buckets) >= self.capacity:
                return max(1, ceil(min(value[1] for value in self.buckets.values()) - now))
            entry = (0, now + rule[1])
        count, expires = entry
        if count >= rule[0]:
            return max(1, ceil(expires - now))
        self.buckets[key] = (count + 1, expires)
        return 0
