"""Defender bots for PvP maps: the world processor program and its static check.

A PvP map carries one privileged world processor (team sys_config.cPvpWaveTeam). Its program waits for
the join window, then turns every player team that has a core but no player into a fortress that never
attacks (sys_config.cdtBotRules), and afterwards keeps the fortresses supplied. Mindustry logic has no
arrays, so the five teams are unrolled and share two subroutines (`decide`, `maintain`), called with the
return address in `ret` the usual way (op add ret @counter 1; jump ...; set @counter ret).

The check mirrors the game's parser (LParser / LStatements @ v159.7): known statements with their field
count, known enum values, labels defined once, every jump target defined, at most 1000 instructions and
500 labels. Content names (@block, @item, @unit) are returned for the name audit.
"""

import re

import sys_config

cMaxInstructions = 1000      # LExecutor.maxInstructions: the parser stops reading after this many
cMaxLabels = 500             # LParser.maxJumps

# Statements the program uses, with their field count (declaration order of the LStatements class).
cdtStatementArgs = {"set": 2, "op": 4, "jump": 4, "wait": 1, "end": 0, "fetch": 5, "setrule": 6,
                    "setblock": 6, "getblock": 4, "setprop": 3, "spawn": 7}
carLogicOps = {"add", "sub", "mul", "div", "idiv", "mod", "max", "min"}
carConditions = {"equal", "notEqual", "lessThan", "lessThanEq", "greaterThan", "greaterThanEq", "strictEqual",
                 "always"}
carFetchTypes = {"unit", "unitCount", "player", "playerCount", "core", "coreCount", "build", "buildCount"}
carTeamRules = {"buildSpeed", "unitHealth", "unitBuildSpeed", "unitMineSpeed", "unitCost", "unitDamage",
                "blockHealth", "blockDamage", "rtsMinWeight", "rtsMinSquad"}
carSettableLayers = {"floor", "ore", "block"}       # TileLayer.settable
carLayers = {"floor", "ore", "block", "building"}
cdtMultiplierRules = {"blockHealth": "blockHealth", "blockDamage": "blockDamage", "unitHealth": "unitHealth",
                      "unitDamage": "unitDamage"}


def fnBotMultipliers(vDifficulty):
    """The bot teams' setrule values at a difficulty: Normal values x the level's enemy health factor."""
    vScale = sys_config.cdtDifficulties[vDifficulty]["health"]
    return {k: round(v * vScale, 3) for k, v in sys_config.cdtBotRules["multipliers"].items()}


def _fnNum(vValue):
    return ("%d" % vValue) if float(vValue).is_integer() else ("%g" % vValue)


def fnBuildProgram(arTeamCores, vDifficulty, vTitle):
    """mlog text of the bot program for `arTeamCores` [{"team", "x", "y", ...}] at `vDifficulty`."""
    dtBot = sys_config.cdtBotRules
    dtTeamNames = {vId: vName for vName, vId in sys_config.cdtPvpTeams.items()}
    dtMult = fnBotMultipliers(vDifficulty)
    arOut = ["# %s: defender bots (generated). After %d s every player team with a core but no player becomes"
             % (vTitle, dtBot["joinWindow"]),
             "# a fortress that never attacks; a player who joins it later takes it over.",
             "wait %d" % dtBot["joinWindow"]]

    def fnLoad(dtCore):
        return ["set team @%s" % dtTeamNames[dtCore["team"]], "set cx %d" % dtCore["x"], "set cy %d" % dtCore["y"]]

    for dtCore in arTeamCores:
        arOut += fnLoad(dtCore) + ["op add ret @counter 1", "jump decide always 0 0",
                                   "set bot%d isbot" % dtCore["team"]]
    arOut.append("loop:")
    arOut.append("wait %d" % dtBot["refresh"])
    for dtCore in arTeamCores:
        vTeam = dtCore["team"]
        arOut += ["jump skip%d equal bot%d 0" % (vTeam, vTeam)] + fnLoad(dtCore) + [
            "op add ret @counter 1", "jump maintain always 0 0", "set bot%d isbot" % vTeam, "skip%d:" % vTeam]
    arOut.append("jump loop always 0 0")

    # decide: an empty slot (core, no player) becomes a bot: multipliers, turrets, wall ring, supplies
    arOut += ["decide:", "set isbot 0", "fetch coreCount c team 0 @air", "jump decided equal c 0",
              "fetch playerCount n team 0 @air", "jump decided notEqual n 0", "set isbot 1"]
    for vKey, vRule in cdtMultiplierRules.items():
        arOut.append("setrule %s %s team 0 0 0" % (vRule, _fnNum(dtMult[vKey])))
    for vBlock, _, (vDx, vDy) in dtBot["turrets"]:
        arOut += ["op add x cx %d" % vDx, "op add y cy %d" % vDy, "setblock block @%s x y team 0" % vBlock]
    vRing = dtBot["wallRing"]
    arOut += ["set k %d" % -vRing, "ringx:", "op add x cx k",
              "op sub y cy %d" % vRing, "setblock block @%s x y team 0" % dtBot["wall"],
              "op add y cy %d" % vRing, "setblock block @%s x y team 0" % dtBot["wall"],
              "op add k k 2", "jump ringx lessThanEq k %d" % vRing,
              "set k %d" % (2 - vRing), "ringy:", "op add y cy k",
              "op sub x cx %d" % vRing, "setblock block @%s x y team 0" % dtBot["wall"],
              "op add x cx %d" % vRing, "setblock block @%s x y team 0" % dtBot["wall"],
              "op add k k 2", "jump ringy lessThanEq k %d" % (vRing - 2),
              "op add ret2 @counter 1", "jump supply always 0 0",
              "decided:", "set @counter ret"]

    # maintain: a bot team keeps its supplies; a joined player gets normal multipliers back
    arOut += ["maintain:", "set isbot 0", "fetch coreCount c team 0 @air", "jump maintained equal c 0",
              "fetch playerCount n team 0 @air", "jump human notEqual n 0", "set isbot 1",
              "op add ret2 @counter 1", "jump supply always 0 0", "jump maintained always 0 0", "human:"]
    for vRule in cdtMultiplierRules.values():
        arOut.append("setrule %s 1 team 0 0 0" % vRule)
    arOut += ["maintained:", "set @counter ret"]

    # supply: reload every turret, replace lost guards (counted first: new units are only counted by
    # the team data on the next update, so a fetch right after a spawn would not see them)
    arOut.append("supply:")
    for vBlock, vAmmo, (vDx, vDy) in dtBot["turrets"]:
        arOut += ["op add x cx %d" % vDx, "op add y cy %d" % vDy, "getblock building b x y",
                  "setprop @%s b %d" % (vAmmo, dtBot["ammo"])]
    vGx, vGy = dtBot["guardSpot"]
    arOut += ["op add x cx %d" % vGx, "op add y cy %d" % vGy]
    for k, (vUnit, vCount) in enumerate(dtBot["guards"]):
        arOut += ["fetch unitCount u team 0 @%s" % vUnit, "op sub need %d u" % vCount,
                  "guard%d:" % k, "jump guarded%d lessThanEq need 0" % k,
                  "spawn @%s x y 90 team u true" % vUnit, "op sub need need 1",
                  "jump guard%d always 0 0" % k, "guarded%d:" % k]
    arOut.append("set @counter ret2")
    return "\n".join(arOut) + "\n"


def fnCheckProgram(sCode):
    """Static check of an mlog program as LParser reads it. Returns (problems, instruction count,
    {"block": set, "item": set, "unit": set} of content names used)."""
    arProblems = []
    arLines = []
    dtLabels = {}
    for vLineNo, vRaw in enumerate(sCode.split("\n"), 1):
        vLine = vRaw.split("#", 1)[0].strip()
        if not vLine:
            continue
        arTokens = vLine.split()
        if len(arTokens) == 1 and arTokens[0].endswith(":"):
            vLabel = arTokens[0][:-1]
            if vLabel in dtLabels:
                arProblems.append("line %d: label %s defined twice" % (vLineNo, vLabel))
            dtLabels[vLabel] = len(arLines)
            continue
        arLines.append((vLineNo, arTokens))
    if len(arLines) > cMaxInstructions:
        arProblems.append("%d instructions, over the parser's %d" % (len(arLines), cMaxInstructions))
    if len(dtLabels) > cMaxLabels:
        arProblems.append("%d labels, over the parser's %d" % (len(dtLabels), cMaxLabels))
    dtContent = {"block": set(), "item": set(), "unit": set()}
    for vLineNo, arTokens in arLines:
        vOp, arArgs = arTokens[0], arTokens[1:]
        if vOp not in cdtStatementArgs:
            arProblems.append("line %d: unknown statement %s" % (vLineNo, vOp))
            continue
        if len(arArgs) != cdtStatementArgs[vOp]:
            arProblems.append("line %d: %s takes %d fields, got %d" % (vLineNo, vOp, cdtStatementArgs[vOp], len(arArgs)))
            continue
        if vOp == "jump":
            if arArgs[0] not in dtLabels and not re.fullmatch(r"\d+", arArgs[0]):
                arProblems.append("line %d: jump to undefined label %s" % (vLineNo, arArgs[0]))
            if arArgs[1] not in carConditions:
                arProblems.append("line %d: unknown condition %s" % (vLineNo, arArgs[1]))
        elif vOp == "op" and arArgs[0] not in carLogicOps:
            arProblems.append("line %d: operator %s not in the checked set" % (vLineNo, arArgs[0]))
        elif vOp == "fetch" and arArgs[0] not in carFetchTypes:
            arProblems.append("line %d: unknown fetch type %s" % (vLineNo, arArgs[0]))
        elif vOp == "setrule" and arArgs[0] not in carTeamRules:
            arProblems.append("line %d: %s is not a team rule" % (vLineNo, arArgs[0]))
        elif vOp == "setblock":
            if arArgs[0] not in carSettableLayers:
                arProblems.append("line %d: layer %s cannot be set" % (vLineNo, arArgs[0]))
            dtContent["block"].add(arArgs[1].lstrip("@"))
        elif vOp == "getblock" and arArgs[0] not in carLayers:
            arProblems.append("line %d: unknown layer %s" % (vLineNo, arArgs[0]))
        elif vOp == "setprop":
            dtContent["item"].add(arArgs[0].lstrip("@"))
        elif vOp == "spawn":
            dtContent["unit"].add(arArgs[0].lstrip("@"))
        elif vOp == "fetch" and arArgs[4] != "@air":
            dtContent["unit"].add(arArgs[4].lstrip("@"))
    return arProblems, len(arLines), dtContent
