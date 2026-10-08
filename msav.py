"""Writer and validator for Mindustry map files (.msav), save format 13.

Mirrors mindustry.io.SaveVersion / SaveFileReader from the game source at tag v159.7
(v8 Build 159.7). Layout of a map file:

    zlib( "MSAV" | int version | region meta | region patches | region content
          | region map | region entities | region markers | region custom )

Every region is an int length followed by its bytes. All numbers are big-endian (Java DataOutput).
"""

import math
import struct
import zlib

SAVE_VERSION = 13
PATCH_FORMAT_VERSION = 2          # mindustry.mod.DataPatcher.patchFormatVersion
DATA_ASSET_PATCH = 0              # mindustry.mod.data.DataAssetType.patch.ordinal()
CONTENT_TYPE_BLOCK = 1            # ContentType.block.ordinal()
CORE_BUILD_REVISION = 1           # CoreBlock.CoreBuild.version()
TEAM_SHARDED = 1

# The reader replaces an unknown floor with the block whose *runtime* id equals Blocks.stone.id (33)
# by looking that id up in this file's own table. Copying the first 34 runtime block ids keeps
# that fallback pointing at real stone (relevant when the map is opened without the mod).
RUNTIME_BLOCK_PREFIX = (
    ["air", "spawn", "remove-wall", "remove-ore", "cliff"]
    + ["build%d" % i for i in range(1, 17)]
    + ["deep-water", "shallow-water", "tainted-water", "deep-tainted-water", "darksand-tainted-water",
       "sand-water", "darksand-water", "tar", "pooled-cryofluid", "molten-slag", "space", "empty", "stone"]
)


def java_utf(text):
    """DataOutput.writeUTF: 2-byte length + modified UTF-8."""
    out = bytearray()
    for ch in text:
        c = ord(ch)
        if 0x01 <= c <= 0x7F:
            out.append(c)
        elif c <= 0x7FF:
            out += bytes((0xC0 | (c >> 6), 0x80 | (c & 0x3F)))
        elif c <= 0xFFFF:
            out += bytes((0xE0 | (c >> 12), 0x80 | ((c >> 6) & 0x3F), 0x80 | (c & 0x3F)))
        else:
            c -= 0x10000
            for unit in (0xD800 | (c >> 10), 0xDC00 | (c & 0x3FF)):
                out += bytes((0xE0 | (unit >> 12), 0x80 | ((unit >> 6) & 0x3F), 0x80 | (unit & 0x3F)))
    if len(out) > 0xFFFF:
        raise ValueError("String too long for writeUTF (%d bytes)" % len(out))
    return struct.pack(">H", len(out)) + bytes(out)


def core_chunk(team_id=TEAM_SHARDED):
    """Building data of a core: revision + Building.writeBase + CoreBuild.write."""
    body = bytearray()
    body += struct.pack(">b", CORE_BUILD_REVISION)
    body += struct.pack(">f", 1.0e9)          # health; the reader caps it at the block's max health
    body += struct.pack(">B", 0x80)           # rotation 0 | "new format" flag
    body += struct.pack(">B", team_id)
    body += struct.pack(">B", 3)              # base version 3 (no fog visibility flags)
    body += struct.pack(">B", 1)              # enabled
    body += struct.pack(">B", 1 << 3)         # module bitmask: no item/power/liquid payloads follow
    body += struct.pack(">BB", 0, 0)          # efficiency, optionalEfficiency
    body += struct.pack(">ff", math.nan, math.nan)  # commandPos = null
    return bytes(body)


def _region(data):
    return struct.pack(">i", len(data)) + data


def _string_map(tags):
    out = bytearray(struct.pack(">h", len(tags)))
    for key, value in tags.items():
        out += java_utf(str(key))
        out += java_utf(str(value))
    return bytes(out)


def building_tiles(x, y, size):
    """Tiles covered by a block of `size` whose center tile is (x, y) (Block.sizeOffset)."""
    offset = -((size - 1) // 2)
    return [(x + dx + offset, y + dy + offset) for dy in range(size) for dx in range(size)]


def encode_map(width, height, floors, overlays, walls, buildings):
    """`floors`/`overlays`/`walls` are per-tile indexes into the block table (row-major, y=0 first).
    `buildings` is a list of dicts {x, y, size, block, chunk}."""
    total = width * height
    building_at = {}
    for b in buildings:
        for (tx, ty) in building_tiles(b["x"], b["y"], b["size"]):
            building_at[ty * width + tx] = b
            walls[ty * width + tx] = b["block"]

    out = bytearray(struct.pack(">HH", width, height))
    pack_floor = struct.Struct(">hhB").pack
    i = 0
    while i < total:
        f, o = floors[i], overlays[i]
        j = i + 1
        while j < total and j - i - 1 < 255 and floors[j] == f and overlays[j] == o:
            j += 1
        out += pack_floor(f, o, j - i - 1)
        i = j

    pack_run = struct.Struct(">hBB").pack
    i = 0
    while i < total:
        b = building_at.get(i)
        if b is not None:
            center = (i == b["y"] * width + b["x"])
            out += struct.pack(">hB?", b["block"], 1, center)
            if center:
                out += _region(b["chunk"])
            i += 1
            continue
        w = walls[i]
        j = i + 1
        while j < total and j - i - 1 < 255 and walls[j] == w and j not in building_at:
            j += 1
        out += pack_run(w, 0, j - i - 1)
        i = j
    return bytes(out)


def data_patches(patches):
    """SaveVersion.writeDataPatches with embedded PatchAssets: `patches` is a list of (path, json text).
    The game applies them to its content while the map is loaded and undoes them afterwards."""
    out = bytearray(struct.pack(">ii", PATCH_FORMAT_VERSION, len(patches)))
    for name, text in patches:
        body = text.encode("utf-8")
        out += struct.pack(">b", DATA_ASSET_PATCH) + java_utf(name) + struct.pack(">?", True)
        out += struct.pack(">i", len(body)) + body
    return bytes(out)


def write_msav(path, width, height, block_table, floors, overlays, walls, buildings, tags, patches=()):
    meta = _string_map(tags)
    content = bytearray(struct.pack(">B", 1))
    content += struct.pack(">bh", CONTENT_TYPE_BLOCK, len(block_table))
    for name in block_table:
        content += java_utf(name)
    tiles = encode_map(width, height, floors, overlays, walls, buildings)
    # entity id mapping (none), team plans (sharded, no plans), world entities (none)
    entities = struct.pack(">h", 0) + struct.pack(">i", 1) + struct.pack(">ii", TEAM_SHARDED, 0) + struct.pack(">i", 0)
    markers = b"{}"   # UBJSON empty object = empty MapMarkers IntMap
    custom = struct.pack(">i", 0)

    raw = bytearray(b"MSAV")
    raw += struct.pack(">i", SAVE_VERSION)
    for region in (meta, data_patches(patches), bytes(content), tiles, entities, markers, custom):
        raw += _region(region)
    data = zlib.compress(bytes(raw), 9)
    with open(path, "wb") as fh:
        fh.write(data)
    return len(raw), len(data)


# ----------------------------------------------------------------------------------------------
# Validator: parses the file the same way SaveVersion.read does and checks every region length.
# ----------------------------------------------------------------------------------------------

class _Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, n):
        if self.pos + n > len(self.data):
            raise ValueError("Unexpected end of data at %d (+%d)" % (self.pos, n))
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def unpack(self, fmt):
        s = struct.Struct(fmt)
        return s.unpack(self.take(s.size))

    def i(self):
        return self.unpack(">i")[0]

    def h(self):
        return self.unpack(">h")[0]

    def ub(self):
        return self.unpack(">B")[0]

    def b(self):
        return self.unpack(">b")[0]

    def utf(self):
        n = self.unpack(">H")[0]
        raw = self.take(n)
        return raw.replace(b"\xc0\x80", b"\x00").decode("utf-8", errors="surrogatepass")


def validate_msav(path, known_blocks=None):
    """Re-reads a map file. Returns a summary dict; raises ValueError on any inconsistency."""
    with open(path, "rb") as fh:
        raw = zlib.decompress(fh.read())
    r = _Reader(raw)
    if r.take(4) != b"MSAV":
        raise ValueError("Bad header")
    version = r.i()
    if version != SAVE_VERSION:
        raise ValueError("Unexpected save version %d" % version)

    def region(name, parse):
        length = r.i()
        start = r.pos
        result = parse(r)
        if r.pos - start != length:
            raise ValueError("Region %s: length %d but parser consumed %d" % (name, length, r.pos - start))
        return result

    def parse_meta(rd):
        count = rd.h()
        return {rd.utf(): rd.utf() for _ in range(count)}

    def parse_patches(rd):
        rd.i()                                   # format version, ignored by the game
        total = rd.i()
        assets = []
        for _ in range(total):
            kind = rd.b()
            asset_path = rd.utf()
            embedded = rd.unpack(">?")[0]
            if kind != DATA_ASSET_PATCH or not embedded:
                raise ValueError("Expected only embedded patch assets")
            length = rd.i()
            assets.append({"path": asset_path, "text": rd.take(length).decode("utf-8")})
        return assets

    def parse_content(rd):
        mapped = rd.ub()
        table = {}
        for _ in range(mapped):
            ctype = rd.b()
            total = rd.h()
            table[ctype] = [rd.utf() for _ in range(total)]
        return table

    tags = region("meta", parse_meta)
    patches = region("patches", parse_patches)
    content = region("content", parse_content)
    blocks = content.get(CONTENT_TYPE_BLOCK, [])
    if known_blocks is not None:
        unknown = [b for b in blocks if b not in known_blocks]
        if unknown:
            raise ValueError("Unknown block names in content header: %s" % unknown)

    stats = {"floor_runs": 0, "block_runs": 0, "buildings": []}

    def parse_map(rd):
        width, height = rd.unpack(">HH")
        total = width * height
        floors = [0] * total
        overlays = [0] * total
        walls = [0] * total
        i = 0
        while i < total:
            f, o, c = rd.unpack(">hhB")
            if not (0 <= f < len(blocks)) or not (0 <= o < len(blocks)):
                raise ValueError("Floor/overlay id out of range at tile %d" % i)
            for j in range(i, min(total, i + c + 1)):
                floors[j] = f
                overlays[j] = o
            stats["floor_runs"] += 1
            i += c + 1
        if i != total:
            raise ValueError("Floor runs overflow the map")
        i = 0
        while i < total:
            block = rd.h()
            if not (0 <= block < len(blocks)):
                raise ValueError("Block id out of range at tile %d" % i)
            packed = rd.b()
            had_entity = (packed & 1) != 0
            had_data = (packed & 4) != 0
            if had_data:
                rd.take(7)
            walls[i] = block
            if had_entity:
                center = rd.unpack(">?")[0]
                if center:
                    length = rd.i()
                    start = rd.pos
                    revision = rd.b()
                    health, rot, team, base_version, enabled, modules, eff, opt = rd.unpack(">fBBBBBBB")
                    if not (rot & 0x80) or base_version != 3 or modules != 8:
                        raise ValueError("Unexpected building base data")
                    cmd = rd.unpack(">ff") if revision >= 1 else None
                    if rd.pos - start != length:
                        raise ValueError("Building chunk length mismatch")
                    stats["buildings"].append({"block": blocks[block], "x": i % width, "y": i // width,
                                               "team": team, "revision": revision, "commandPos": cmd})
                i += 1
            elif not had_data:
                run = rd.ub()
                for j in range(i, min(total, i + run + 1)):
                    walls[j] = block
                stats["block_runs"] += 1
                i += run + 1
            else:
                i += 1
        if i != total:
            raise ValueError("Block runs overflow the map")
        return width, height, floors, overlays, walls

    width, height, floors, overlays, walls = region("map", parse_map)

    def parse_entities(rd):
        mappings = rd.h()
        for _ in range(mappings):
            rd.h()
            rd.utf()
        teams = rd.i()
        team_ids = []
        for _ in range(teams):
            team_ids.append(rd.i())
            plans = rd.i()
            if plans:
                raise ValueError("Unexpected block plans")
        entities = rd.i()
        if entities:
            raise ValueError("Unexpected world entities")
        return team_ids

    teams = region("entities", parse_entities)

    def parse_markers(rd):
        if rd.take(2) != b"{}":
            raise ValueError("Markers region is not an empty UBJSON object")

    region("markers", parse_markers)

    def parse_custom(rd):
        if rd.i() != 0:
            raise ValueError("Unexpected custom chunks")

    region("custom", parse_custom)
    if r.pos != len(raw):
        raise ValueError("Trailing bytes after the last region: %d" % (len(raw) - r.pos))

    return {
        "version": version, "width": width, "height": height, "tags": tags, "patches": patches, "blocks": blocks,
        "floors": floors, "overlays": overlays, "walls": walls, "teams": teams, **stats,
    }
