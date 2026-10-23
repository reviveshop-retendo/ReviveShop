#!/usr/bin/env python3
"""Minimal IPS (International Patching System) build/inspect/apply tool.

Used by the ReviveShop Nimbus-style patch set. IPS is the format Luma3DS
consumes for sysmodule patches (/luma/sysmodules/<tid>.ips) and per-title
patches (/luma/titles/<tid>/code.ips).

    # inspect
    ./ips.py inspect 0004013000002F02.ips

    # create:  one or more OFF=HEXBYTES pairs (offset is decimal or 0x-hex,
    #          patch bytes are hex with optional spaces/colons)
    ./ips.py create out.ips 0x6c56=0x18e7...

    # apply to a base binary and write the patched result
    ./ips.py apply in.ips code.bin patched.bin
"""
import sys


def read(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:5] != b"PATCH":
        raise ValueError("not an IPS file (missing PATCH magic)")
    i = 5
    records = []
    while True:
        if data[i:i + 3] == b"EOF":
            break
        offset = int.from_bytes(data[i:i + 3], "big")
        size = int.from_bytes(data[i + 3:i + 5], "big")
        i += 5
        if size == 0:
            rle_size = int.from_bytes(data[i:i + 2], "big")
            value = data[i + 2]
            i += 3
            records.append((offset, bytes([value]) * rle_size, True))
        else:
            records.append((offset, data[i:i + size], False))
            i += size
    return records


def write(path, records):
    out = bytearray(b"PATCH")
    for rec in records:
        offset, blob = rec[0], rec[1]
        if len(blob) == 0:
            continue
        if len(offset.to_bytes(3, "big")) > 3:
            raise ValueError("offset too large for IPS (max 0xFFFFFF)")
        out += offset.to_bytes(3, "big")
        # simple RLE when a long run of one byte
        if len(blob) > 4 and len(set(blob)) == 1:
            out += b"\x00\x00" + len(blob).to_bytes(2, "big") + bytes([blob[0]])
        else:
            out += len(blob).to_bytes(2, "big") + blob
    out += b"EOF"
    with open(path, "wb") as fh:
        fh.write(out)
    return len(out)


def apply(base_path, records, out_path):
    with open(base_path, "rb") as fh:
        data = bytearray(fh.read())
    for offset, blob, _ in records:
        if offset + len(blob) > len(data):
            data.extend(b"\x00" * (offset + len(blob) - len(data)))
        data[offset:offset + len(blob)] = blob
    with open(out_path, "wb") as fh:
        fh.write(data)


def parse_bytes(text):
    text = text.replace("0x", "").replace(" ", "").replace(":", "").replace(",", "")
    return bytes.fromhex(text)


def parse_offset(text):
    if text.lower().startswith("0x"):
        return int(text, 16)
    return int(text, 0)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    cmd = argv[1]
    if cmd == "inspect":
        for offset, blob, rle in read(argv[2]):
            tag = " (RLE)" if rle else ""
            print(f"offset 0x{offset:06x}  {len(blob):>5} bytes{tag}  "
                  f"{blob[:16].hex()}{'...' if len(blob) > 16 else ''}")
        return 0
    if cmd == "create":
        records = []
        for pair in argv[3:]:
            off, _, hexv = pair.partition("=")
            records.append((parse_offset(off), parse_bytes(hexv), False))
        n = write(argv[2], records)
        print(f"wrote {argv[2]} ({n} bytes, {len(records)} record(s))")
        return 0
    if cmd == "apply":
        records = read(argv[2])
        apply(argv[3], records, argv[4])
        print(f"applied {len(records)} record(s) -> {argv[4]}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
