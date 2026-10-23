"""Parser for the PSF/param.sfo application metadata format."""

import struct

PSF_MAGIC = 0x46535000
FMT_UTF8_SPECIAL = 0x0004
FMT_UTF8 = 0x0204
FMT_INT32 = 0x0404


def parse(data):
    if len(data) < 20 or struct.unpack_from("<I", data, 0)[0] != PSF_MAGIC:
        raise ValueError("not a param.sfo (bad magic)")

    version, key_off, data_off, count = struct.unpack_from("<IIII", data, 4)

    entries = {}
    for i in range(count):
        base = 20 + i * 16
        if base + 16 > len(data):
            break
        key_rel, fmt, length, max_len, data_rel = struct.unpack_from("<HHIII", data, base)

        key_pos = key_off + key_rel
        key_end = data.find(b"\x00", key_pos)
        if key_end < 0:
            key_end = len(data)
        try:
            key = data[key_pos:key_end].decode("utf-8", "replace")
        except Exception:
            continue

        raw = data[data_off + data_rel: data_off + data_rel + length]
        if fmt in (FMT_UTF8, FMT_UTF8_SPECIAL):
            value = raw.split(b"\x00", 1)[0].decode("utf-8", "replace")
        elif fmt == FMT_INT32:
            value = struct.unpack("<i", raw[:4].ljust(4, b"\x00"))[0]
        else:
            value = raw
        entries[key] = value

    return entries


def parse_file(path):
    with open(path, "rb") as fh:
        return parse(fh.read())
