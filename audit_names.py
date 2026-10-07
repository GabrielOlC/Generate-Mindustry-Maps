#!/usr/bin/env python3
"""Checks every content name a generated map uses against the real game and mod content lists.

    python audit_names.py                                   # default map, game tag v159.7
    python audit_names.py "path\\to\\map.msav" --tag v160.6   # another map / another game build

Downloads (standard library only, needs internet):
  * Blocks.java, UnitTypes.java, Items.java, StatusEffects.java from github.com/Anuken/Mindustry at --tag
  * the file list of github.com/AureusStratus/ExoGenesis (Exogenesis Old) - mod names are
    "exogenesisold-<file name>"
A name the game does not know is silently replaced (blocks -> air/stone, units -> dagger), so this is
the only way to catch typos or content renamed in a newer game version.
"""

import argparse
import json
import os
import re
import sys
import urllib.request

import msav

GAME_RAW = "https://raw.githubusercontent.com/Anuken/Mindustry/%s/core/src/mindustry/%s"
MOD_TREE = "https://api.github.com/repos/AureusStratus/ExoGenesis/git/trees/main?recursive=1"
MOD_PREFIX = "exogenesisold-"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "biomes-map-audit"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser()
    parser.add_argument("map", nargs="?",
                        default=os.path.join(here, "maps", "Biomes Extended Remastered.msav"))
    parser.add_argument("--tag", default="v159.7", help="Mindustry release tag the map targets")
    args = parser.parse_args()

    blocks_src = fetch(GAME_RAW % (args.tag, "content/Blocks.java"))
    units_src = fetch(GAME_RAW % (args.tag, "content/UnitTypes.java"))
    items_src = fetch(GAME_RAW % (args.tag, "content/Items.java"))
    status_src = fetch(GAME_RAW % (args.tag, "content/StatusEffects.java"))

    item_fields = dict(re.findall(r'(\w+) = new Item\("([a-z-]+)"', items_src))
    vanilla_blocks = set(re.findall(r'new [A-Za-z]+\("([a-z0-9-]+)"', blocks_src))
    vanilla_blocks |= {"build%d" % i for i in range(1, 17)}          # ConstructBlock sizes
    for field in re.findall(r'new OreBlock\(Items\.([a-zA-Z]+)\)', blocks_src):
        if field in item_fields:
            vanilla_blocks.add("ore-" + item_fields[field])
    vanilla_units = set(re.findall(r'new [A-Za-z]*UnitType\("([a-z-]+)"', units_src))
    vanilla_items = set(item_fields.values())
    statuses = set(re.findall(r'new StatusEffect\("([a-z-]+)"', status_src))

    mod_blocks, mod_units = set(), set()
    for t in json.loads(fetch(MOD_TREE))["tree"]:
        p = t["path"]
        if t["type"] == "blob" and p.endswith((".json", ".hjson")):
            base = MOD_PREFIX + os.path.splitext(os.path.basename(p))[0]
            if p.startswith("content/blocks/"):
                mod_blocks.add(base)
            elif p.startswith("content/units/"):
                mod_units.add(base)

    info = msav.validate_msav(args.map)
    table = info["blocks"]
    rules = json.loads(info["tags"]["rules"])
    bad_blocks = [n for n in table if n not in vanilla_blocks | mod_blocks]
    units = sorted({g["type"] for g in rules["spawns"]})
    bad_units = [u for u in units if u not in vanilla_units | mod_units]
    bad_effects = sorted({g["effect"] for g in rules["spawns"] if "effect" in g} - statuses)
    bad_items = [s["item"] for s in rules["loadout"] if s["item"] not in vanilla_items]
    width = info["width"]
    spawn_tiles = {(i % width, i // width) for i, k in enumerate(info["overlays"]) if k and table[k] == "spawn"}
    pinned = {((g["spawn"] >> 16) & 0xFFFF, g["spawn"] & 0xFFFF) for g in rules["spawns"] if "spawn" in g}

    print("game %s: %d blocks, %d units | Exogenesis Old: %d blocks, %d units"
          % (args.tag, len(vanilla_blocks), len(vanilla_units), len(mod_blocks), len(mod_units)))
    print("block names used: %d, unknown: %s" % (len(table), bad_blocks or "none"))
    print("wave unit types: %d, unknown: %s" % (len(units), bad_units or "none"))
    print("status effects unknown: %s | loadout items unknown: %s" % (bad_effects or "none", bad_items or "none"))
    print("pinned wave spawns on spawn tiles: %s" % (pinned <= spawn_tiles))
    print("rules JSON: %d bytes (limit 65535)" % len(info["tags"]["rules"]))
    ok = not (bad_blocks or bad_units or bad_effects or bad_items) and pinned <= spawn_tiles
    print("All names valid." if ok else "PROBLEMS FOUND.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
