"""Секции файла .MDN: цепочка записей [tag:1][len:2 LE][body:len].
Запись с tag=0x3f и len=8 открывает секцию (имя в cp866: INFOCONT, INFOBLKS, INFOZADM, INFOFR15, INFOPICT, INFOHIST)."""
from __future__ import annotations
import struct


def read_sections(path: str) -> dict[str, list[bytes]]:
    d = open(path, 'rb').read()
    i, cur, sec = 0, None, {}
    while i < len(d) - 3:
        tag = d[i]
        ln = int.from_bytes(d[i + 1:i + 3], 'little')
        body = d[i + 3:i + 3 + ln]
        i += 3 + ln
        if tag == 0x3f and ln == 8:
            cur = body.decode('cp866')
            sec.setdefault(cur, [])
        elif cur is not None:
            sec[cur].append(body)
    return sec


def section_blob(sec: dict[str, list[bytes]], name: str) -> bytes:
    return b''.join(x for x in sec[name] if len(x) > 8)


def read_zadm(sec: dict[str, list[bytes]]) -> dict:
    """INFOZADM: [mode:1][horizon:f32][dt:f32][dt_out:f32][x:f32] — гипотеза (17 байт)."""
    b = b''.join(sec.get('INFOZADM', []))
    if len(b) < 17:
        return {}
    mode = b[0]
    f = struct.unpack_from('<4f', b, 1)
    return dict(mode=mode, horizon=f[0], dt=f[1], dt_out=f[2], extra=f[3])
