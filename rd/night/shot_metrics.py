#!/usr/bin/python3
"""Region image metrics for a baseline and a variant screenshot, standard library only.

    python3 rd/night/shot_metrics.py <base.png> <variant.png> <x> <y> <w> <h> [grow] [thresh]

Prints JSON: size and mean luma of each frame; inside the region, median and 99th-percentile
luma and the contrast (p99 + 5) / (median + 5); outside the region grown by `grow` px
(default 4), the share of pixels whose largest channel difference exceeds `thresh` (default
24). Luma is Rec. 601 on 8-bit values. Reads 8-bit RGB or RGBA, non-interlaced PNG, the
format Unreal's screenshots use. Python 3.9 compatible.
"""

import json
import struct
import sys
import zlib


def read_png(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: not a PNG")
    pos, idat, width, height, channels = 8, [], 0, 0, 0
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or color not in (2, 6) or interlace:
                raise ValueError(f"{path}: only 8-bit RGB/RGBA non-interlaced PNG")
            channels = 3 if color == 2 else 4
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    raw = zlib.decompress(b"".join(idat))
    stride = width * channels
    rows, prev = [], bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1 : start + 1 + stride])
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b = prev[i]
            c = prev[i - channels] if i >= channels else 0
            if kind == 1:
                line[i] = (line[i] + a) & 255
            elif kind == 2:
                line[i] = (line[i] + b) & 255
            elif kind == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif kind == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 255
        rows.append(line)
        prev = line
    return width, height, channels, rows


def luma(row, x, ch):
    return 0.299 * row[x * ch] + 0.587 * row[x * ch + 1] + 0.114 * row[x * ch + 2]


def pct(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))]


def main(argv):
    if len(argv) < 7:
        sys.exit(__doc__)
    base, var = read_png(argv[1]), read_png(argv[2])
    x0, y0, w, h = (int(v) for v in argv[3:7])
    grow = int(argv[7]) if len(argv) > 7 else 4
    threshold = int(argv[8]) if len(argv) > 8 else 24
    out = {"region": [x0, y0, w, h], "grow_px": grow, "diff_threshold": threshold}
    for name, (wd, ht, ch, rows) in (("baseline", base), ("variant", var)):
        all_l = [luma(r, x, ch) for r in rows for x in range(wd)]
        xs = range(max(0, x0), min(wd, x0 + w))
        inside = [luma(rows[y], x, ch) for y in range(max(0, y0), min(ht, y0 + h)) for x in xs]
        med, p99 = pct(inside, 0.5), pct(inside, 0.99)
        out[name] = {
            "size": [wd, ht],
            "mean_luma": round(sum(all_l) / len(all_l), 2),
            "region_median_luma": round(med, 2),
            "region_p99_luma": round(p99, 2),
            "region_contrast": round((p99 + 5) / (med + 5), 3),
        }
    if base[:2] != var[:2]:
        out["outside_changed_share"] = None
    else:
        wd, ht = base[0], base[1]
        changed = total = 0
        for y in range(ht):
            rb, rv = base[3][y], var[3][y]
            for x in range(wd):
                if x0 - grow <= x < x0 + w + grow and y0 - grow <= y < y0 + h + grow:
                    continue
                total += 1
                d = max(abs(rb[x * base[2] + k] - rv[x * var[2] + k]) for k in range(3))
                changed += d > threshold
        out["outside_changed_share"] = round(changed / total, 5)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv)
