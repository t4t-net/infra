"""Pull client db2 tables for a product straight off blizzard's CDN, no client install.

  version service -> build + cdn config -> encoding (ckey->ekey) + root (fdid->ckey)
  -> archive indexes (ekey -> archive, offset) -> ranged GET -> BLTE -> WDC5 + WoWDBDefs
"""
import re
import struct
import urllib.error
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VERSION = "https://us.version.battle.net/v2/products/{product}/{what}"
DBD = "https://raw.githubusercontent.com/wowdev/WoWDBDefs/master/definitions/{table}.dbd"
UA = {"User-Agent": "forever-ah/0.1 (+tailnet price tracker)"}


def http(url, rng=None):
    headers = dict(UA)
    if rng:
        headers["Range"] = f"bytes={rng[0]}-{rng[0] + rng[1] - 1}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as r:
        return r.read()


def bpsv(text):
    """blizzard's pipe-separated tables: a Name!TYPE:n header, ## comments, rows"""
    lines = [l for l in text.splitlines() if l and not l.startswith("##")]
    cols = [c.split("!")[0] for c in lines[0].split("|")]
    return [dict(zip(cols, l.split("|"))) for l in lines[1:]]


def blte(data):
    if data[:4] != b"BLTE":
        raise ValueError("not BLTE")
    header_size = struct.unpack(">I", data[4:8])[0]
    if header_size == 0:
        chunks = [data[8:]]
    else:
        count = int.from_bytes(data[9:12], "big")
        infos = [struct.unpack(">II", data[12 + i * 24:20 + i * 24]) for i in range(count)]
        pos, chunks = header_size, []
        for comp, _ in infos:
            chunks.append(data[pos:pos + comp])
            pos += comp
    out = bytearray()
    for i, c in enumerate(chunks):
        mode = c[:1]
        if mode == b"N":
            out += c[1:]
        elif mode == b"Z":
            out += zlib.decompress(c[1:])
        elif mode == b"F":
            out += blte(c[1:])
        elif mode == b"E":
            # encrypted 4 a key we dont have; zero fill so offsets still line up
            size = struct.unpack(">II", data[12 + i * 24:20 + i * 24])[1] if header_size else 0
            out += bytes(size)
        else:
            raise ValueError(f"unknown BLTE mode {mode!r}")
    return bytes(out)


class CDN:
    def __init__(self, product, cache, region="us"):
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        v = next(r for r in bpsv(http(VERSION.format(product=product, what="versions")).decode()) if r["Region"] == region)
        c = next(r for r in bpsv(http(VERSION.format(product=product, what="cdns")).decode()) if r["Name"] == region)
        self.build = v["VersionsName"]
        self.hosts = c["Hosts"].split()
        self.path = c["Path"]
        self.build_config = self.config(v["BuildConfig"])
        self.cdn_config = self.config(v["CDNConfig"])

    def url(self, kind, h, suffix=""):
        return f"http://{self.hosts[0]}/{self.path}/{kind}/{h[:2]}/{h[2:4]}/{h}{suffix}"

    def fetch(self, kind, h, suffix="", rng=None):
        """CDN objects r content-addressed, so a cached copy never goes stale"""
        name = f"{kind}-{h}{suffix}" + (f"-{rng[0]}-{rng[1]}" if rng else "")
        p = self.cache / name
        if p.exists():
            return p.read_bytes()
        data = http(self.url(kind, h, suffix), rng)
        p.write_bytes(data)
        return data

    def config(self, h):
        out = {}
        for line in self.fetch("config", h).decode().splitlines():
            if " = " in line:
                k, v = line.split(" = ", 1)
                out[k] = v.split()
        return out


def parse_encoding(data):
    """ckey -> ekey (first of each entry's ekeys)"""
    ckey_size, ekey_size, cpage_kb = data[3], data[4], struct.unpack(">H", data[5:7])[0]
    cpage_count = struct.unpack(">I", data[9:13])[0]
    espec_size = struct.unpack(">I", data[18:22])[0]
    pos = 22 + espec_size + cpage_count * (ckey_size + 16)
    out = {}
    for _ in range(cpage_count):
        page = data[pos:pos + cpage_kb * 1024]
        pos += cpage_kb * 1024
        i = 0
        while i + 6 <= len(page):
            n = page[i]
            if n == 0:
                break
            ckey = page[i + 6:i + 6 + ckey_size]
            ekey = page[i + 6 + ckey_size:i + 6 + ckey_size + ekey_size]
            out[ckey] = ekey
            i += 6 + ckey_size + n * ekey_size
    return out


ENUS = 0x2
NO_NAME_HASH = 0x10000000


def parse_root(data, want):
    """fdid -> ckey 4 just th fdids in want, preferring enUS / all-locale records"""
    if data[:4] != b"TSFM":
        raise ValueError("pre-MFST root, not handled")
    a, b = struct.unpack("<II", data[4:12])
    if a < 100:  # header_size, version, total, named
        header_size, version = a, b
        pos = header_size
    else:  # old MFST: total, named
        version, pos = 0, 12
    found = {}
    while pos < len(data):
        if version >= 2:
            n, locale, u1, u2 = struct.unpack("<IIII", data[pos:pos + 16])
            flags = u1 | u2 | (data[pos + 16] << 17)
            pos += 17
        else:
            n, flags, locale = struct.unpack("<III", data[pos:pos + 12])
            pos += 12
        deltas = struct.unpack(f"<{n}i", data[pos:pos + 4 * n])
        pos += 4 * n
        ckeys = pos
        pos += 16 * n
        if not (flags & NO_NAME_HASH):
            pos += 8 * n
        if not (locale & ENUS) and locale != 0xFFFFFFFF:
            continue
        fdid = -1
        for i, d in enumerate(deltas):
            fdid += d + 1
            if fdid in want and fdid not in found:
                found[fdid] = data[ckeys + 16 * i:ckeys + 16 * i + 16]
    return found


def parse_index(data):
    """archive .index: ekey -> (offset, size)"""
    # footer, counting back from th end: 8 byte checksum, u32 count, checksum_size, key_size,
    # size_bytes, offset_bytes, block_kb
    key_size, block_kb = data[-14], data[-17]
    block = block_kb * 1024
    entry = key_size + 8
    out = {}
    for b in range(0, len(data) - 28, block):
        page = data[b:b + block]
        for i in range(0, len(page) - entry + 1, entry):
            k = page[i:i + key_size]
            if not any(k):
                break
            size, off = struct.unpack(">II", page[i + key_size:i + entry])
            out[k] = (off, size)
    return out


class Storage:
    def __init__(self, product, cache):
        self.cdn = CDN(product, cache)
        enc_ekey = self.cdn.build_config["encoding"][1]
        self.encoding = parse_encoding(blte(self.cdn.fetch("data", enc_ekey)))
        self.archives = self.cdn.cdn_config["archives"]
        self.where = {}
        self._indexed = 0

    def ekey_data(self, ekey):
        h = ekey.hex()
        try:
            return blte(self.cdn.fetch("data", h))  # loose file
        except urllib.error.HTTPError as e:
            # blizzard's cdn answers 403, not 404, 4 "no loose file by that key"
            if e.code not in (403, 404):
                raise
        # walk archive indexes (cached) until we see it
        while ekey not in self.where and self._indexed < len(self.archives):
            batch = self.archives[self._indexed:self._indexed + 32]
            with ThreadPoolExecutor(16) as pool:
                parsed = list(pool.map(lambda a: parse_index(self.cdn.fetch("data", a, ".index")), batch))
            for a, idx in zip(batch, parsed):
                for k, (off, size) in idx.items():
                    self.where.setdefault(k, (a, off, size))
            self._indexed += len(batch)
        if ekey not in self.where:
            raise KeyError(f"ekey {h} not in any archive")
        a, off, size = self.where[ekey]
        return blte(self.cdn.fetch("data", a, rng=(off, size)))

    def ckey_data(self, ckey):
        return self.ekey_data(self.encoding[ckey])

    def files(self, fdids):
        root = blte(self.cdn.fetch("data", self.encoding[bytes.fromhex(self.cdn.build_config["root"][0])].hex()))
        ckeys = parse_root(root, set(fdids))
        return {f: self.ckey_data(c) for f, c in ckeys.items()}


# ---- WDC5

def parse_dbd(text, layout_hash):
    """column names/types from WoWDBDefs, plus th inline field order 4 this layout"""
    cols, section, blocks, cur = {}, None, [], None
    for line in text.splitlines():
        line = line.strip()
        if line == "COLUMNS":
            section = "cols"
            continue
        if not line:
            section = None if section == "cols" else section
            cur = None
            continue
        if section == "cols":
            m = re.match(r"(\w+)(?:<[^>]*>)?\s+(\w+)", line)
            if m:
                cols[m.group(2)] = m.group(1)
            continue
        if line.startswith(("LAYOUT", "BUILD", "COMMENT")):
            if cur is None:
                cur = {"layouts": [], "fields": []}
                blocks.append(cur)
            if line.startswith("LAYOUT"):
                cur["layouts"] += [h.strip().upper() for h in line[6:].split(",")]
            continue
        if cur is not None:
            m = re.match(r"(\$([\w,]+)\$)?(\w+)(?:<(u?)(\d+)>)?(?:\[(\d+)\])?", line)
            ann = (m.group(2) or "").split(",")
            cur["fields"].append({"name": m.group(3), "ann": ann, "unsigned": m.group(4) == "u",
                                  "bits": int(m.group(5)) if m.group(5) else 32, "array": int(m.group(6) or 1),
                                  "type": cols.get(m.group(3), "int")})
    want = f"{layout_hash:08X}"
    for b in blocks:
        if want in b["layouts"]:
            return b["fields"]
    raise KeyError(f"no dbd layout {want}")


def bits(rec, off, n):
    v = int.from_bytes(rec[off // 8:(off + n + 7) // 8 + 1], "little")
    return (v >> (off % 8)) & ((1 << n) - 1)


def read_wdc5(data, dbd_text):
    if data[:4] != b"WDC5":
        raise ValueError(f"not WDC5: {data[:4]!r}")
    p = 4 + 4 + 128
    (record_count, field_count, record_size, string_table_size, table_hash, layout_hash, min_id, max_id, locale,
     flags, id_index, total_field_count, bitpacked_offset, lookup_columns, fsi_size, common_size, pallet_size,
     section_count) = struct.unpack("<9I2H7I", data[p:p + 9 * 4 + 4 + 7 * 4])
    p += 9 * 4 + 4 + 7 * 4
    sections = []
    for _ in range(section_count):
        sections.append(struct.unpack("<QIIIIIIII", data[p:p + 40]))
        p += 40
    p += field_count * 4  # field_structure, fsi has everything we need
    fsi = [struct.unpack("<HHIIIII", data[p + i * 24:p + i * 24 + 24]) for i in range(fsi_size // 24)]
    p += fsi_size
    pallet = data[p:p + pallet_size]
    p += pallet_size
    common_raw = data[p:p + common_size]

    # per-field slices of pallet nd common data, in field order
    pallet_at, common, po, co = [], [], 0, 0
    for f in fsi:
        stype, extra = f[3], f[2]
        pallet_at.append(po)
        common.append({})
        if stype in (3, 4):
            po += extra
        if stype == 2:
            for j in range(extra // 8):
                k, v = struct.unpack("<II", common_raw[co + j * 8:co + j * 8 + 8])
                common[-1][k] = v
            co += extra

    fields = parse_dbd(dbd_text, layout_hash)
    inline = [f for f in fields if "noninline" not in f["ann"] and not ("id" in f["ann"] and flags & 0x4)]
    rel = next((f for f in fields if "relation" in f["ann"]), None)
    idf = next((f for f in fields if "id" in f["ann"]), None)
    if flags & 0x1:
        return read_sparse(data, sections, inline, idf)

    rows = []
    for tact_key, off, n, st_size, _, idl_size, rel_size, _, copy_count in sections:
        if tact_key and not any(data[off:off + n * record_size]):
            continue  # encrypted section, no key
        recs = data[off:off + n * record_size]
        q = off + n * record_size + st_size
        ids = list(struct.unpack(f"<{idl_size // 4}I", data[q:q + idl_size])) if idl_size else []
        q += idl_size
        copies = [struct.unpack("<II", data[q + i * 8:q + i * 8 + 8]) for i in range(copy_count)]
        q += copy_count * 8
        relmap = {}
        if rel_size:
            cnt = struct.unpack("<I", data[q:q + 4])[0]
            for i in range(cnt):
                fk, ri = struct.unpack("<II", data[q + 12 + i * 8:q + 20 + i * 8])
                relmap[ri] = fk
        for r in range(n):
            rec = recs[r * record_size:(r + 1) * record_size]
            row, raw = {}, []
            for fi, f in enumerate(fsi):
                foff, fbits, extra, stype, a1, a2, a3 = f
                if stype == 0:
                    raw.append(int.from_bytes(rec[foff // 8:(foff + fbits) // 8], "little"))
                elif stype in (1, 5):
                    v = bits(rec, foff, fbits)
                    if stype == 5 and v >> (fbits - 1):
                        v -= 1 << fbits
                    raw.append(v)
                elif stype == 2:
                    raw.append(None)  # filled once we know th id
                elif stype == 3:
                    i = bits(rec, foff, fbits)
                    raw.append(struct.unpack("<I", pallet[pallet_at[fi] + i * 4:pallet_at[fi] + i * 4 + 4])[0])
                elif stype == 4:
                    i = bits(rec, foff, fbits)
                    base = pallet_at[fi] + i * 4 * a3
                    raw.append(list(struct.unpack(f"<{a3}I", pallet[base:base + 4 * a3])))
            rid = ids[r] if ids else raw[id_index]
            for fi, f in enumerate(fsi):
                if f[3] == 2:
                    raw[fi] = common[fi].get(rid, f[4])
            for fdef, f, v in zip(inline, fsi, raw):
                b = fdef["bits"]
                if f[3] == 0 and fdef["type"] == "int":
                    # uncompressed fields r packed little endian, arrays back 2 back
                    vals = [(v >> (b * k)) & ((1 << b) - 1) for k in range(fdef["array"])]
                    if not fdef["unsigned"]:
                        vals = [x - (1 << b) if x >> (b - 1) else x for x in vals]
                    v = vals if fdef["array"] > 1 else vals[0]
                row[fdef["name"]] = v
            if idf:
                row[idf["name"]] = rid
            if rel:
                row[rel["name"]] = relmap.get(r)
            rows.append(row)
        for new, old in copies:
            src = next((x for x in rows if x.get(idf["name"] if idf else "ID") == old), None)
            if src:
                rows.append({**src, (idf["name"] if idf else "ID"): new})
    return rows


def inline_fields(data, dbd_text):
    """th dbd fields actually stored in each record of this db2, 4 walking hotfix rows of th same table"""
    layout_hash, flags = struct.unpack("<I", data[156:160])[0], struct.unpack("<H", data[172:174])[0]
    return [f for f in parse_dbd(dbd_text, layout_hash)
            if "noninline" not in f["ann"] and not ("id" in f["ann"] and flags & 0x4)]


def walk_record(b, fields, p=0):
    """unpacked record: fields back 2 back, strings inline nd nul terminated. returns (row, end offset)"""
    row = {}
    for f in fields:
        vals = []
        for _ in range(f["array"]):
            if f["type"] in ("string", "locstring"):
                z = b.index(b"\0", p)
                vals.append(b[p:z].decode(errors="replace"))
                p = z + 1
            elif f["type"] == "float":
                vals.append(struct.unpack("<f", b[p:p + 4])[0])
                p += 4
            else:
                n = f["bits"] // 8
                vals.append(int.from_bytes(b[p:p + n], "little", signed=not f["unsigned"]))
                p += n
        row[f["name"]] = vals if f["array"] > 1 else vals[0]
    return row, p


def read_sparse(data, sections, fields, idf):
    """offset map tables (ItemSparse etc) store records unpacked, so walk each one by its dbd types"""
    rows = []
    for tact_key, off, _, _, end, idl_size, rel_size, map_count, copy_count in sections:
        if tact_key and not any(data[off:end]):
            continue
        q = end + idl_size + copy_count * 8
        spans = [struct.unpack("<IH", data[q + i * 6:q + i * 6 + 6]) for i in range(map_count)]
        q += map_count * 6 + rel_size
        ids = struct.unpack(f"<{map_count}I", data[q:q + map_count * 4])
        for rid, (o, size) in zip(ids, spans):
            row, p = walk_record(data, fields, o)
            # records r zero padded 2 4 bytes
            if not 0 <= o + size - p < 4 or any(data[p:o + size]):
                raise ValueError(f"record {rid}: walked {p - o} of {size} bytes")
            if idf:
                row[idf["name"]] = rid
            rows.append(row)
    return rows


# ---- hotfixes
# blizz patches db2 rows server side nd pushes them at login, nd th client caches them in
# Cache/ADB/<locale>/DBCache.bin. th cdn files nd th battle.net api both serve th unpatched rows

HOTFIX_VALID = 1  # 2 = row deleted, 3/4 = not 4 this client


def read_dbcache(data):
    """(build, {(table hash, record id): (push id, status, record bytes)}), newest push per row"""
    if data[:4] != b"XFTH":
        raise ValueError(f"not a DBCache: {data[:4]!r}")
    _, build = struct.unpack("<II", data[4:12])
    rows, p = {}, 44
    while p + 32 <= len(data):
        magic, _, push, _, table, rec, size, status = struct.unpack("<4siiIIIIB", data[p:p + 29])
        if magic != b"XFTH":
            raise ValueError(f"lost sync at {p:#x}")
        p += 32
        if (table, rec) not in rows or push >= rows[table, rec][0]:
            rows[table, rec] = (push, status, data[p:p + size])
        p += size
    return build, rows
