#!/usr/bin/env python3
"""Biomes Extended Remastered - procedural generator for a Mindustry PvE map.

Target: Mindustry v8 Build 159.7 (save format 13) with the "Exogenesis Old" mod (exogenesisold 1.9.1).
Only the Python standard library is used (Python 3.8+).

    python generate_map.py                        # default seed, writes to the "maps" folder next to this file
    python generate_map.py --seed 7 --out ./out   # another variation in another folder

Outputs: the .msav map, a top-down preview PNG, an enemy-routes PNG and a JSON report with the
measured statistics (biome areas, ore tiles, routes, choke points, wave curve).

Ore nodes are not part of the terrain written here: the map carries ore filters (see ores.py) that the
game re-rolls every time the map is loaded. The preview and the report show simulated rolls.
"""

import argparse
import heapq
import json
import math
import os
import random
import struct
import time
import zlib
from array import array
from collections import deque

import msav
import ores
import waves

MAP_NAME = "Biomes Extended Remastered"
MAP_AUTHOR = "DecONagi"
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maps")
DEFAULT_SEED = 1597

W = H = 800
N = W * H
CX = CY = 400
DEG = math.pi / 180.0

DESERT, SEMIARID, FROZEN, FOREST, VOLCANO, BASIN = range(6)
BIOME_NAMES = ("Desert (E)", "Semi-arid (NE)", "Frozen (N)", "Forest (W)", "Volcano (SW)", "Crossroads Basin")

# Biome borders (degrees counter-clockwise from east; +y is north) and the biome on each side.
BOUNDS = (22.0, 68.0, 135.0, 205.0, 285.0)
SIDES = ((DESERT, SEMIARID), (SEMIARID, FROZEN), (FROZEN, FOREST), (FOREST, VOLCANO), (VOLCANO, DESERT))

SPAWNS = {
    "frozen": (420, 778),
    "semiarid": (730, 730),
    "desert": (778, 352),
    "forest": (22, 450),
    "volcano": (68, 68),
}
SPAWN_LABELS = {"frozen": "North spawn (Frozen)", "semiarid": "North-east spawn (Semi-arid)",
                "desert": "East spawn (Desert)", "forest": "West spawn (Forest)",
                "volcano": "South-west spawn (Volcano)"}
GATES = {"East Gate": 0.0, "North-east Gate": 45.0, "North Gate": 92.0, "West Gate": 178.0, "South-west Gate": 238.0}

# Separator ridges: they follow the (warped) biome border and are 13-19 tiles thick,
# which also stops legged units (Tile.legSolid needs 3+ tiles of rock depth).
RIDGES = (
    {"name": "Salt Escarpment", "angle": 22.0, "r0": 92, "r1": 470, "passes": ((165, 8, "Salt Gap"),)},
    {"name": "Rime Bluffs", "angle": 68.0, "r0": 92, "r1": 300, "passes": ((175, 9, "Rime Pass"),)},
    {"name": "Taiga Wall", "angle": 135.0, "r0": 92, "r1": 345, "passes": ((150, 8, "Taiga Pass"),)},
    {"name": "Ashwood Ridge", "angle": 205.0, "r0": 92, "r1": 470, "passes": ((180, 9, "Cinder Pass"),)},
    {"name": "Obsidian Wall", "angle": 285.0, "r0": 92, "r1": 470,
     "passes": ((150, 8, "Obsidian Gate"), (290, 8, "Far Obsidian Gate"))},
)

VOLCANO_CENTER = (230, 185)
LAVA_RIVER_WEST = [(230, 185), (196, 172), (160, 158), (122, 146), (84, 137), (44, 128), (0, 120), (-14, 118)]
LAVA_RIVER_SOUTH = [(230, 185), (238, 150), (229, 112), (243, 72), (236, 34), (240, -14)]
BASALT_BRIDGES = {"West Basalt Bridge": (103, 141), "South Basalt Bridge": (236, 92)}
PYRO_CREEKS = ([(262, 214), (284, 240), (302, 266), (316, 296), (322, 320)],
               [(272, 176), (300, 170), (330, 182), (352, 200)])
LAVA_POOLS = ((175, 245, 7), (330, 135, 8), (122, 62, 6), (180, 95, 7))

FOREST_RIVER = [(235, 655), (215, 625), (192, 590), (168, 545), (178, 498), (155, 452), (168, 405),
                (150, 360), (162, 318), (158, 280), (148, 245), (138, 212)]
FORDS = {"North Ford": (176, 500), "South Ford": (166, 408)}
MIRROR_LAKE = (148, 360, 19)
SPORE_HOLLOW = (90, 585, 58)

CRYO_RING_R = 268
FROST_BRIDGES = {"Frost Bridge East": 87.0, "Frost Bridge West": 114.0}

MESA_CANYONS = {"Red Canyon": 45.0, "Dust Canyon": 60.0}
OASIS = (36.0, 330)

DUNE_GAPS = {"Tar Narrows": (398, 7), "Salt Pass": (205, 6), "Southern Breach": (62, 5)}
TAR_FIELDS = ((640, 428, 11), (655, 445, 9), (628, 447, 8), (662, 425, 8), (646, 462, 7),
              (640, 368, 11), (656, 352, 9), (626, 350, 8), (662, 372, 8), (648, 334, 7))
BLACK_LAKE = (532, 300, 15)
WRECK_FIELD = (706, 205, 36)
SALT_PAN = (640, 120, 50)

OUTPOSTS = (  # name, biome, nominal centre of a 7x7 core-zone pad
    ("Rimeward Outpost", FROZEN, (361, 568)),
    ("Siratla Outpost", FROZEN, (213, 699)),
    ("Steppe Outpost", SEMIARID, (495, 526)),
    ("Oasis Outpost", SEMIARID, (655, 647)),
    ("Dunewatch Outpost", DESERT, (556, 337)),
    ("Wreckage Outpost", DESERT, (688, 262)),
    ("Riverbank Outpost", FOREST, (232, 436)),
    ("Sporewood Outpost", FOREST, (112, 520)),
    ("Ember Outpost", VOLCANO, (306, 261)),
    ("Ashfall Outpost", VOLCANO, (358, 103)),
)

LIQUID_FLOORS = {"deep-water", "shallow-water", "sand-water", "darksand-water", "tar", "pooled-cryofluid",
                 "molten-slag", "pyromagma"}
DEEP_FLOORS = {"deep-water", "tar", "pooled-cryofluid", "molten-slag"}
NO_DECOR_FLOORS = LIQUID_FLOORS | {"glowingvein", "siratla-crystal", "core-zone", "metal-floor",
                                   "metal-floor-damaged", "dark-panel-1", "dark-panel-2", "dark-panel-3",
                                   "dark-panel-4", "dark-panel-5", "dark-panel-6"}
NON_SOLID_BLOCKS = {"boulder", "snow-boulder", "sand-boulder", "dacite-boulder", "basalt-boulder",
                    "shale-boulder", "spore-cluster", "siratla-stone-boulder"}
NATURAL_WALL = {
    "stone": "stone-wall", "crater-stone": "stone-wall", "char": "dune-wall", "basalt": "dune-wall",
    "hotrock": "dune-wall", "magmarock": "dune-wall", "sand-floor": "sand-wall", "darksand": "dune-wall",
    "salt": "salt-wall", "shale": "shale-wall", "dirt": "dirt-wall", "mud": "dirt-wall", "grass": "dirt-wall",
    "moss": "stone-wall", "spore-moss": "spore-wall", "dacite": "dacite-wall", "snow": "snow-wall",
    "ice-snow": "snow-wall", "ice": "ice-wall", "siratla-stone": "siratla-stone-wall",
    "metal-floor-damaged": "dark-metal",
}
BIOME_FLOOR = {DESERT: "sand-floor", SEMIARID: "dirt", FROZEN: "snow", FOREST: "grass", VOLCANO: "basalt",
               BASIN: "stone"}
BOULDERS = {DESERT: "sand-boulder", SEMIARID: "dacite-boulder", FROZEN: "snow-boulder", FOREST: "boulder",
            VOLCANO: "basalt-boulder", BASIN: "boulder"}

# Exogenesis Old terrain. Mod content is registered as "<mod name>-<file name>", so these are written
# to the map with the prefix (ContentLoader.getByName does no prefixing of its own).
MOD_BLOCKS = {"pyromagma", "siratla-stone", "siratla-stone-wall", "siratla-crystal", "glowingvein",
              "siratla-stone-boulder", "ore-dytrix", "ore-siradamite", "ore-stellar-steel", "ore-urbium"}
MOD_PREFIX = "exogenesisold-"


def file_block_name(name):
    return MOD_PREFIX + name if name in MOD_BLOCKS else name


# Lava: floors drawn as lava, and Attribute.heat per floor (Blocks.java @ v159.7; Exogenesis Old 1.9.1
# gives none of its floors on this map any heat). Thermal generators need heat > 0 under their 2x2.
LAVA_FLOORS = {"molten-slag", "pyromagma"}
FLOOR_HEAT = {"molten-slag": 0.85, "magmarock": 0.75, "hotrock": 0.5}

# Map data patches (embedded in the save, applied by the game only while the map is loaded).
# 1. The thermal generator is already `floating`, but Build.validPlace also wants it to touch non-deep
#    ground (contactsShallows), so it only fit along the banks of the molten slag. `placeableLiquid`
#    lifts that rule. Only heat floors pass ThermalGenerator.canPlaceOn, so this opens up lava and
#    nothing else.
# 2. Exogenesis' pyromagma (the creeks) is drawn as lava but has no heat at all, so no thermal generator
#    could stand on it. It gets the heat of molten slag. This is a separate asset with a dotted path:
#    without the mod the path does not resolve, and the game only logs a warning for it.
DATA_PATCHES = (
    ("thermal-generators-on-lava.json", json.dumps({
        "name": "Thermal generators on lava",
        "block": {"thermal-generator": {"placeableLiquid": True}},
    })),
    ("pyromagma-heat.json", json.dumps({
        "name": "Pyromagma gives heat",
        "block.%s.attributes.heat" % file_block_name("pyromagma"): FLOOR_HEAT["molten-slag"],
    })),
)


# ----------------------------------------------------------------------------------------------
# Noise
# ----------------------------------------------------------------------------------------------

def smooth(t):
    return t * t * (3.0 - 2.0 * t)


def value_noise(seed, sx, sy):
    """Smooth value noise over the whole grid, computed row-wise for speed."""
    rng = random.Random(seed)
    ox, oy = rng.uniform(0, 1000), rng.uniform(0, 1000)
    x0, y0 = int(ox / sx), int(oy / sy)
    gw = int((W - 1 + ox) / sx) - x0 + 2
    gh = int((H - 1 + oy) / sy) - y0 + 2
    lattice = [[rng.random() for _ in range(gw)] for _ in range(gh)]
    xi, xt = [], []
    for x in range(W):
        f = (x + ox) / sx
        k = int(f)
        xi.append(k - x0)
        xt.append(smooth(f - k))
    rows = [[row[k] + (row[k + 1] - row[k]) * t for k, t in zip(xi, xt)] for row in lattice]
    out = []
    for y in range(H):
        f = (y + oy) / sy
        k = int(f)
        t = smooth(f - k)
        a, b = rows[k - y0], rows[k - y0 + 1]
        out.extend([p + (q - p) * t for p, q in zip(a, b)])
    return out


def uniformize(values):
    """Rank-normalise to a uniform [0, 1] distribution so thresholds read as coverage fractions."""
    order = sorted(range(N), key=values.__getitem__)
    out = array("f", bytes(4 * N))
    step = 1.0 / (N - 1)
    for rank, i in enumerate(order):
        out[i] = rank * step
    return out


def fbm(seed, scale, octaves=3, stretch_y=1.0):
    total = None
    amp = 1.0
    for o in range(octaves):
        s = max(scale / (2 ** o), 2.0)
        layer = value_noise(seed * 1009 + o * 7919, s, s * stretch_y)
        total = [v * amp for v in layer] if total is None else [t + v * amp for t, v in zip(total, layer)]
        amp *= 0.5
    return uniformize(total)


class Noise1D:
    def __init__(self, seed, scale):
        rng = random.Random(seed)
        self.values = [rng.random() for _ in range(4096)]
        self.scale = scale

    def __call__(self, t):
        f = t / self.scale
        k = int(math.floor(f))
        u = smooth(f - k)
        a = self.values[k % 4096]
        b = self.values[(k + 1) % 4096]
        return a + (b - a) * u


# ----------------------------------------------------------------------------------------------
# Geometry helpers
# ----------------------------------------------------------------------------------------------

def polar(angle, r):
    return int(round(CX + r * math.cos(angle * DEG))), int(round(CY + r * math.sin(angle * DEG)))


def angdiff(a, b):
    return (a - b + 180.0) % 360.0 - 180.0


def sector(angle):
    if 22.0 <= angle < 68.0:
        return SEMIARID
    if 68.0 <= angle < 135.0:
        return FROZEN
    if 135.0 <= angle < 205.0:
        return FOREST
    if 205.0 <= angle < 285.0:
        return VOLCANO
    return DESERT


def disc(cx, cy, rad):
    """(index, distance) for every tile within `rad` of (cx, cy)."""
    x0, x1 = max(0, int(cx - rad) - 1), min(W - 1, int(cx + rad) + 1)
    y0, y1 = max(0, int(cy - rad) - 1), min(H - 1, int(cy + rad) + 1)
    r2 = rad * rad
    for y in range(y0, y1 + 1):
        dy = y - cy
        base = y * W
        for x in range(x0, x1 + 1):
            dx = x - cx
            dd = dx * dx + dy * dy
            if dd <= r2:
                yield base + x, math.sqrt(dd)


def catmull_rom(points, step=1.5):
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for k in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[k - 1], pts[k], pts[k + 1], pts[k + 2]
        n = max(2, int(math.dist(p1, p2) / step))
        for s in range(n):
            t = s / n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * p1[c] + (-p0[c] + p2[c]) * t + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * t2
                                    + (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c]) * t3) for c in (0, 1)))
    out.append(tuple(points[-1]))
    return out


def meander(dense, amplitude, scale, seed):
    if amplitude <= 0:
        return dense
    noise = Noise1D(seed, scale)
    out = []
    length = 0.0
    for k, (x, y) in enumerate(dense):
        a = dense[max(0, k - 1)]
        b = dense[min(len(dense) - 1, k + 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        norm = math.hypot(tx, ty) or 1.0
        if k:
            length += math.dist(dense[k - 1], dense[k])
        off = amplitude * (noise(length) - 0.5) * 2.0
        out.append((x - ty / norm * off, y + tx / norm * off))
    return out


def crossing(field, dense, nominal, along):
    """River tiles within `along` tiles (measured along the flow) of the centreline point nearest `nominal`.
    Used for bridges and fords so they always span the whole meandering channel."""
    k = min(range(len(dense)), key=lambda j: (dense[j][0] - nominal[0]) ** 2 + (dense[j][1] - nominal[1]) ** 2)
    cx, cy = dense[k]
    a, b = dense[max(0, k - 3)], dense[min(len(dense) - 1, k + 3)]
    tx, ty = b[0] - a[0], b[1] - a[1]
    norm = math.hypot(tx, ty) or 1.0
    tx, ty = tx / norm, ty / norm
    tiles = [i for i, d in disc(cx, cy, along + 18.0)
             if i in field and abs((i % W - cx) * tx + (i // W - cy) * ty) <= along]
    return (int(round(cx)), int(round(cy))), tiles


def polyline_field(points, maxd, amplitude=0.0, scale=40.0, seed=0):
    """({tile index: distance to the smoothed, optionally meandering polyline}, dense centreline)."""
    dense = meander(catmull_rom(points), amplitude, scale, seed)
    field = {}
    for k in range(len(dense) - 1):
        ax, ay = dense[k]
        bx, by = dense[k + 1]
        vx, vy = bx - ax, by - ay
        l2 = vx * vx + vy * vy or 1e-9
        x0, x1 = max(0, int(min(ax, bx) - maxd)), min(W - 1, int(max(ax, bx) + maxd) + 1)
        y0, y1 = max(0, int(min(ay, by) - maxd)), min(H - 1, int(max(ay, by) + maxd) + 1)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                t = ((x - ax) * vx + (y - ay) * vy) / l2
                t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
                dx, dy = x - (ax + vx * t), y - (ay + vy * t)
                d = math.sqrt(dx * dx + dy * dy)
                if d <= maxd:
                    i = y * W + x
                    old = field.get(i)
                    if old is None or d < old:
                        field[i] = d
    return field, dense


# ----------------------------------------------------------------------------------------------
# Map builder
# ----------------------------------------------------------------------------------------------

class MapBuilder:
    def __init__(self, seed, ore_rolls=1):
        self.seed = seed
        self.ore_rolls = ore_rolls
        self.rng = random.Random(seed)
        self.floor = ["stone"] * N
        self.ore = [None] * N      # overlays written to the map: spawn markers only (ores come from filters)
        self.wall = [None] * N
        self.prot = bytearray(N)   # 0 free, 1 liquid/bank feature, 2 forced open, 3 structural wall
        self.keep = bytearray(N)   # 1 = keep free of natural walls and decorations
        self.lava_core = set()
        self.markers = {}          # named choke points: name -> (x, y)
        self.pads = []
        self.notes = []

    # -- setup -----------------------------------------------------------------------------------

    def build_noise(self):
        s = self.seed
        self.wA = fbm(s + 1, 190, 3)
        self.wB = fbm(s + 2, 55, 3)
        self.n1 = fbm(s + 3, 42, 3)
        self.n2 = fbm(s + 4, 13, 2)
        self.n3 = fbm(s + 5, 100, 3)
        self.blend = fbm(s + 6, 7, 2)
        self.rimN = fbm(s + 7, 28, 2)
        self.thick = fbm(s + 8, 36, 3)
        self.rock = fbm(s + 9, 30, 4)
        self.grove = fbm(s + 10, 15, 3)
        self.mesa = fbm(s + 11, 46, 4)
        self.dune = fbm(s + 12, 16, 3, stretch_y=4.0)
        self.vein = fbm(s + 13, 38, 3)
        self.fine = fbm(s + 14, 4, 1)
        self.edge = fbm(s + 15, 24, 2)

    def build_polar(self):
        self.R = array("f", bytes(4 * N))
        self.T = array("f", bytes(4 * N))
        i = 0
        for y in range(H):
            dy = y - CY
            for x in range(W):
                dx = x - CX
                self.R[i] = math.hypot(dx, dy)
                self.T[i] = math.degrees(math.atan2(dy, dx)) % 360.0
                i += 1

    def warp(self, i):
        return 9.0 * (self.wA[i] - 0.5) + 3.0 * (self.wB[i] - 0.5)

    def build_biomes(self):
        """CB = sector biome on the warped angle, BI = dithered biome used for floors."""
        self.TW = array("f", bytes(4 * N))
        self.ARC = array("f", bytes(4 * N))
        self.NB = bytearray(N)
        self.CB = bytearray(N)
        self.BI = bytearray(N)
        self.BAND = array("f", bytes(4 * N))
        R, T = self.R, self.T
        for i in range(N):
            r = R[i]
            tw = (T[i] + self.warp(i)) % 360.0
            best, nb = 999.0, 0
            for k, ba in enumerate(BOUNDS):
                d = abs((tw - ba + 180.0) % 360.0 - 180.0)
                if d < best:
                    best, nb = d, k
            arc = best * DEG * r
            cb = sector(tw)
            band = 9.0 + 14.0 * self.n3[i]
            b = cb
            if arc < band and r > 75.0 and self.blend[i] < 0.5 * (1.0 - arc / band):
                lo, hi = SIDES[nb]
                b = hi if cb == lo else lo
            if r < 60.0 + 10.0 * (self.rimN[i] - 0.5):
                b = BASIN
            self.TW[i], self.ARC[i], self.NB[i], self.CB[i], self.BI[i], self.BAND[i] = tw, arc, nb, cb, b, band

    def glacier(self, i):
        return self.CB[i] == FROZEN and self.R[i] > 305.0 + 30.0 * (self.n3[i] - 0.5)

    # -- floors ----------------------------------------------------------------------------------

    def palette(self, b, i, r):
        a, c, d = self.n1[i], self.n2[i], self.n3[i]
        if b == BASIN:
            if d > 0.83:
                return "darksand"
            if a > 0.74:
                return "grass"
            if c > 0.82:
                return "dirt"
            if a < 0.10:
                return "crater-stone"
            return "stone"
        if b == DESERT:
            if d < 0.13 and r > 230:
                return "salt"
            if c > 0.88 and a > 0.35:
                return "shale"
            if a > 0.78:
                return "darksand"
            return "sand-floor"
        if b == SEMIARID:
            if d > 0.86 and c > 0.45:
                return "shale"
            if d < 0.12:
                return "salt"
            if a > 0.66:
                return "dacite"
            if c > 0.84:
                return "darksand"
            if c < 0.10 and a < 0.5:
                return "grass"
            return "dirt"
        if b == FROZEN:
            if self.glacier(i):
                if a > 0.82:
                    return "ice"
                if a < 0.62:
                    return "siratla-stone"
                return "ice-snow"
            if a > 0.80:
                return "ice"
            if a > 0.56:
                return "ice-snow"
            return "snow"
        if b == FOREST:
            if a > 0.64:
                return "moss"
            if c > 0.85:
                return "dirt"
            if d < 0.14 and c > 0.45:
                return "mud"
            return "grass"
        # volcano
        vx, vy = VOLCANO_CENTER
        x, y = i % W, i // W
        hot = math.hypot(x - vx, y - vy) < 85.0
        if d < 0.15:
            return "crater-stone"
        if c > (0.92 if hot else 0.965):
            return "magmarock"
        if c > (0.75 if hot else 0.89):
            return "hotrock"
        if a > 0.72:
            return "char"
        return "basalt"

    def paint_floors(self):
        R = self.R
        for i in range(N):
            r = R[i]
            b = self.BI[i]
            fl = self.palette(b, i, r)
            if b != BASIN:
                # ring road: the basin's ground leaks out through the gates
                if r < 100.0 and self.blend[i] < (100.0 - r) / 35.0 * 0.7:
                    fl = self.palette(BASIN, i, r)
                arc, band = self.ARC[i], self.BAND[i] * 1.3
                if arc < band:
                    t = 1.0 - arc / band
                    bound = BOUNDS[self.NB[i]]
                    c = self.n2[i]
                    if bound == 205.0 and b == FOREST and c < 0.75 * t:
                        fl = "char"                      # Ashwood: burnt forest floor
                    elif bound == 68.0 and b == SEMIARID and c < 0.6 * t:
                        fl = "ice-snow" if self.n1[i] > 0.5 else "snow"   # tundra steppe
                    elif bound == 68.0 and b == FROZEN and c < 0.4 * t:
                        fl = "dirt"
                    elif bound == 285.0 and c < 0.6 * t:
                        fl = "darksand"                  # ash dunes
                    elif bound == 22.0 and c < 0.5 * t:
                        fl = "salt"                      # salt escarpment
                    elif bound == 135.0 and b == FOREST and c < 0.5 * t:
                        fl = "snow"                      # taiga
                    elif bound == 135.0 and b == FROZEN and c < 0.35 * t:
                        fl = "grass"
            self.floor[i] = fl

    # -- liquid and special-floor features -------------------------------------------------------

    def set_floor(self, i, fl, prot=None):
        self.floor[i] = fl
        if prot is not None and self.prot[i] < prot:
            self.prot[i] = prot

    def volcano_features(self):
        for pts, seed in ((LAVA_RIVER_WEST, 11), (LAVA_RIVER_SOUTH, 12)):
            field, dense = polyline_field(pts, 12.0, amplitude=5.0, scale=35.0, seed=self.seed + seed)
            for i, d in field.items():
                wc = 3.2 + 2.0 * self.n1[i]
                if d <= wc:
                    self.set_floor(i, "molten-slag", 1)
                    self.lava_core.add(i)
                elif d <= wc + 2.5:
                    if self.floor[i] not in LIQUID_FLOORS:
                        self.set_floor(i, "magmarock", 1)
                elif d <= wc + 5.0 and self.floor[i] not in LIQUID_FLOORS:
                    self.set_floor(i, "hotrock", 1)
            for name, nominal in BASALT_BRIDGES.items():
                centre, tiles = crossing(field, dense, nominal, 7.0)
                if math.dist(centre, nominal) > 30:
                    continue
                self.markers[name] = centre
                for i in tiles:
                    if field[i] <= 3.2 + 2.0 * self.n1[i] + 5.0:
                        self.set_floor(i, "basalt" if field[i] <= 3.2 + 2.0 * self.n1[i] + 2.5 else "hotrock")
                        self.prot[i] = 2
                        self.keep[i] = 1
                        self.lava_core.discard(i)
        for k, pts in enumerate(PYRO_CREEKS):
            field, _ = polyline_field(pts, 6.0, amplitude=3.0, scale=20.0, seed=self.seed + 20 + k)
            for i, d in field.items():
                if self.floor[i] in DEEP_FLOORS:
                    continue
                if d <= 2.2:
                    self.set_floor(i, "pyromagma", 1)
                elif d <= 4.5:
                    self.set_floor(i, "hotrock", 1)
        for (px, py, pr) in LAVA_POOLS:
            for i, d in disc(px, py, pr + 3.5):
                if d < pr - 2:
                    self.set_floor(i, "molten-slag", 1)
                elif d < pr + 1.5:
                    self.set_floor(i, "magmarock", 1)
                elif self.floor[i] not in LIQUID_FLOORS:
                    self.set_floor(i, "hotrock", 1)

    def forest_features(self):
        field, dense = polyline_field(FOREST_RIVER, 16.0, amplitude=7.0, scale=40.0, seed=self.seed + 30)
        lx, ly, lr = MIRROR_LAKE
        lake = {i: d - (lr + 3.0 * (self.n3[i] - 0.5)) for i, d in disc(lx, ly, lr + 8)}
        for i in set(field) | set(lake):
            if self.CB[i] != FOREST:
                continue
            d = field.get(i, 99.0) - (4.5 + 2.0 * self.n1[i])   # signed distance to the river channel
            s = min(d, lake.get(i, 99.0) + 2.0)
            if s <= 0.0:
                fl = "deep-water"
            elif s <= 3.0:
                fl = "shallow-water"
            elif s <= 5.5:
                fl = "sand-water" if self.n2[i] > 0.45 else "darksand-water"
            elif s <= 9.0:
                if self.floor[i] not in LIQUID_FLOORS:
                    self.set_floor(i, "darksand" if self.n2[i] > 0.55 else "mud")
                continue
            else:
                continue
            self.set_floor(i, fl, 1)
        for name, nominal in FORDS.items():
            centre, tiles = crossing(field, dense, nominal, 8.5)
            self.markers[name] = centre
            for i, d in disc(centre[0], centre[1], 16.0):
                self.keep[i] = 1
            for i in tiles:
                if self.floor[i] == "deep-water":
                    self.set_floor(i, "shallow-water")
                    self.prot[i] = 2
        sx, sy, sr = SPORE_HOLLOW
        self.spore_zone = set()
        for i, d in disc(sx, sy, sr):
            if self.CB[i] != FOREST or self.prot[i] or self.floor[i] in LIQUID_FLOORS:
                continue
            if d < sr * (0.72 + 0.28 * self.n3[i]):
                self.floor[i] = "spore-moss" if self.n2[i] > 0.3 else "moss"
                self.spore_zone.add(i)

    def frozen_features(self):
        lakes = {}
        noise = Noise1D(self.seed + 40, 9.0)
        a = 58.0
        while a <= 145.0:
            rr = CRYO_RING_R + 10.0 * (noise(a) - 0.5)
            rad = 17.0 + 7.0 * noise(a + 500.0)
            cx, cy = CX + rr * math.cos(a * DEG), CY + rr * math.sin(a * DEG)
            for i, d in disc(cx, cy, rad + 4.0):
                s = d - rad
                if s < lakes.get(i, 99.0):
                    lakes[i] = s
            a += 3.0
        for i, s in lakes.items():
            if self.CB[i] != FROZEN:
                continue
            if s < -3.5:
                self.set_floor(i, "pooled-cryofluid", 1)
            elif s < 0.0:
                self.set_floor(i, "ice", 1)
            elif s < 3.0 and self.floor[i] not in LIQUID_FLOORS:
                self.set_floor(i, "ice-snow")
        for name, ang in FROST_BRIDGES.items():
            self.markers[name] = polar(ang, CRYO_RING_R)
            for i in self.ring_slice(ang, 6.0, CRYO_RING_R - 45, CRYO_RING_R + 45):
                if self.CB[i] == FROZEN and (self.prot[i] == 1 or i in lakes):
                    self.set_floor(i, "ice")
                    self.prot[i] = 2
                    self.keep[i] = 1
        for i in range(N):
            if self.glacier(i) and not self.prot[i] and self.floor[i] not in LIQUID_FLOORS:
                if 1.0 - abs(2.0 * self.vein[i] - 1.0) > 0.972:
                    self.floor[i] = "glowingvein"

    def ring_slice(self, angle, half_width, r0, r1):
        """Tiles whose arc distance to the ray at `angle` is below half_width, between radii r0 and r1."""
        rm = (r0 + r1) / 2.0
        cx, cy = CX + rm * math.cos(angle * DEG), CY + rm * math.sin(angle * DEG)
        out = set()
        for i, d in disc(cx, cy, (r1 - r0) / 2.0 + half_width + 2.0):
            r = self.R[i]
            if r0 <= r <= r1 and abs(angdiff(self.T[i], angle)) * DEG * r <= half_width:
                out.add(i)
        return out

    def semiarid_features(self):
        ox, oy = polar(*OASIS)
        for i, d in disc(ox, oy, 18.0):
            if d < 4.5:
                self.set_floor(i, "deep-water", 1)
            elif d < 8.5:
                self.set_floor(i, "shallow-water", 1)
            elif d < 11.0:
                self.set_floor(i, "sand-water", 1)
            elif d < 17.0:
                self.set_floor(i, "grass" if self.n2[i] > 0.35 else "moss")
                if d > 13.0 and self.blend[i] > 0.82:
                    self.wall[i] = "shrubs"
        self.markers["Last Oasis"] = (ox, oy)

    def desert_features(self):
        tar = {}
        for (tx, ty, tr) in TAR_FIELDS + (BLACK_LAKE,):
            for i, d in disc(tx, ty, tr + 6.0):
                s = d - tr * (0.85 + 0.3 * self.fine[i])
                if s < tar.get(i, 99.0):
                    tar[i] = s
        for i, s in tar.items():
            if self.CB[i] != DESERT:
                continue
            if s < -1.5:
                self.set_floor(i, "tar", 1)
            elif s < 4.0 and self.floor[i] not in LIQUID_FLOORS:
                self.set_floor(i, "shale", 1 if s < 1.0 else None)
        wx, wy, wr = WRECK_FIELD
        self.wreck_zone = set()
        for i, d in disc(wx, wy, wr):
            if self.CB[i] != DESERT or self.prot[i]:
                continue
            if d < wr * (0.7 + 0.3 * self.n3[i]):
                c = self.n2[i]
                if c > 0.55:
                    self.floor[i] = "metal-floor-damaged"
                elif c > 0.42:
                    self.floor[i] = "dark-panel-%d" % (1 + int(self.fine[i] * 5.99))
                else:
                    self.floor[i] = "darksand"
                self.wreck_zone.add(i)
        px, py, pr = SALT_PAN
        for i, d in disc(px, py, pr):
            if self.CB[i] == DESERT and not self.prot[i] and d < pr * (0.75 + 0.25 * self.n3[i]):
                if self.floor[i] not in LIQUID_FLOORS:
                    self.floor[i] = "salt"
        for name, (gy, _) in DUNE_GAPS.items():
            self.markers[name] = (int(round(self.dune_x(gy))), gy)

    # -- walls -----------------------------------------------------------------------------------

    def keep_clear(self):
        for (sx, sy) in SPAWNS.values():
            for i, d in disc(sx, sy, 24.0):
                self.keep[i] = 1
        for i, d in disc(400.5, 400.5, 14.0):
            self.keep[i] = 1

    def natural_walls(self):
        R = self.R
        for i in range(N):
            if self.wall[i] is not None or self.prot[i] or self.keep[i] or R[i] < 105.0:
                continue
            fl = self.floor[i]
            if fl in LIQUID_FLOORS:
                continue
            b = self.BI[i]
            rock = self.rock[i]
            g = self.grove[i]
            w = None
            bound = BOUNDS[self.NB[i]]
            in_band = self.ARC[i] < self.BAND[i] * 1.4
            if in_band and bound == 135.0 and g > 0.79:
                w = "snow-pine" if fl in ("snow", "ice-snow", "ice") else "pine"
            elif in_band and bound == 205.0 and g > 0.90 and self.blend[i] > 0.6:
                w = "white-tree-dead"
            elif b == VOLCANO:
                if rock > 0.90:
                    w = NATURAL_WALL.get(fl, "dune-wall")
            elif b == FROZEN:
                if self.glacier(i):
                    if rock > 0.88:
                        w = NATURAL_WALL.get(fl, "ice-wall")
                elif rock > 0.915:
                    w = NATURAL_WALL.get(fl, "snow-wall")
                elif g > 0.94:
                    w = "snow-pine"
            elif b == SEMIARID:
                if self.mesa[i] > 0.885 or rock > 0.955:
                    w = NATURAL_WALL.get(fl, "dirt-wall")
                elif g > 0.97 and fl in ("grass", "dirt"):
                    w = "shrubs"
            elif b == DESERT:
                if i in self.wreck_zone:
                    if rock > 0.9:
                        w = "dark-metal"
                elif self.dune[i] > 0.935 or rock > 0.965:
                    w = NATURAL_WALL.get(fl, "sand-wall")
            elif b == FOREST:
                if g > 0.80:
                    w = "spore-pine" if i in self.spore_zone else "pine"
                elif g > 0.775 and self.blend[i] > 0.5:
                    w = "shrubs"
                elif rock > 0.97:
                    w = NATURAL_WALL.get(fl, "stone-wall")
            if w is not None:
                self.wall[i] = w

    def structural(self, i):
        fl = self.floor[i]
        w = NATURAL_WALL.get(fl, "stone-wall")
        if w in MOD_BLOCKS or w == "dark-metal":
            return "ice-wall" if fl == "siratla-stone" else "stone-wall"
        if w == "spore-wall" or w == "dirt-wall" and self.BI[i] == FOREST:
            return "stone-wall"
        return w

    def put_wall(self, i, wall=None):
        self.wall[i] = wall or self.structural(i)
        self.prot[i] = 3

    def open_tile(self, i):
        if self.wall[i] is not None and self.wall[i] not in NON_SOLID_BLOCKS:
            self.wall[i] = None
        if self.prot[i] != 1:
            self.prot[i] = 2

    def dune_x(self, y):
        if not hasattr(self, "_dune_noise"):
            self._dune_noise = Noise1D(self.seed + 50, 30.0)
        return 600.0 + 20.0 * math.sin(y / 46.0) + 16.0 * (self._dune_noise(y) - 0.5)

    def structural_walls(self):
        R, T = self.R, self.T
        # Twin mesas of the semi-arid steppe with two canyons
        for i in range(N):
            r = R[i]
            if r < 195.0 or r > 290.0 or self.CB[i] != SEMIARID:
                continue
            inner = 212.0 + 14.0 * (self.mesa[i] - 0.5)
            outer = 268.0 + 14.0 * (self.thick[i] - 0.5)
            if inner <= r <= outer:
                a = T[i]
                red = abs(angdiff(a, MESA_CANYONS["Red Canyon"])) * DEG * r
                dust_axis = MESA_CANYONS["Dust Canyon"] + 2.5 * math.sin((r - 212.0) / 9.0)
                dust = abs(angdiff(a, dust_axis)) * DEG * r
                if red < 7.0 or dust < 4.5:
                    self.open_tile(i)
                    self.keep[i] = 1
                else:
                    self.put_wall(i, "dacite-wall" if self.floor[i] == "dacite" else "dirt-wall")
        for name, ang in MESA_CANYONS.items():
            self.markers[name] = polar(ang, 240)
        # Dune wall splitting the desert
        for y in range(H):
            xc = self.dune_x(y)
            gap = any(abs(y - gy) <= hw for (gy, hw) in DUNE_GAPS.values())
            for x in range(max(0, int(xc - 9)), min(W, int(xc + 10))):
                i = y * W + x
                if self.CB[i] != DESERT or R[i] < 120.0:
                    continue
                if abs(x - xc) <= 5.0 + 2.0 * self.thick[i]:
                    if gap:
                        self.open_tile(i)
                        self.keep[i] = 1
                    else:
                        self.put_wall(i, "dune-wall" if self.floor[i] == "darksand" else "sand-wall")
        # Volcano cone around a crater of molten slag; only the lava channels cut through it
        vx, vy = VOLCANO_CENTER
        for i, d in disc(vx, vy, 52.0):
            outer = 41.0 + 9.0 * (self.rock[i] - 0.5)
            if d < 19.0:
                self.set_floor(i, "molten-slag", 1)
                self.wall[i] = None
            elif d < outer:
                if i in self.lava_core:
                    continue
                self.put_wall(i, "dune-wall")
        # Separator ridges
        for i in range(N):
            r = R[i]
            if r < 90.0:
                continue
            for rd in RIDGES:
                if r < rd["r0"] or r > rd["r1"]:
                    continue
                dd = angdiff(self.TW[i], rd["angle"])
                ht = 6.5 + 3.0 * self.thick[i]
                e = min(r - rd["r0"], rd["r1"] - r)
                if e < 12.0:
                    ht *= 0.45 + 0.55 * e / 12.0
                if abs(dd) * DEG * r <= ht:
                    if any(abs(r - pr) <= hw for (pr, hw, _) in rd["passes"]):
                        self.open_tile(i)
                        self.keep[i] = 1
                    else:
                        self.put_wall(i)
                    break
        for rd in RIDGES:
            for (pr, hw, pname) in rd["passes"]:
                self.markers[pname] = self.boundary_point(rd["angle"], pr)
        # Crossroads Rim with five gates
        for i in range(N):
            r = R[i]
            if r < 50.0 or r > 80.0:
                continue
            rin = 60.0 + 10.0 * (self.rimN[i] - 0.5)
            rout = rin + 11.0 + 4.0 * (self.thick[i] - 0.5)
            if rin <= r <= rout:
                gate = any(abs(angdiff(self.T[i], g)) * DEG * r < 8.0 for g in GATES.values())
                if gate:
                    self.open_tile(i)
                    self.keep[i] = 1
                    if self.floor[i] in LIQUID_FLOORS:
                        self.floor[i] = "stone"
                else:
                    self.put_wall(i, "stone-wall")
        for name, g in GATES.items():
            self.markers[name] = polar(g, 66)
        # Map border
        for i in range(N):
            x, y = i % W, i // W
            e = min(x, y, W - 1 - x, H - 1 - y)
            if e < 3.0 + 8.0 * self.edge[i]:
                self.put_wall(i)

    def boundary_point(self, angle, r):
        """Point of the warped biome border at radius r (iterative correction of the warp)."""
        a = angle
        for _ in range(4):
            x, y = polar(a, r)
            x, y = min(W - 1, max(0, x)), min(H - 1, max(0, y))
            a = angle - self.warp(y * W + x)
        return polar(a, r)

    # -- open areas: outpost pads, spawns, core plaza ------------------------------------------

    def place_pads(self):
        for name, biome, (nx, ny) in OUTPOSTS:
            spot = None
            for radius in range(0, 60, 2):
                candidates = [(nx, ny)] if radius == 0 else [
                    (int(nx + radius * math.cos(k * math.pi / 8)), int(ny + radius * math.sin(k * math.pi / 8)))
                    for k in range(16)]
                for (x, y) in candidates:
                    if self.pad_ok(x, y, biome):
                        spot = (x, y)
                        break
                if spot:
                    break
            if spot is None:
                self.notes.append("Could not place %s" % name)
                continue
            x, y = spot
            for dy in range(-6, 7):
                for dx in range(-6, 7):
                    i = (y + dy) * W + (x + dx)
                    self.open_tile(i)
                    self.keep[i] = 1
                    self.ore[i] = None
                    if max(abs(dx), abs(dy)) <= 3:
                        self.floor[i] = "core-zone"
                    elif max(abs(dx), abs(dy)) == 4:
                        self.floor[i] = "dark-panel-3"
            self.pads.append({"name": name, "biome": BIOME_NAMES[biome], "x": x, "y": y})

    def pad_ok(self, x, y, biome):
        if not (12 <= x < W - 12 and 12 <= y < H - 12):
            return False
        if self.CB[y * W + x] != biome:
            return False
        for dy in range(-7, 8):
            for dx in range(-7, 8):
                i = (y + dy) * W + (x + dx)
                if self.prot[i] in (1, 3) or self.floor[i] in LIQUID_FLOORS:
                    return False
        return True

    def clear_spawns_and_core(self):
        for key, (sx, sy) in SPAWNS.items():
            for i, d in disc(sx, sy, 15.0):
                self.open_tile(i)
                if self.floor[i] in DEEP_FLOORS or self.floor[i] in LIQUID_FLOORS:
                    self.floor[i] = BIOME_FLOOR[self.CB[i]]
                    self.prot[i] = 2
            self.ore[sy * W + sx] = "spawn"
        for y in range(392, 410):
            for x in range(392, 410):
                i = y * W + x
                self.open_tile(i)
                self.floor[i] = "dark-panel-4" if x in (392, 409) or y in (392, 409) else "metal-floor"

    # -- resources -------------------------------------------------------------------------------

    def decorate(self):
        rng = random.Random(self.seed + 99)
        for i in range(N):
            if self.wall[i] is not None or self.ore[i] is not None or self.prot[i] or self.keep[i]:
                continue
            if self.floor[i] in NO_DECOR_FLOORS or self.R[i] < 20.0:
                continue
            b = self.BI[i]
            roll = rng.random()
            if i in getattr(self, "spore_zone", ()) and roll < 0.02:
                self.wall[i] = "spore-cluster"
            elif roll < (0.004 if b == BASIN else 0.011):
                self.wall[i] = "siratla-stone-boulder" if self.floor[i] == "siratla-stone" else BOULDERS[b]

    def roll_ores(self):
        """Runs the map's ore filters the way the game does on every load. Nothing here is written to the
        map; the first roll feeds the preview and all rolls feed the report."""
        self.filters = ores.build_filters(MOD_BLOCKS)
        problems = ores.check_filters(self.filters, MOD_BLOCKS)
        assert not problems, problems
        self.region = [BASIN if self.BI[i] == BASIN else self.CB[i] for i in range(N)]
        open_tiles = [i for i in range(N) if self.wall[i] is None or self.wall[i] in NON_SOLID_BLOCKS]
        self.rolls = []
        for rng in ores.roll_seeds(self.seed, self.ore_rolls):
            floor, overlay = ores.roll(self.filters, W, self.floor, self.ore, open_tiles, LIQUID_FLOORS, rng)
            if not self.rolls:
                self.preview_floor, self.preview_ore = floor, overlay
            self.rolls.append(ores.measure(W, H, floor, overlay, self.region, BIOME_NAMES))

    # -- connectivity ----------------------------------------------------------------------------

    def passable(self, i):
        w = self.wall[i]
        return (w is None or w in NON_SOLID_BLOCKS) and self.floor[i] not in DEEP_FLOORS

    def bfs(self, start):
        dist = array("i", [-1]) * N
        dist[start] = 0
        q = deque([start])
        while q:
            i = q.popleft()
            x = i % W
            nd = dist[i] + 1
            for j in (i - 1 if x > 0 else -1, i + 1 if x < W - 1 else -1, i - W, i + W):
                if 0 <= j < N and dist[j] < 0 and self.passable(j):
                    dist[j] = nd
                    q.append(j)
        return dist

    def carve_path(self, src, dst):
        """Cheapest path where rock/deep liquid is expensive; then make a 7-wide passage along it."""
        cost_open, cost_hard = 1, 30
        best = {src: 0}
        prev = {}
        heap = [(0, src)]
        tx, ty = dst % W, dst // W
        while heap:
            c, i = heapq.heappop(heap)
            if i == dst:
                break
            if c > best.get(i, 1 << 60):
                continue
            x = i % W
            for j in (i - 1 if x > 0 else -1, i + 1 if x < W - 1 else -1, i - W, i + W):
                if not (0 <= j < N):
                    continue
                step = cost_open if self.passable(j) else cost_hard
                nc = c + step
                if nc < best.get(j, 1 << 60):
                    best[j] = nc
                    prev[j] = i
                    h = abs(j % W - tx) + abs(j // W - ty)
                    heapq.heappush(heap, (nc + h, j))
        i = dst
        carved = 0
        swap = {"deep-water": "shallow-water", "tar": "shale", "pooled-cryofluid": "ice", "molten-slag": "magmarock"}
        while i in prev:
            if not self.passable(i):
                for j, d in disc(i % W, i // W, 3.0):
                    if self.wall[j] is not None and self.wall[j] not in NON_SOLID_BLOCKS:
                        self.wall[j] = None
                        carved += 1
                    if self.floor[j] in swap:
                        self.floor[j] = swap[self.floor[j]]
                        carved += 1
            i = prev[i]
        return carved

    def ensure_connectivity(self):
        start = 397 * W + 400
        dist = self.bfs(start)
        for key, (sx, sy) in SPAWNS.items():
            s = sy * W + sx
            if dist[s] < 0:
                carved = self.carve_path(s, start)
                self.notes.append("Carved %d tiles to connect %s spawn" % (carved, key))
                dist = self.bfs(start)
        for pad in self.pads:
            p = pad["y"] * W + pad["x"]
            if dist[p] < 0:
                carved = self.carve_path(p, start)
                self.notes.append("Carved %d tiles to connect %s" % (carved, pad["name"]))
                dist = self.bfs(start)
        self.dist = dist

    def corridor(self, key, slack=0.02):
        """Every tile on a near-shortest ground route (within `slack`) from a spawn to the core.
        Mindustry's flow field uses 4-way steps, so many staircase routes tie; the corridor shows them all."""
        sx, sy = SPAWNS[key]
        ds = self.bfs(sy * W + sx)
        dc = self.dist
        best = ds[397 * W + 400]
        limit = best * (1.0 + slack) + 4
        tiles = bytearray(N)
        for i in range(N):
            a, b = ds[i], dc[i]
            if a >= 0 and b >= 0 and a + b <= limit:
                tiles[i] = 1
        hits = []
        for name, (mx, my) in self.markers.items():
            reach = [ds[j] for j, d in disc(mx, my, 20.0) if tiles[j]]
            if reach:
                hits.append((min(reach), name))
        return best, [name for _, name in sorted(hits)], tiles

    # -- statistics ----------------------------------------------------------------------------

    def statistics(self):
        """Terrain written to the map (ores and siratla crystal are rolled in-game, see ore_statistics)."""
        biome_tiles = [0] * 6
        open_tiles = [0] * 6
        resources = {}
        groups = {
            "water": {"deep-water", "shallow-water", "sand-water", "darksand-water"},
            "cryofluid": {"pooled-cryofluid"}, "oil (tar)": {"tar"}, "oil-rich ground (shale)": {"shale"},
            "slag (lava)": {"molten-slag"}, "pyroplasma (pyromagma)": {"pyromagma"},
            "cold plasma (glowing vein)": {"glowingvein"},
            "heat (hotrock/magmarock)": {"hotrock", "magmarock"}, "spore moss": {"spore-moss"},
            "sand floor (sand/darksand)": {"sand-floor", "darksand"},
        }
        for i in range(N):
            b = self.region[i]
            biome_tiles[b] += 1
            if self.passable(i):
                open_tiles[b] += 1
            fl = self.floor[i]
            for gname, members in groups.items():
                if fl in members:
                    resources.setdefault(BIOME_NAMES[b], {}).setdefault(gname, 0)
                    resources[BIOME_NAMES[b]][gname] += 1
        return {
            "biome_tiles": {BIOME_NAMES[b]: biome_tiles[b] for b in range(6)},
            "walkable_tiles": {BIOME_NAMES[b]: open_tiles[b] for b in range(6)},
            "special_floors": resources,
        }

    def ore_statistics(self):
        """Averages over the simulated rolls: patches (6+ tiles) and ore tiles per biome, patch sizes."""
        n = len(self.rolls)
        tiles, count, sizes = {}, {}, []
        for roll_tiles, roll_count, roll_sizes in self.rolls:
            for total, part in ((tiles, roll_tiles), (count, roll_count)):
                for reg, kinds in part.items():
                    for kind, v in kinds.items():
                        total.setdefault(reg, {}).setdefault(kind, 0)
                        total[reg][kind] += v / n
            sizes += roll_sizes
        sizes.sort()

        def tidy(table):
            return {reg: dict(sorted(((k, round(v)) for k, v in table.get(reg, {}).items()), key=lambda kv: -kv[1]))
                    for reg in BIOME_NAMES}

        return {
            "rolls": n,
            "patches_per_game": round(len(sizes) / n),
            "patch_tiles": {"median": sizes[len(sizes) // 2], "p10": sizes[len(sizes) // 10],
                            "p90": sizes[len(sizes) * 9 // 10], "smallest_counted": 6},
            "patches_per_biome": {reg: round(sum(count.get(reg, {}).values())) for reg in BIOME_NAMES},
            "patches": tidy(count),
            "ore_tiles": tidy(tiles),
        }

    # -- export ----------------------------------------------------------------------------------

    def block_table(self):
        used = set(self.floor) | {o for o in self.ore if o} | {w for w in self.wall if w} | {"core-foundation"}
        table = list(msav.RUNTIME_BLOCK_PREFIX)
        table += sorted(used - set(table))
        return table


# ----------------------------------------------------------------------------------------------
# Preview image
# ----------------------------------------------------------------------------------------------

COLORS = {
    "stone": (92, 92, 98), "crater-stone": (80, 80, 88), "char": (58, 52, 50), "basalt": (52, 50, 56),
    "hotrock": (128, 72, 52), "magmarock": (196, 96, 44), "molten-slag": (255, 132, 36),
    "pyromagma": (255, 70, 20), "sand-floor": (222, 196, 138), "darksand": (150, 118, 88),
    "salt": (232, 226, 214), "shale": (132, 98, 78), "dirt": (142, 110, 80), "mud": (100, 84, 70),
    "dacite": (164, 152, 142), "grass": (88, 140, 70), "moss": (70, 112, 62), "spore-moss": (112, 82, 142),
    "snow": (236, 240, 246), "ice": (176, 208, 240), "ice-snow": (208, 224, 240),
    "siratla-stone": (150, 172, 196), "siratla-crystal": (120, 205, 245), "glowingvein": (160, 230, 255),
    "deep-water": (38, 68, 140), "shallow-water": (72, 112, 182), "sand-water": (122, 150, 170),
    "darksand-water": (90, 110, 132), "tar": (28, 28, 34), "pooled-cryofluid": (96, 200, 232),
    "core-zone": (230, 186, 60), "metal-floor": (112, 112, 122), "metal-floor-damaged": (96, 96, 102),
    "dark-panel-1": (66, 66, 72), "dark-panel-2": (62, 62, 70), "dark-panel-3": (72, 72, 80),
    "dark-panel-4": (60, 60, 66), "dark-panel-5": (64, 64, 70), "dark-panel-6": (58, 58, 64),
    "stone-wall": (58, 58, 64), "sand-wall": (176, 146, 98), "salt-wall": (196, 190, 180),
    "shale-wall": (98, 74, 60), "dirt-wall": (98, 74, 54), "dacite-wall": (118, 108, 100),
    "snow-wall": (188, 198, 210), "ice-wall": (136, 166, 200), "dune-wall": (64, 48, 42),
    "spore-wall": (80, 60, 100), "dark-metal": (40, 40, 48), "siratla-stone-wall": (104, 126, 150),
    "pine": (36, 88, 40), "snow-pine": (58, 106, 82), "spore-pine": (92, 58, 122), "shrubs": (58, 100, 50),
    "white-tree-dead": (112, 100, 90),
    "ore-copper": (218, 142, 92), "ore-lead": (142, 132, 176), "ore-scrap": (136, 134, 124),
    "ore-coal": (30, 30, 30), "ore-titanium": (140, 162, 232), "ore-thorium": (240, 150, 200),
    "ore-beryllium": (58, 143, 100), "ore-tungsten": (118, 138, 154), "ore-dytrix": (115, 255, 174),
    "ore-siradamite": (169, 216, 255), "ore-stellar-steel": (102, 177, 255), "ore-urbium": (64, 64, 84),
}


def write_png(path, width, height, pixels):
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw += pixels[y * width * 3:(y + 1) * width * 3]

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


def render_preview(mb, path):
    """Top-down view with the first simulated ore roll (every game rolls its own)."""
    px = bytearray(N * 3)
    for i in range(N):
        x, y = i % W, i // W
        w, o, f = mb.wall[i], mb.preview_ore[i], mb.preview_floor[i]
        if w is not None and w not in NON_SOLID_BLOCKS:
            c = COLORS.get(w, (60, 60, 60))
        elif o is not None and o != "spawn":
            c = COLORS.get(o, (255, 0, 255))
        else:
            c = COLORS.get(f, (255, 0, 255))
            if w is not None:
                c = tuple(int(v * 0.8) for v in c)
        k = ((H - 1 - y) * W + x) * 3
        px[k:k + 3] = bytes(c)

    def dot(cx, cy, rad, color, ring=False):
        for i, d in disc(cx, cy, rad):
            if ring and d < rad - 1.5:
                continue
            x, y = i % W, i // W
            k = ((H - 1 - y) * W + x) * 3
            px[k:k + 3] = bytes(color)

    for (sx, sy) in SPAWNS.values():
        dot(sx, sy, 37.5, (255, 60, 60), ring=True)
        dot(sx, sy, 7, (230, 30, 30))
    for pad in mb.pads:
        dot(pad["x"], pad["y"], 6, (0, 230, 230), ring=True)
    for name, (mx, my) in mb.markers.items():
        dot(mx, my, 3.5, (255, 230, 0))
    dot(400.5, 400.5, 5, (255, 150, 0))
    write_png(path, W, H, px)


ROUTE_COLORS = {"frozen": (0, 190, 255), "semiarid": (255, 150, 0), "desert": (235, 215, 0),
                "forest": (40, 200, 60), "volcano": (255, 50, 50)}


def render_routes(mb, corridors, path):
    """Grey terrain with each spawn's near-shortest ground corridor in its own colour."""
    px = bytearray(N * 3)
    for i in range(N):
        x, y = i % W, i // W
        w, f = mb.wall[i], mb.floor[i]
        if w is not None and w not in NON_SOLID_BLOCKS:
            c = (38, 38, 42)
        elif f in DEEP_FLOORS:
            c = (40, 70, 130) if f != "molten-slag" else (150, 60, 20)
        elif f in LIQUID_FLOORS:
            c = (150, 175, 210)
        else:
            c = (196, 196, 200)
        hit = [ROUTE_COLORS[k] for k, (_, _, tiles) in corridors.items() if tiles[i]]
        if hit:
            r = sum(h[0] for h in hit) // len(hit)
            g = sum(h[1] for h in hit) // len(hit)
            b = sum(h[2] for h in hit) // len(hit)
            c = ((c[0] + 2 * r) // 3, (c[1] + 2 * g) // 3, (c[2] + 2 * b) // 3)
        k = ((H - 1 - y) * W + x) * 3
        px[k:k + 3] = bytes(c)

    def dot(cx, cy, rad, color):
        for i, d in disc(cx, cy, rad):
            k = ((H - 1 - i // W) * W + i % W) * 3
            px[k:k + 3] = bytes(color)

    for name, (mx, my) in mb.markers.items():
        dot(mx, my, 5, (0, 0, 0))
        dot(mx, my, 3, (255, 255, 255))
    for key, (sx, sy) in SPAWNS.items():
        dot(sx, sy, 9, (0, 0, 0))
        dot(sx, sy, 7, ROUTE_COLORS[key])
    for pad in mb.pads:
        dot(pad["x"], pad["y"], 4, (0, 230, 230))
    dot(400.5, 400.5, 7, (0, 0, 0))
    dot(400.5, 400.5, 5, (255, 140, 0))
    write_png(path, W, H, px)


# ----------------------------------------------------------------------------------------------

DESCRIPTION = (
    "[accent]800x800 PvE survival for 4-8 players, built for Exogenesis Old.[]\n"
    "Hold the Crossroads core against endless waves from five biome spawns: the frozen north, the semi-arid "
    "north-east, the eastern desert, the western forest and the volcano in the south-west. Serpulo and "
    "Erekir armies march with Exogenesis Old elites. Ore nodes are re-rolled every time the map is loaded: "
    "every ore can appear in every biome, and each biome leans toward the materials of the Exogenesis "
    "faction it is themed after. Thermal generators can be built anywhere on lava. Claim the core-zone "
    "outposts to expand. Bosses from wave 40; sagittarius from wave 300."
)


def main():
    parser = argparse.ArgumentParser(description="Generate the Biomes Extended Remastered Mindustry map.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--name", default=MAP_NAME)
    parser.add_argument("--ore-rolls", type=int, default=1,
                        help="in-game ore rolls to simulate for the report (20-50 s each; default 1)")
    args = parser.parse_args()

    t0 = time.time()
    os.makedirs(args.out, exist_ok=True)
    mb = MapBuilder(args.seed, max(1, args.ore_rolls))
    steps = (
        ("noise fields", mb.build_noise), ("polar grid", mb.build_polar), ("biomes", mb.build_biomes),
        ("floors", mb.paint_floors), ("volcano", mb.volcano_features), ("forest", mb.forest_features),
        ("frozen", mb.frozen_features), ("semi-arid", mb.semiarid_features), ("desert", mb.desert_features),
        ("keep-clear zones", mb.keep_clear), ("natural walls", mb.natural_walls),
        ("structural walls", mb.structural_walls), ("outpost pads", mb.place_pads),
        ("spawns and core plaza", mb.clear_spawns_and_core), ("decorations", mb.decorate),
        ("connectivity", mb.ensure_connectivity), ("ore rolls (preview)", mb.roll_ores),
    )
    for label, step in steps:
        ts = time.time()
        step()
        print("  %-22s %6.1fs" % (label, time.time() - ts))

    routes, corridors = {}, {}
    for key in SPAWNS:
        length, hits, tiles = mb.corridor(key)
        corridors[key] = (length, hits, tiles)
        routes[SPAWN_LABELS[key]] = {"shortest_ground_path_tiles": length,
                                     "choke_points_on_near_shortest_routes": hits}

    table = mb.block_table()
    index = {name: k for k, name in enumerate(table)}
    floors = [index[f] for f in mb.floor]
    overlays = [index[o] if o else 0 for o in mb.ore]
    walls = [index[w] if w else 0 for w in mb.wall]
    core = {"x": 400, "y": 400, "size": 4, "block": index["core-foundation"], "chunk": msav.core_chunk()}

    rules = waves.build_rules(SPAWNS)
    tags = {
        "name": args.name, "author": MAP_AUTHOR, "description": DESCRIPTION,
        "rules": json.dumps(rules, separators=(",", ":")),
        "width": str(W), "height": str(H), "build": "159", "saved": str(int(time.time() * 1000)),
        "playtime": "0", "mapname": args.name, "wave": "1", "tick": "0.0", "wavetime": "0.0",
        "stats": "{}", "locales": "{}", "mods": "[]", "controlGroups": "null", "viewpos": "(3204.0,3204.0)",
        "controlledType": "null", "nocores": "false", "playerteam": "1", "hasExternalAssets": "false",
        "sectorPreset": "", "genfilters": ores.to_json(mb.filters, file_block_name),
    }
    map_path = os.path.join(args.out, args.name + ".msav")
    file_table = [file_block_name(name) for name in table]
    raw_size, file_size = msav.write_msav(map_path, W, H, file_table, floors, overlays, walls, [core], tags,
                                          DATA_PATCHES)

    check = msav.validate_msav(map_path, known_blocks=set(file_table))
    assert check["blocks"] == file_table
    assert check["width"] == W and check["height"] == H
    assert [table[k] for k in check["floors"]] == mb.floor
    assert all((table[k] if k else None) == (o if o else None) for k, o in zip(check["overlays"], mb.ore))
    assert {table[k] for k in check["overlays"] if k} == {"spawn"}
    assert len(check["buildings"]) == 1 and check["buildings"][0]["block"] == "core-foundation"
    assert check["buildings"][0]["team"] == 1
    assert [(p["path"], p["text"]) for p in check["patches"]] == list(DATA_PATCHES)
    assert json.loads(check["tags"]["genfilters"]) == json.loads(tags["genfilters"])

    preview_path = os.path.join(args.out, args.name + " - preview.png")
    render_preview(mb, preview_path)
    routes_path = os.path.join(args.out, args.name + " - enemy routes.png")
    render_routes(mb, corridors, routes_path)

    report = {
        "map": args.name, "seed": args.seed, "size": [W, H], "game": "Mindustry v8 build 159.7 (save version 13)",
        "mod": "Exogenesis Old (exogenesisold 1.9.1)", "file": map_path,
        "file_bytes": file_size, "uncompressed_bytes": raw_size,
        "spawns": {SPAWN_LABELS[k]: v for k, v in SPAWNS.items()},
        "routes": routes, "outposts": mb.pads,
        "choke_points": {k: v for k, v in sorted(mb.markers.items())},
        "statistics": mb.statistics(),
        "ore_rolls": mb.ore_statistics(),
        "ore_filters": json.loads(tags["genfilters"]), "genfilters_bytes": len(tags["genfilters"]),
        "data_patches": [{"path": p, "patch": json.loads(t)} for p, t in DATA_PATCHES],
        "rules": {k: v for k, v in rules.items() if k != "spawns"}, "spawn_groups": len(rules["spawns"]),
        "rules_json_bytes": len(tags["rules"]),
        "wave_summary": waves.wave_summary([1, 10, 20, 30, 40, 50, 60, 75, 90, 100, 120, 150, 200, 250, 300]),
        "wave_curve": waves.curve(1, 310, 10),
        "notes": mb.notes,
    }
    report_path = os.path.join(args.out, args.name + " - report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print("\nMap written:   %s (%d KB, %d KB uncompressed)" % (map_path, file_size // 1024, raw_size // 1024))
    print("Preview:       %s" % preview_path)
    print("Enemy routes:  %s" % routes_path)
    print("Report:        %s" % report_path)
    for label, info in routes.items():
        print("  %-30s %4d tiles via %s" % (label, info["shortest_ground_path_tiles"],
                                           ", ".join(info["choke_points_on_near_shortest_routes"])))
    ore_stats = report["ore_rolls"]
    print("Ores: %d in-game filters, ~%d patches per game (median %d tiles; %d simulated roll%s)"
          % (len(mb.filters), ore_stats["patches_per_game"], ore_stats["patch_tiles"]["median"],
             ore_stats["rolls"], "" if ore_stats["rolls"] == 1 else "s"))
    for note in mb.notes:
        print("  note: " + note)
    print("Done in %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
