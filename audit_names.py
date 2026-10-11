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
  * on PvP maps: LStatements.java, LogicRule.java and FetchType.java at --tag, to confirm the defender
    bots' world-processor code still parses (statements, team rules, fetch types, content names)
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
    """Names of the public fields declared in a Java source (`public float a = 1, b = 2;`,
    `public Attributes attributes = new Attributes();`)."""
    names = set()
    for decl in re.findall(r"public\s+(?:static\s+)?(?:final\s+)?[\w.<>\[\]]+\s+([^;(){}]+);", java):
        for part in decl.split(","):
            name = part.split("=")[0].strip()
            if re.fullmatch(r"[A-Za-z_]\w*", name):
                names.add(name)
    # first name of declarations whose initializer the pattern above cannot take apart
    names.update(re.findall(r"public\s+(?:(?:static|final|transient|volatile)\s+)*(?:@\w+\s+)?"
                            r"[\w.]+(?:<[\w.<>, ?]*>)?(?:\[\])*\s+(\w+)\s*(?:=|;|,)", java))
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


def patch_paths(tree, prefix=""):
    """Data patch JSON -> dotted paths ("block.thermal-generator.placeableLiquid"); the game accepts both
    nested objects and dotted keys."""
    out = []
    for key, value in tree.items():
        if not prefix and key == "name":
            continue
        out += patch_paths(value, prefix + key + ".") if isinstance(value, dict) else [prefix + key]
    return out


def audit_patches(tag, patches, known_blocks):
    """Problems with the data patches at this game tag: block names, Block fields and attributes."""
    problems = []
    block_fields = public_fields(fetch(GAME_RAW % (tag, "world/Block.java")))
    attributes = set(re.findall(r'(\w+)\s*=\s*add\("(\w+)"\)', fetch(GAME_RAW % (tag, "world/meta/Attribute.java"))))
    attributes = {name for _, name in attributes}
    for asset in patches:
        for path in patch_paths(json.loads(asset["text"])):
            parts = path.split(".")
            if parts[0] != "block" or len(parts) < 3:
                problems.append("%s: only block field patches are audited, found %s" % (asset["path"], path))
                continue
            if parts[1] not in known_blocks:
                problems.append("%s: unknown block %s" % (asset["path"], parts[1]))
            if parts[2] not in block_fields:
                problems.append("%s: Block has no field %s" % (asset["path"], parts[2]))
            elif parts[2] == "attributes" and (len(parts) != 4 or parts[3] not in attributes):
                problems.append("%s: unknown attribute in %s" % (asset["path"], path))
            elif parts[2] != "attributes" and len(parts) != 3:
                problems.append("%s: nested field %s is not audited" % (asset["path"], path))
    return problems


def _fnEnumNames(java):
    """Constant names of the first Java enum in a source file."""
    vBody = java.split("{", 1)[1].split(";", 1)[0]
    vBody = re.sub(r"//[^\n]*", "", vBody)
    return {v.strip() for v in vBody.split(",") if v.strip()}


def fnAuditLogic(vTag, arBuildings, arKnownBlocks, arKnownItems, arKnownUnits):
    """Problems with world-processor code at this game tag (empty list = fine), and how many processors."""
    import cm_bot
    arCodes = [b["code"] for b in arBuildings if "code" in b]
    if not arCodes:
        return [], 0
    arStatements = set(re.findall(r'@RegisterStatement\("(\w+)"\)', fetch(GAME_RAW % (vTag, "logic/LStatements.java"))))
    arRules = _fnEnumNames(fetch(GAME_RAW % (vTag, "logic/LogicRule.java")))
    arFetch = _fnEnumNames(fetch(GAME_RAW % (vTag, "logic/FetchType.java")))
    arProblems = []
    for sCode in arCodes:
        arCheck, _, dtContent = cm_bot.fnCheckProgram(sCode)
        arProblems += arCheck
        for vLine in sCode.split("\n"):
            arTokens = vLine.split("#", 1)[0].split()
            if not arTokens or arTokens[0].endswith(":"):
                continue
            if arTokens[0] not in arStatements:
                arProblems.append("statement %s does not exist" % arTokens[0])
            elif arTokens[0] == "setrule" and arTokens[1] not in arRules:
                arProblems.append("logic rule %s does not exist" % arTokens[1])
            elif arTokens[0] == "fetch" and arTokens[1] not in arFetch:
                arProblems.append("fetch type %s does not exist" % arTokens[1])
        arProblems += ["logic block %s unknown" % n for n in sorted(dtContent["block"] - arKnownBlocks)]
        arProblems += ["logic item %s unknown" % n for n in sorted(dtContent["item"] - arKnownItems)]
        arProblems += ["logic unit %s unknown" % n for n in sorted(dtContent["unit"] - arKnownUnits)]
    return sorted(set(arProblems)), len(arCodes)


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
    logic_problems, processors = fnAuditLogic(args.tag, info["buildings"], vanilla_blocks, vanilla_items, vanilla_units)

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
    if processors:
        print("world processors: %d, problems: %s" % (processors, logic_problems or "none"))
    ok = (not (bad_blocks or bad_units or bad_effects or bad_items or filter_problems or patch_problems
               or logic_problems) and pinned <= spawn_tiles)
    print("All names valid." if ok else "PROBLEMS FOUND.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
