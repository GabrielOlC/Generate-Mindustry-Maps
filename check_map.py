#!/usr/bin/env python3
"""Re-reads a generated map and proves that every choke point really is the only way across its barrier.

    python check_map.py                                  # default map in the "maps" folder
    python check_map.py "path\\to\\map.msav"              # another map

The map is decoded with the same region/length checks the game performs (msav.validate_msav).
Each barrier test closes the named choke points and checks whether the far side is still reachable
by ground units (walls and deep liquids block; boulders do not).
"""

import json
import math
import sys
from collections import deque

import generate_map as gm
import msav


def main(path):
    info = msav.validate_msav(path)
    width, height = info["width"], info["height"]
    names = info["blocks"]
    mod_content = sorted(n for n in names if n.startswith(gm.MOD_PREFIX))
    unprefixed = [n for n in names if n in gm.MOD_BLOCKS]
    blocks = [n[len(gm.MOD_PREFIX):] if n.startswith(gm.MOD_PREFIX) else n for n in names]
    floor = [blocks[k] for k in info["floors"]]
    wall = [blocks[k] if k else None for k in info["walls"]]
    spawns = sum(1 for k in info["overlays"] if k and blocks[k] == "spawn")
    rules = json.loads(info["tags"]["rules"])
    print("Decoded %s: %dx%d, save version %d, %d block types, %d spawn points, %d wave groups"
          % (info["tags"]["name"], width, height, info["version"], len(blocks), spawns, len(rules["spawns"])))
    for b in info["buildings"]:
        print("  building: %s at (%d, %d), team %d" % (b["block"], b["x"], b["y"], b["team"]))
    print("  Exogenesis Old terrain used: " + ", ".join(mod_content))
    if unprefixed:
        print("  FAIL: mod blocks without the '%s' prefix: %s" % (gm.MOD_PREFIX, unprefixed))
        return 1
    units = sorted({g["type"] for g in rules["spawns"]})
    mod_units = [u for u in units if u.startswith(gm.MOD_PREFIX)]
    print("  wave unit types: %d (%d from Exogenesis Old)" % (len(units), len(mod_units)))

    report = json.load(open(path[:-len(".msav")] + " - report.json", encoding="utf-8"))
    marks = report["choke_points"]

    def passable(i):
        w = wall[i]
        return (w is None or w in gm.NON_SOLID_BLOCKS) and floor[i] not in gm.DEEP_FLOORS

    def around(names, rad):
        out = set()
        for n in names:
            mx, my = marks[n]
            for y in range(my - rad, my + rad + 1):
                for x in range(mx - rad, mx + rad + 1):
                    if math.hypot(x - mx, y - my) <= rad and 0 <= x < width and 0 <= y < height:
                        out.add(y * width + x)
        return out

    def angle(i):
        return math.degrees(math.atan2(i // width - 400, i % width - 400)) % 360

    def reachable(start, goal, region, closed):
        s = start[1] * width + start[0]
        g = goal[1] * width + goal[0]
        seen = {s}
        q = deque([s])
        while q:
            i = q.popleft()
            if i == g:
                return True
            x = i % width
            for j in (i - 1 if x > 0 else -1, i + 1 if x < width - 1 else -1, i - width, i + width):
                if 0 <= j < width * height and j not in seen and j not in closed and passable(j) and region(j):
                    seen.add(j)
                    q.append(j)
        return False

    tests = [
        ("Forest river", ["North Ford", "South Ford"], 16, (60, 450), (230, 450),
         lambda j: j % width < 300 and 230 < j // width < 620),
        ("Volcano lava rivers", ["West Basalt Bridge", "South Basalt Bridge"], 16, (68, 68), (309, 253),
         lambda j: True),
        ("Frozen cryofluid lakes", ["Frost Bridge East", "Frost Bridge West"], 18, (420, 760), (400, 560),
         lambda j: 64 <= angle(j) <= 140),
        ("Semi-arid mesas", ["Red Canyon", "Dust Canyon"], 22, (730, 730), (495, 526),
         lambda j: 18 <= angle(j) <= 72),
        ("Desert dune wall", ["Tar Narrows", "Salt Pass", "Southern Breach"], 18, (778, 352), (556, 337),
         lambda j: angle(j) >= 280 or angle(j) <= 26),
    ]
    ok = True
    print("\nBarrier tests (enemy side -> core side):")
    for label, names, rad, start, goal, region in tests:
        open_ = reachable(start, goal, region, set())
        closed = reachable(start, goal, region, around(names, rad))
        good = open_ and not closed
        ok &= good
        print("  %-24s crossings open: %-9s crossings closed: %-9s %s"
              % (label, "reachable" if open_ else "BLOCKED", "LEAKS" if closed else "sealed",
                 "OK" if good else "FAIL  <- " + ", ".join(names)))
    print("\nAll checks passed." if ok else "\nSome checks failed.")
    return 0 if ok else 1


if __name__ == "__main__":
    default = gm.os.path.join(gm.DEFAULT_OUT, gm.MAP_NAME + ".msav")
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else default))
