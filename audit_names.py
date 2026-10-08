#!/usr/bin/env python3
"""Checks every content name a generated map uses against the real game and mod content lists.

    python audit_names.py                                   # default map, game tag v159.7
    python audit_names.py "path\\to\\map.msav" --tag v160.6   # another map / another game build

Downloads (standard library only, needs internet):
  * Blocks.java, UnitTypes.java, Items.java, StatusEffects.java from github.com/Anuken/Mindustry at --tag
  * the generation-filter sources, Block.java, World.java and JsonIO.java at --tag, to confirm the ore
    filters and the data patch still mean what the generator assumes
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


def public_fields(java):
    """Names of the public fields declared in a Java source (`public float a = 1, b = 2;`)."""
    names = set()
    for decl in re.findall(r"public\s+(?:static\s+)?(?:final\s+)?[\w.<>\[\]]+\s+([^;(){}]+);", java):
        for part in decl.split(","):
            name = part.split("=")[0].strip()
            if re.fullmatch(r"[A-Za-z_]\w*", name):
                names.add(name)
    return names


def audit_filters(tag, filters, known_blocks):
    """Problems with the genfilters list at this game tag (empty list = fine)."""
    problems = []
    world = fetch(GAME_RAW % (tag, "core/World.java"))
    jsonio = fetch(GAME_RAW % (tag, "io/JsonIO.java"))
    if "filter.randomize()" not in world:
        problems.append("World.java no longer re-rolls filter seeds on load")
    if 'addClassTag(Strings.camelize(i.getClass().getSimpleName().replace("Filter", ""))' not in jsonio:
        problems.append("JsonIO.java changed how filter class tags are named")
    base = public_fields(fetch(GAME_RAW % (tag, "maps/filters/GenerateFilter.java")))
    fields = {}
    for f in filters:
        cls = f["class"]
        if cls not in fields:
            fields[cls] = base | public_fields(fetch(GAME_RAW % (tag, "maps/filters/%sFilter.java"
                                                                     % (cls[0].upper() + cls[1:]))))
        unknown = sorted(set(f) - {"class"} - fields[cls])
        if unknown:
            problems.append("%s filter has no field(s) %s" % (cls, unknown))
        for key in ("ore", "target", "floor", "block"):
            if key in f and f[key] not in known_blocks:
                problems.append("%s filter: unknown block %s" % (cls, f[key]))
    return problems


def audit_patches(tag, patches, known_blocks):
    """Problems with the data patches at this game tag: block names and Block fields."""
    problems = []
    block_fields = public_fields(fetch(GAME_RAW % (tag, "world/Block.java")))
    for asset in patches:
        body = json.loads(asset["text"])
        for ctype, entries in body.items():
            if ctype == "name":
                continue
            if ctype != "block":
                problems.append("%s: only block patches are audited, found %s" % (asset["path"], ctype))
                continue
            for name, values in entries.items():
                if name not in known_blocks:
                    problems.append("%s: unknown block %s" % (asset["path"], name))
                for field in values:
                    if field not in block_fields:
                        problems.append("%s: Block has no field %s" % (asset["path"], field))
    return problems


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
    filters = json.loads(info["tags"].get("genfilters") or "[]")
    filter_names = {f[k] for f in filters for k in ("ore", "target", "floor", "block") if k in f}
    filter_problems = audit_filters(args.tag, filters, vanilla_blocks | mod_blocks)
    patch_problems = audit_patches(args.tag, info["patches"], vanilla_blocks | mod_blocks)

    print("game %s: %d blocks, %d units | Exogenesis Old: %d blocks, %d units"
          % (args.tag, len(vanilla_blocks), len(vanilla_units), len(mod_blocks), len(mod_units)))
    print("block names used: %d, unknown: %s" % (len(table), bad_blocks or "none"))
    print("ore filters: %d using %d block names, problems: %s"
          % (len(filters), len(filter_names), filter_problems or "none"))
    print("data patches: %d, problems: %s" % (len(info["patches"]), patch_problems or "none"))
    print("wave unit types: %d, unknown: %s" % (len(units), bad_units or "none"))
    print("status effects unknown: %s | loadout items unknown: %s" % (bad_effects or "none", bad_items or "none"))
    print("pinned wave spawns on spawn tiles: %s" % (pinned <= spawn_tiles))
    print("rules JSON: %d bytes, genfilters: %d bytes (limit 65535 each)"
          % (len(info["tags"]["rules"]), len(info["tags"].get("genfilters", ""))))
    ok = (not (bad_blocks or bad_units or bad_effects or bad_items or filter_problems or patch_problems)
          and pinned <= spawn_tiles)
    print("All names valid." if ok else "PROBLEMS FOUND.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
