"""Minimal HEIC -> JPEG converter using only Python + ffmpeg (HEVC decoder).

The system libheif has no HEVC plugin, so we parse the HEIF container
ourselves: find the primary item (usually a 'grid' of HEVC tiles), turn
each tile into an Annex-B HEVC stream with the hvcC parameter sets,
decode with ffmpeg and stitch the tiles with Pillow. EXIF orientation is
not used by HEIC; 'irot'/'imir' properties are honoured instead.

Usage: python3 -m video.heic in.heic out.jpg
"""
import os
import struct
import subprocess
import sys
import tempfile

from PIL import Image


def _boxes(data, start, end):
    pos = start
    while pos + 8 <= end:
        size, typ = struct.unpack(">I4s", data[pos:pos + 8])
        hdr = 8
        if size == 1:
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            hdr = 16
        elif size == 0:
            size = end - pos
        yield typ.decode("latin1"), pos + hdr, pos + size
        pos += size


def _child(data, start, end, name):
    for t, s, e in _boxes(data, start, end):
        if t == name:
            return s, e
    return None


def _uint(data, pos, n):
    if n == 0:
        return 0, pos
    v = int.from_bytes(data[pos:pos + n], "big")
    return v, pos + n


def parse(data):
    meta = _child(data, 0, len(data), "meta")
    ms, me = meta[0] + 4, meta[1]  # full box
    # primary item
    s, e = _child(data, ms, me, "pitm")
    ver = data[s]
    primary = struct.unpack(">H" if ver == 0 else ">I", data[s + 4:s + 6 if ver == 0 else s + 8])[0]
    # item types
    types = {}
    s, e = _child(data, ms, me, "iinf")
    ver = data[s]
    p = s + 4 + (2 if ver == 0 else 4)
    for t, bs, be in _boxes(data, p, e):
        if t != "infe":
            continue
        v = data[bs]
        if v >= 2:
            if v == 2:
                iid = struct.unpack(">H", data[bs + 4:bs + 6])[0]
                q = bs + 8
            else:
                iid = struct.unpack(">I", data[bs + 4:bs + 8])[0]
                q = bs + 10
            types[iid] = data[q:q + 4].decode("latin1")
    # locations
    locs = {}
    idat_box = _child(data, ms, me, "idat")
    idat = idat_box[0] if idat_box else 0
    s, e = _child(data, ms, me, "iloc")
    ver = data[s]
    p = s + 4
    b1, b2 = data[p], data[p + 1]
    off_size, len_size, base_size = b1 >> 4, b1 & 15, b2 >> 4
    idx_size = b2 & 15 if ver in (1, 2) else 0
    p += 2
    if ver < 2:
        count = struct.unpack(">H", data[p:p + 2])[0]; p += 2
    else:
        count = struct.unpack(">I", data[p:p + 4])[0]; p += 4
    for _ in range(count):
        if ver < 2:
            iid = struct.unpack(">H", data[p:p + 2])[0]; p += 2
        else:
            iid = struct.unpack(">I", data[p:p + 4])[0]; p += 4
        method = 0
        if ver in (1, 2):
            method = data[p + 1] & 15
            p += 2  # construction method: 0 = file offset, 1 = idat
        p += 2  # data ref index
        base, p = _uint(data, p, base_size)
        ext_count = struct.unpack(">H", data[p:p + 2])[0]; p += 2
        exts = []
        for _ in range(ext_count):
            _, p = _uint(data, p, idx_size)
            off, p = _uint(data, p, off_size)
            ln, p = _uint(data, p, len_size)
            exts.append((base + off, ln))
        locs[iid] = [(o + (idat if method == 1 else 0), n) for o, n in exts]
    # references (dimg: grid -> tiles)
    refs = {}
    r = _child(data, ms, me, "iref")
    if r:
        ver = data[r[0]]
        n = 2 if ver == 0 else 4
        fmt = ">H" if n == 2 else ">I"
        for t, bs, be in _boxes(data, r[0] + 4, r[1]):
            q = bs
            frm = struct.unpack(fmt, data[q:q + n])[0]; q += n
            cnt = struct.unpack(">H", data[q:q + 2])[0]; q += 2
            to = []
            for _ in range(cnt):
                to.append(struct.unpack(fmt, data[q:q + n])[0]); q += n
            refs.setdefault((t, frm), []).extend(to)
    # properties
    s, e = _child(data, ms, me, "iprp")
    cs, ce = _child(data, s, e, "ipco")
    props = [(t, bs, be) for t, bs, be in _boxes(data, cs, ce)]
    assoc = {}
    for t, bs, be in _boxes(data, s, e):
        if t != "ipma":
            continue
        ver, flags = data[bs], int.from_bytes(data[bs + 1:bs + 4], "big")
        q = bs + 4
        cnt = struct.unpack(">I", data[q:q + 4])[0]; q += 4
        for _ in range(cnt):
            if ver < 1:
                iid = struct.unpack(">H", data[q:q + 2])[0]; q += 2
            else:
                iid = struct.unpack(">I", data[q:q + 4])[0]; q += 4
            n = data[q]; q += 1
            lst = []
            for _ in range(n):
                if flags & 1:
                    v = struct.unpack(">H", data[q:q + 2])[0] & 0x7FFF; q += 2
                else:
                    v = data[q] & 0x7F; q += 1
                lst.append(v)
            assoc[iid] = lst
    return dict(primary=primary, types=types, locs=locs, refs=refs,
                props=props, assoc=assoc)


def _item_data(data, info, iid):
    return b"".join(data[o:o + n] for o, n in info["locs"][iid])


def _prop(info, iid, name):
    for idx in info["assoc"].get(iid, []):
        if idx and info["props"][idx - 1][0] == name:
            return info["props"][idx - 1]
    return None


def _hvcc_annexb(data, box):
    _, s, e = box
    p = s + 22
    narr = data[p]; p += 1
    out = b""
    for _ in range(narr):
        p += 1
        n = struct.unpack(">H", data[p:p + 2])[0]; p += 2
        for _ in range(n):
            ln = struct.unpack(">H", data[p:p + 2])[0]; p += 2
            out += b"\x00\x00\x00\x01" + data[p:p + ln]
            p += ln
    return out


def _to_annexb(buf):
    out, p = b"", 0
    while p + 4 <= len(buf):
        ln = struct.unpack(">I", buf[p:p + 4])[0]; p += 4
        out += b"\x00\x00\x00\x01" + buf[p:p + ln]
        p += ln
    return out


def _decode_tiles(data, info, tiles):
    hdr = _hvcc_annexb(data, _prop(info, tiles[0], "hvcC"))
    stream = b"".join(hdr + _to_annexb(_item_data(data, info, t)) for t in tiles)
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "t.hevc")
        open(src, "wb").write(stream)
        subprocess.run(["ffmpeg", "-v", "error", "-f", "hevc", "-i", src,
                        "-vsync", "0", os.path.join(td, "f%04d.png")], check=True)
        return [Image.open(os.path.join(td, "f%04d.png" % (i + 1))).convert("RGB")
                for i in range(len(tiles))]


def convert(src, dst, quality=95):
    data = open(src, "rb").read()
    info = parse(data)
    pid = info["primary"]
    if info["types"].get(pid) == "grid":
        g = _item_data(data, info, pid)
        flags = g[1]
        rows, cols = g[2] + 1, g[3] + 1
        if flags & 1:
            w, h = struct.unpack(">II", g[4:12])
        else:
            w, h = struct.unpack(">HH", g[4:8])
        tiles = info["refs"][("dimg", pid)]
        imgs = _decode_tiles(data, info, tiles)
        tw, th = imgs[0].size
        canvas = Image.new("RGB", (cols * tw, rows * th))
        for i, im in enumerate(imgs):
            canvas.paste(im, ((i % cols) * tw, (i // cols) * th))
        img = canvas.crop((0, 0, w, h))
    else:
        img = _decode_tiles(data, info, [pid])[0]
        ispe = _prop(info, pid, "ispe")
        if ispe:
            w, h = struct.unpack(">II", data[ispe[1] + 4:ispe[1] + 12])
            img = img.crop((0, 0, w, h))
    rot = _prop(info, pid, "irot")
    if rot:
        angle = (data[rot[1]] & 3) * 90
        if angle:
            img = img.rotate(angle, expand=True)
    mir = _prop(info, pid, "imir")
    if mir:
        img = img.transpose(Image.FLIP_LEFT_RIGHT if data[mir[1]] & 1 == 0
                            else Image.FLIP_TOP_BOTTOM)
    img.save(dst, "JPEG", quality=quality)
    return img.size


if __name__ == "__main__":
    print(convert(sys.argv[1], sys.argv[2]))
