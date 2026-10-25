"""ULID monotonik: 48 bit waktu (ms) + 80 bit acak, Crockford base32, 26 karakter.

ID yang dibuat dalam milidetik yang sama tetap berurutan (bagian acak dinaikkan +1), jadi
urutan audit log & ledger stabil walaupun jam tidak bergerak (misalnya FakeClock di test).
"""

from __future__ import annotations

import secrets
import threading

from studio.shared.clock import Clock, SystemClock

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_LENGTH = 26
_RANDOM_MAX = (1 << 80) - 1

_lock = threading.Lock()
_last_millis = -1
_last_random = 0


def _encode(value: int) -> str:
    chars = []
    for _ in range(_LENGTH):
        value, index = divmod(value, 32)
        chars.append(_ALPHABET[index])
    return "".join(reversed(chars))


def new_id(clock: Clock | None = None) -> str:
    global _last_millis, _last_random
    millis = int((clock or SystemClock()).now().timestamp() * 1000)
    with _lock:
        if millis <= _last_millis:
            # Jam sama (atau mundur): lanjutkan dari ID terakhir supaya tetap urut.
            millis = _last_millis
            random_part = _last_random + 1
            if random_part > _RANDOM_MAX:
                millis += 1
                random_part = secrets.randbits(79)
        else:
            random_part = secrets.randbits(79)  # sisakan ruang untuk penambahan
        _last_millis, _last_random = millis, random_part
    return _encode((millis << 80) | random_part)


def is_valid_id(value: str) -> bool:
    return len(value) == _LENGTH and all(char in _ALPHABET for char in value)
