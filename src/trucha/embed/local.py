from __future__ import annotations

import hashlib
import math
import re

TOKEN_RE = re.compile(r"[\w.-]+", re.UNICODE)


def embed_text(text: str, dimensions: int = 64) -> list[float]:
    """Create a deterministic, dependency-free embedding for local development."""
    vector = [0.0] * dimensions
    for token in TOKEN_RE.findall(text.lower()):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
        index = int.from_bytes(digest[:8], "big") % dimensions
        sign = 1.0 if digest[8] & 1 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    return vector if norm == 0 else [value / norm for value in vector]
