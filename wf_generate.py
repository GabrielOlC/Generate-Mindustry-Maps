#!/usr/bin/env python3
"""Map generator controller: asks which map type and difficulty to generate and routes them to the layout.

    python wf_generate.py                                   # asks for the map type, then the difficulty
    python wf_generate.py --list                            # lists the map types and difficulties
    python wf_generate.py --map biomes-confluence           # no questions; the hardest difficulty
    python wf_generate.py --map biomes-confluence --difficulty normal
    python wf_generate.py --map biomes-extended --seed 42 --ore-rolls 5 --out "D:\\some\\folder"

Every map type is a layout in the `layouts` folder; every difficulty is a level in sys_config.py. All of
them share the same pipeline (cm_pipeline.py). Leaving the difficulty out - no --difficulty, or Enter at
the question - picks the hardest level. Each run writes the .msav, a preview PNG, an enemy-routes PNG and
a JSON report to the maps folder, then runs the map's checks; the exit code is 0 only if they all pass.
"""

import argparse
import sys

import cm_layout
import cm_pipeline
import sys_config


def fnAskMapType(dtLayouts):
    """Prints the numbered map types and reads a choice (number or key); None if there is no answer."""
    arKeys = list(dtLayouts)
    print("Map types:")
    for vNumber, vKey in enumerate(arKeys, 1):
        print("  %d. %s  [%s]\n     %s" % (vNumber, dtLayouts[vKey].cName, vKey, dtLayouts[vKey].cSummary))
    while True:
        try:
            vAnswer = input("Which map type? (number or key): ").strip()
        except EOFError:
            return None
        if vAnswer.isdigit() and 1 <= int(vAnswer) <= len(arKeys):
            return arKeys[int(vAnswer) - 1]
        if vAnswer in dtLayouts:
            return vAnswer
        print("  Not a map type: %r" % vAnswer)


def fnAskDifficulty():
    """Prints the numbered difficulties and reads a choice; Enter (or no answer) picks the hardest."""
    arKeys = list(sys_config.cdtDifficulties)
    print("Difficulties:")
    for vNumber, vKey in enumerate(arKeys, 1):
        print("  %d. %s" % (vNumber, sys_config.fnDifficultyNote(vKey)[len("Difficulty: "):-1]))
    while True:
        try:
            vAnswer = input("Which difficulty? (number or key, Enter = %s): "
                            % sys_config.cdtDifficulties[sys_config.cDefaultDifficulty]["label"]).strip().lower()
        except EOFError:
            vAnswer = ""
        if not vAnswer:
            return sys_config.cDefaultDifficulty
        if vAnswer.isdigit() and 1 <= int(vAnswer) <= len(arKeys):
            return arKeys[int(vAnswer) - 1]
        if vAnswer in sys_config.cdtDifficulties:
            return vAnswer
        print("  Not a difficulty: %r" % vAnswer)


def fnMain(arArgv=None):
    sParser = argparse.ArgumentParser(description="Generate a Mindustry map of one of the registered map types.")
    sParser.add_argument("--map", help="map type key (see --list); asked for when left out")
    sParser.add_argument("--difficulty", choices=list(sys_config.cdtDifficulties),
                         help="wave difficulty (default: %s, the hardest)" % sys_config.cDefaultDifficulty)
    sParser.add_argument("--list", action="store_true", help="list the map types and difficulties and exit")
    sParser.add_argument("--seed", type=int, help="terrain seed (default: the map type's own)")
    sParser.add_argument("--out", default=sys_config.cDefaultOut, help="output folder (default: maps)")
    sParser.add_argument("--ore-rolls", type=int, default=1,
                         help="in-game ore rolls to simulate for the report (20-50 s each; default 1)")
    sArgs = sParser.parse_args(arArgv)

    dtLayouts = cm_layout.fnFindLayouts()
    if sArgs.list:
        print("Map types:")
        for vKey, sLayoutClass in dtLayouts.items():
            print("  %-20s %s - %s" % (vKey, sLayoutClass.cName, sLayoutClass.cSummary))
        print("Difficulties (default: the hardest):")
        for vKey in sys_config.cdtDifficulties:
            print("  %-20s %s" % (vKey, sys_config.fnDifficultyNote(vKey)))
        return 0
    vKey = sArgs.map
    vDifficulty = sArgs.difficulty
    if vKey is None:
        vKey = fnAskMapType(dtLayouts)
        if vKey is None:
            print("No map type chosen.")
            return 2
        if vDifficulty is None:
            vDifficulty = fnAskDifficulty()
    if vKey not in dtLayouts:
        print("Unknown map type '%s'. Map types: %s" % (vKey, ", ".join(dtLayouts)))
        return 2
    sLayout = dtLayouts[vKey]()
    vSeed = sArgs.seed if sArgs.seed is not None else sLayout.cDefaultSeed
    vOk = cm_pipeline.fnGenerate(sLayout, vSeed, sArgs.out, sArgs.ore_rolls,
                                 vDifficulty or sys_config.cDefaultDifficulty)
    return 0 if vOk else 1


if __name__ == "__main__":
    sys.exit(fnMain())
