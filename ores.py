"""In-game ore placement for "Biomes Extended Remastered".

Ore nodes are not baked into the map. The map's "genfilters" tag holds a list of generation filters that
the game runs every time the map is loaded: World.FilterContext.applyFilters calls filter.randomize()
(a fresh random seed) before applying each one, so every game rolls new ore positions.

This module defines that filter list (`build_filters`) and ports the game's noise function
(arc.util.noise.Simplex at Arc 208a754044, the version pinned by Mindustry v159.7) together with the
OreFilter / NoiseFilter rules (mindustry.maps.filters at v159.7). The generator uses the port to preview
rolls (`roll`) and to measure how much ore a typical game gets (`measure`).
"""

import json
import math
import random
import struct
from collections import deque

# ----------------------------------------------------------------------------------------------
# Filter list
# ----------------------------------------------------------------------------------------------

OCTAVES = 2.0
FALLOFF = 0.15   # weak second octave: round, solid patches with few one-tile specks

# Map-wide layer: every ore can turn up on any open ground of every biome.
# (ore, scale, threshold). The scale sets how many patches an ore gets (about 1 / scale^2.4) and the
# threshold how big they are. On this map the whole list gives ~1,250 patches per game with a median of
# ~33 tiles (10-88 for 80% of them); the README quotes the measured numbers from the report.
# All scales and thresholds below (and in TENDENCIES / CRYSTAL_HOSTS) were tuned together for ~15% less
# ore than the first random layout: each threshold keeps 85% of the area the old one covered, and each
# scale is ~4% larger so that the cut removes patches rather than shrinking them.
WIDESPREAD = (
    ("ore-copper", 46, 0.881), ("ore-lead", 46, 0.881),
    ("ore-coal", 48, 0.885), ("ore-titanium", 48, 0.885),
    ("ore-scrap", 52, 0.885), ("ore-thorium", 52, 0.885),
    ("ore-beryllium", 56, 0.885), ("ore-tungsten", 56, 0.885),
    ("ore-dytrix", 56, 0.885), ("ore-urbium", 56, 0.885),
    ("ore-siradamite", 56, 0.885), ("ore-stellar-steel", 56, 0.885),
)

# Biome tendencies: extra patches of a few ores on a floor that (nearly) only one biome has. They make
# those ores about 1.5-2x as common there without taking any ore away from the other biomes.
# (floor, ore, scale, threshold)
TENDENCIES = (
    ("stone", "ore-copper", 31, 0.844),          # Crossroads Basin + Ring Road: starter copper and lead
    ("stone", "ore-lead", 31, 0.848),
    ("grass", "ore-coal", 42, 0.881),            # Forest
    ("moss", "ore-lead", 42, 0.881),
    ("basalt", "ore-thorium", 42, 0.881),        # Volcano
    ("basalt", "ore-tungsten", 44, 0.881),
    ("basalt", "ore-beryllium", 42, 0.881),
    ("snow", "ore-titanium", 36, 0.867),         # Frozen tundra
    ("ice-snow", "ore-titanium", 36, 0.867),
    ("siratla-stone", "ore-siradamite", 40, 0.876),  # Siratla Glacier
    ("siratla-stone", "ore-stellar-steel", 40, 0.876),
    ("dacite", "ore-dytrix", 37, 0.871),         # Semi-arid steppe
    ("dirt", "ore-titanium", 46, 0.885),
    ("sand-floor", "ore-scrap", 42, 0.881),      # Desert
    ("sand-floor", "ore-urbium", 44, 0.881),
)

# Siratla crystal is a floor (drills astrolite), so it is placed by NoiseFilters, one per host floor.
# (floor it replaces, scale, threshold): dense on the glacier, sparse in every other biome.
CRYSTAL = "siratla-crystal"
CRYSTAL_HOSTS = (
    ("siratla-stone", 37, 0.876),
    ("snow", 50, 0.894), ("basalt", 50, 0.894), ("grass", 50, 0.894), ("dirt", 50, 0.894), ("sand-floor", 50, 0.894),
)

# Floors kept free of ore: outpost pads (core-zone + ring) and the core plaza (metal floor + border).
CLEAR_FLOORS = ("core-zone", "dark-panel-3", "metal-floor", "dark-panel-4")


def ore_filter(ore, target, scl, threshold):
    return {"class": "ore", "ore": ore, "target": target, "scl": float(scl), "threshold": threshold,
            "octaves": OCTAVES, "falloff": FALLOFF}


def build_filters(mod_blocks):
    """The genfilters list, with content names as the generator spells them (no mod prefix).

    Order matters because a later filter overwrites an earlier one on the same tile, and because of how
    the game reads unknown names: without the mod, every mod block name becomes "air". A mod-ore
    filter then erases ore instead of placing it, so all filters that place mod content run first,
    before any vanilla ore exists. Targets are always vanilla floors except for mod ores, so no
    vanilla filter can turn into a map-wide one."""
    crystal = [{"class": "noise", "floor": CRYSTAL, "block": "air", "target": host, "scl": float(scl),
                "threshold": thr, "octaves": OCTAVES, "falloff": FALLOFF} for host, scl, thr in CRYSTAL_HOSTS]
    wide = [ore_filter(ore, "air", scl, thr) for ore, scl, thr in WIDESPREAD]
    lean = [ore_filter(ore, floor, scl, thr) for floor, ore, scl, thr in TENDENCIES]
    mod_first = [f for f in wide + lean if f["ore"] in mod_blocks]
    vanilla = [f for f in wide if f["ore"] not in mod_blocks] + [f for f in lean if f["ore"] not in mod_blocks]
    clear = [ore_filter("air", floor, 1, 0.0) for floor in CLEAR_FLOORS]
    return crystal + mod_first + vanilla + clear


def check_filters(filters, mod_blocks):
    """Problems that would make the filters misbehave in the game (empty list = fine)."""
    problems = []
    vanilla_ore_seen = False
    for k, f in enumerate(filters):
        if f["class"] == "noise":
            if f.get("block") != "air":
                problems.append("filter %d: NoiseFilter must set block to air (the default is stone-wall)" % k)
            if f.get("target", "air") == "air":
                problems.append("filter %d: NoiseFilter without a target would repaint liquids and barriers" % k)
            if f.get("target") in mod_blocks and f.get("floor") not in mod_blocks:
                problems.append("filter %d: vanilla floor on a mod target becomes map-wide without the mod" % k)
            continue
        ore, target = f["ore"], f.get("target", "air")
        if ore in mod_blocks:
            if vanilla_ore_seen:
                problems.append("filter %d: mod ore after vanilla ores (erases them without the mod)" % k)
        else:
            if ore != "air":
                vanilla_ore_seen = True
            if target in mod_blocks:
                problems.append("filter %d: %s on mod floor %s becomes map-wide without the mod" % (k, ore, target))
            if ore == "air" and target == "air":
                problems.append("filter %d: clears ore from the whole map" % k)
    return problems


def to_json(filters, file_name):
    """genfilters tag text. Filter class tags are Strings.camelize(simple name minus "Filter")."""
    out = []
    for f in filters:
        g = dict(f)
        for key in ("ore", "target", "floor", "block"):
            if key in g:
                g[key] = file_name(g[key])
        out.append(g)
    return json.dumps(out, separators=(",", ":"))


# ----------------------------------------------------------------------------------------------
# Port of arc.util.noise.Simplex.noise2d / raw2d (Java doubles == Python floats, int32 wrap emulated)
# ----------------------------------------------------------------------------------------------

_GRAD3 = ((1, 1), (-1, 1), (1, -1), (-1, -1), (1, 0), (-1, 0), (1, 0), (-1, 0),
          (0, 1), (0, -1), (0, 1), (0, -1))     # (x, y) of Simplex.grad3
_F2 = 0.5 * (math.sqrt(3.0) - 1.0)
_G2 = (3.0 - math.sqrt(3.0)) / 6.0


def f32(value):
    """Round a Python float to the nearest Java float."""
    return struct.unpack(">f", struct.pack(">f", value))[0]


def perm_table(seed):
    """Simplex.perm(seed, k) for k in 0..511 (perm masks its argument to 0..255 itself)."""
    mult = (0x45d9f3b + seed) & 0xFFFFFFFF
    out = []
    for k in range(512):
        x = ((k & 255) * 0x45d9f3b) & 0xFFFFFFFF
        x = (((x >> 16) ^ x) * mult) & 0xFFFFFFFF
        x = (x >> 16) ^ x
        out.append(x & 0xFF)
    return out


def raw2d(perm, x, y):
    """Simplex.raw2d for one seed's permutation table."""
    s = (x + y) * _F2
    a, b = x + s, y + s
    i = int(a) if a > 0 else int(a) - 1           # Simplex.fastfloor
    j = int(b) if b > 0 else int(b) - 1
    t = (i + j) * _G2
    x0 = x - (i - t)
    y0 = y - (j - t)
    if x0 > y0:
        i1, j1 = 1, 0
    else:
        i1, j1 = 0, 1
    x1 = x0 - i1 + _G2
    y1 = y0 - j1 + _G2
    x2 = x0 - 1.0 + 2.0 * _G2
    y2 = y0 - 1.0 + 2.0 * _G2
    ii = i & 255
    jj = j & 255
    n = 0.0
    t0 = 0.5 - x0 * x0 - y0 * y0
    if t0 >= 0:
        g = _GRAD3[perm[ii + perm[jj]] % 12]
        t0 *= t0
        n = t0 * t0 * (g[0] * x0 + g[1] * y0)
    t1 = 0.5 - x1 * x1 - y1 * y1
    if t1 >= 0:
        g = _GRAD3[perm[ii + i1 + perm[jj + j1]] % 12]
        t1 *= t1
        n += t1 * t1 * (g[0] * x1 + g[1] * y1)
    t2 = 0.5 - x2 * x2 - y2 * y2
    if t2 >= 0:
        g = _GRAD3[perm[ii + 1 + perm[jj + 1]] % 12]
        t2 *= t2
        n += t2 * t2 * (g[0] * x2 + g[1] * y2)
    return 70.0 * n


def noise2d(perm, octaves, persistence, scale, x, y):
    """Simplex.noise2d (before the final cast to float)."""
    total, frequency, amplitude, max_amplitude = 0.0, scale, 1.0, 0.0
    for _ in range(int(math.ceil(octaves))):
        total += (raw2d(perm, x * frequency, y * frequency) + 1.0) / 2.0 * amplitude
        frequency *= 2
        max_amplitude += amplitude
        amplitude *= persistence
    return total / max_amplitude


def hits(f, seed, width, tiles):
    """The tiles where GenerateFilter.noise(x, y, scl, 1, octaves, falloff) > threshold, compared in floats
    like the game does. Only two-octave filters are used. The second octave adds at most `falloff`, so
    it is skipped wherever the first one alone cannot reach the threshold."""
    assert f["octaves"] == 2.0
    thr = f32(f["threshold"])
    if thr <= 0.0:
        return list(tiles)   # the noise is (raw + 1) / 2 >= 0 and equals 0 only at an exact minimum
    perm = perm_table(seed)
    scale = f32(1.0 / f32(f["scl"]))
    p = f32(f["falloff"])
    first_min = 2.0 * ((thr - 1e-6) * (1.0 + p) - p) - 1.0     # smallest useful raw2d of the first octave
    out = []
    for i in tiles:
        x = i % width + 10.0
        y = i // width + 10.0
        first = raw2d(perm, x * scale, y * scale)
        if first < first_min:
            continue
        v = ((first + 1.0) / 2.0 + (raw2d(perm, x * scale * 2, y * scale * 2) + 1.0) / 2.0 * p) / (1.0 + p)
        if v > thr if abs(v - thr) > 1e-6 else f32(v) > thr:
            out.append(i)
    return out


# ----------------------------------------------------------------------------------------------
# Rolling the filters like the game does on load
# ----------------------------------------------------------------------------------------------

def roll(filters, width, floor, overlay, open_tiles, liquid_floors, rng):
    """Applies `filters` with fresh seeds from `rng`. Returns (floor, overlay) as new lists.

    `open_tiles` are the tiles not covered by a solid wall: filters still write under walls in the game,
    but that ore is hidden and never mined, so the preview skips those tiles."""
    floor = list(floor)
    overlay = list(overlay)
    for f in filters:
        seed = rng.randrange(1000000000)                     # GenerateFilter.randomize: Mathf.random(999999999)
        target = f.get("target", "air")
        if f["class"] == "noise":
            tiles = [i for i in open_tiles if target == "air" or floor[i] == target]
            for i in hits(f, seed, width, tiles):
                floor[i] = f["floor"]
            continue
        put = None if f["ore"] == "air" else f["ore"]
        tiles = [i for i in open_tiles
                 if floor[i] not in liquid_floors and overlay[i] != "spawn"          # Floor.hasSurface, spawn guard
                 and (target == "air" or floor[i] == target or overlay[i] == target)]
        for i in hits(f, seed, width, tiles):
            overlay[i] = put
    return floor, overlay


def patches(width, height, layer, values, min_size=6):
    """Connected 4-way components of equal values in `layer` -> list of (value, first tile, size)."""
    total = width * height
    seen = bytearray(total)
    out = []
    for s in range(total):
        v = layer[s]
        if v not in values or seen[s]:
            continue
        seen[s] = 1
        q = deque([s])
        size = 0
        while q:
            i = q.popleft()
            size += 1
            x = i % width
            for j in (i - 1 if x > 0 else -1, i + 1 if x < width - 1 else -1, i - width, i + width):
                if 0 <= j < total and not seen[j] and layer[j] == v:
                    seen[j] = 1
                    q.append(j)
        if size >= min_size:
            out.append((v, s, size))
    return out


def measure(width, height, floor, overlay, region_of, region_names):
    """Ore tiles and patches per region for one roll."""
    tiles = {}
    for i, o in enumerate(overlay):
        if o and o != "spawn":
            reg = region_names[region_of[i]]
            tiles.setdefault(reg, {}).setdefault(o, 0)
            tiles[reg][o] += 1
        elif floor[i] == CRYSTAL:
            reg = region_names[region_of[i]]
            tiles.setdefault(reg, {}).setdefault(CRYSTAL, 0)
            tiles[reg][CRYSTAL] += 1
    kinds = {o for o in overlay if o and o != "spawn"}
    found = patches(width, height, overlay, kinds) + patches(width, height, floor, {CRYSTAL})
    count = {}
    for value, first, size in found:
        reg = region_names[region_of[first]]
        count.setdefault(reg, {}).setdefault(value, 0)
        count[reg][value] += 1
    sizes = sorted(size for _, _, size in found)
    return tiles, count, sizes


def roll_seeds(seed, rolls):
    """One random generator per previewed roll; the game itself uses a new seed on every load."""
    return [random.Random("ore-roll-%d-%d" % (seed, k)) for k in range(rolls)]
