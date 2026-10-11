"""Shared verification of a written map, for any map type.

The map is decoded with the same region/length checks the game performs (msav.validate_msav), then:
  * content names, the spawn marks and the wave groups (pins on spawn tiles, boats only at naval spawns)
  * the in-game ore filters (genfilters tag) and the data patches, with thermal generators on all lava
  * ground routes from every spawn to the core
  * the layout's barrier tests: with its choke points closed, the far side must be out of reach under the
    game's own rule, where only walls and allDeep tiles stop ground units (a deep tile at a bank only
    costs more, so it does not count as closed)
  * naval spawns: the spawn ring is shallow liquid, and the boats' flow field brings them to rest within
    reach of the core
PvP maps (layout result sMatch "pvp") are checked for, instead of the single core:
  * one core per player slot, the PvP rules (attack mode, waves from the PvP wave team under the RTS AI)
  * the world processor of the defender bots: team, code that passes cm_bot's parser check, the cores it
    looks after, and a clear fortress square around every core
  * ground routes from every wave spawn to every base and between all bases, naval links between bases
  * resources: every base holds every floor resource, foreign ones as small pockets only
"""

import json
import math

import cm_bot
import cm_terrain
import msav
import ores
import sys_config
import waves

cSpawnSpread = 2.5        # WaveSpawner puts ground and naval units 2 tiles from the spawn tile
cNavalReach = 12.0        # tiles from the core centre where a resting boat counts as attacking the core


def _fnPlainName(vName):
    return vName[len(sys_config.cModPrefix):] if vName.startswith(sys_config.cModPrefix) else vName


def fnFlattenPatch(dtTree, vPrefix=""):
    """Data patch JSON -> {"block.thermal-generator.placeableLiquid": True, ...} (both syntaxes)."""
    dtOut = {}
    for vKey, vValue in dtTree.items():
        vPath = vPrefix + vKey
        if isinstance(vValue, dict):
            dtOut.update(fnFlattenPatch(vValue, vPath + "."))
        else:
            dtOut[vPath] = vValue
    return dtOut


def fnThermalOnLava(vWidth, vHeight, arFloor, arWall, dtPatched):
    """Every 2x2 thermal-generator spot fully on lava must be placeable (Build.validPlace +
    ThermalGenerator.canPlaceOn), apart from spots under walls or in the map's border darkness."""
    if dtPatched.get("block.thermal-generator.placeableLiquid") is not True:
        print("  FAIL: thermal generators only fit on the lava banks (missing placeableLiquid patch)")
        return False
    dtHeat = dict(sys_config.cdtFloorHeat)
    for vPath, vValue in dtPatched.items():
        arParts = vPath.split(".")
        if arParts[0] == "block" and arParts[2:] == ["attributes", "heat"]:
            dtHeat[_fnPlainName(arParts[1])] = vValue
    vSpots, vBlocked, vCold, arColdFloors = 0, 0, 0, set()
    for vY in range(vHeight - 1):
        for vX in range(vWidth - 1):
            arTiles = (vY * vWidth + vX, vY * vWidth + vX + 1, (vY + 1) * vWidth + vX, (vY + 1) * vWidth + vX + 1)
            if not all(arFloor[i] in sys_config.carLavaFloors for i in arTiles):
                continue
            vSpots += 1
            vSolid = any(arWall[i] is not None and arWall[i] not in sys_config.carNonSolidBlocks for i in arTiles)
            if vSolid or min(vX, vY, vWidth - 2 - vX, vHeight - 2 - vY) <= 2:      # World.getDarkness at the border
                vBlocked += 1
            elif sum(dtHeat.get(arFloor[i], 0.0) for i in arTiles) <= 0.0:
                vCold += 1
                arColdFloors.update(arFloor[i] for i in arTiles)
    print("  thermal generators on lava: %d of %d spots placeable (%d under walls or at the map edge)"
          % (vSpots - vBlocked - vCold, vSpots, vBlocked))
    if vCold:
        print("  FAIL: %d lava spots have no heat (%s)" % (vCold, ", ".join(sorted(arColdFloors))))
        return False
    return True


def _fnContent(dtInfo, sResult):
    """Names, spawn marks and wave groups. Returns (ok, floor, wall, rules)."""
    vWidth = dtInfo["width"]
    arNames = dtInfo["blocks"]
    arModContent = sorted(n for n in arNames if n.startswith(sys_config.cModPrefix))
    arUnprefixed = [n for n in arNames if n in sys_config.carModBlocks]
    arBlocks = [_fnPlainName(n) for n in arNames]
    arFloor = [arBlocks[k] for k in dtInfo["floors"]]
    arWall = [arBlocks[k] if k else None for k in dtInfo["walls"]]
    dtRules = json.loads(dtInfo["tags"]["rules"])
    arSpawnTiles = {(i % vWidth, i // vWidth) for i, k in enumerate(dtInfo["overlays"])
                    if k and arBlocks[k] == sys_config.cSpawnOverlay}
    print("Decoded %s: %dx%d, save version %d, %d block types, %d spawn points (%d on water), %d wave groups"
          % (dtInfo["tags"]["name"], vWidth, dtInfo["height"], dtInfo["version"], len(arBlocks), len(arSpawnTiles),
             len(sResult.arNavalSpawnKeys), len(dtRules["spawns"])))
    for dtBuilding in dtInfo["buildings"]:
        print("  building: %s at (%d, %d), team %d%s" % (dtBuilding["block"], dtBuilding["x"], dtBuilding["y"],
                                                        dtBuilding["team"], " (%d bytes of code, %s ipt)"
                                                        % (len(dtBuilding["code"]), dtBuilding["ipt"])
                                                        if "code" in dtBuilding else ""))
    print("  Exogenesis Old terrain used: " + ", ".join(arModContent))
    vOk = True
    if arUnprefixed:
        print("  FAIL: mod blocks without the '%s' prefix: %s" % (sys_config.cModPrefix, arUnprefixed))
        vOk = False
    arBaked = sorted({arBlocks[k] for k in dtInfo["overlays"] if k} - {sys_config.cSpawnOverlay})
    if arBaked:
        print("  FAIL: ores baked into the map (they would not change between games): %s" % arBaked)
        vOk = False
    if arSpawnTiles != set(sResult.dtSpawns.values()):
        print("  FAIL: spawn marks %s differ from the layout's spawns" % sorted(arSpawnTiles))
        vOk = False
    arUnits = sorted({g["type"] for g in dtRules["spawns"]})
    print("  wave unit types: %d (%d from Exogenesis Old), rules JSON %d bytes"
          % (len(arUnits), sum(1 for u in arUnits if u.startswith(sys_config.cModPrefix)), len(dtInfo["tags"]["rules"])))
    if len(dtInfo["tags"]["rules"].encode("utf-8")) > 65535:
        print("  FAIL: rules JSON is over the 65,535-byte writeUTF limit")
        vOk = False
    dtPins = {}
    for g in dtRules["spawns"]:
        if "spawn" in g:
            dtPins.setdefault(g["type"], set()).add(((g["spawn"] >> 16) & 0xFFFF, g["spawn"] & 0xFFFF))
    if any(not arPos <= arSpawnTiles for arPos in dtPins.values()):
        print("  FAIL: a wave group is pinned to a tile without a spawn mark")
        vOk = False
    arNavalTiles = {sResult.dtSpawns[k] for k in sResult.arNavalSpawnKeys}
    for g in dtRules["spawns"]:
        if g["type"] not in waves.cdtNavalSwap:
            continue
        vAt = ((g["spawn"] >> 16) & 0xFFFF, g["spawn"] & 0xFFFF) if "spawn" in g else None
        if vAt not in arNavalTiles:
            print("  FAIL: naval %s would spawn on dry ground (%s)" % (g["type"], vAt or "every spawn"))
            vOk = False
    return vOk, arFloor, arWall, dtRules


def _fnFilters(dtInfo):
    arFilters = json.loads(dtInfo["tags"].get("genfilters") or "[]")
    if not arFilters:
        print("  FAIL: no genfilters; the game would scatter its default ores instead")
        return False
    arPlain = []
    for f in arFilters:
        g = dict(f)
        for vKey in ("ore", "target", "floor", "block"):
            if vKey in g:
                g[vKey] = _fnPlainName(g[vKey])
                if g[vKey] in sys_config.carModBlocks and not f[vKey].startswith(sys_config.cModPrefix):
                    print("  FAIL: filter uses mod block %s without the prefix" % g[vKey])
                    return False
        arPlain.append(g)
    arProblems = ores.check_filters(arPlain, sys_config.carModBlocks)
    arKinds = sorted({f["ore"] for f in arPlain if f["class"] == "ore" and f["ore"] != "air"})
    print("  in-game ore filters: %d (%d ores + siratla crystal), re-rolled on every load" % (len(arFilters), len(arKinds)))
    for vProblem in arProblems:
        print("  FAIL: " + vProblem)
    return not arProblems


def _fnPatches(dtInfo, arFloor, arWall):
    dtPatched = {}
    for dtAsset in dtInfo["patches"]:
        dtBody = {k: v for k, v in json.loads(dtAsset["text"]).items() if k != "name"}
        print("  data patch %s: %s" % (dtAsset["path"], json.dumps(dtBody)))
        dtPatched.update(fnFlattenPatch(dtBody))
    return fnThermalOnLava(dtInfo["width"], dtInfo["height"], arFloor, arWall, dtPatched)


def _fnGround(sGrid, sResult, arFloor, arWall):
    """Ground routes and barrier tests."""
    vW = sGrid.vWidth
    arSolid = bytearray(1 if w is not None and w not in sys_config.carNonSolidBlocks else 0 for w in arWall)
    arAllDeep = sGrid.fnAllDeep(arFloor, sys_config.carDeepFloors)

    def fnWalkable(i):           # what units really walk on: no wall, no deep liquid
        return not arSolid[i] and arFloor[i] not in sys_config.carDeepFloors

    def fnPathable(i):           # what the pathfinder lets them try: no wall, not allDeep
        return not arSolid[i] and not arAllDeep[i]

    vOk = True
    if sResult.sMatch == "pvp":
        vOk &= _fnGroundPvp(sGrid, sResult, fnWalkable)
    else:
        vCx, vCy = sResult.arCore
        vGoal = (vCy - 3) * vW + vCx
        arDist = sGrid.fnBfs(vGoal, fnWalkable)
        print("\nGround routes (spawn -> core):")
        for vKey, (vSx, vSy) in sResult.dtSpawns.items():
            vSteps = arDist[vSy * vW + vSx]
            vOk &= vSteps >= 0
            print("  %-34s %s" % (sResult.dtSpawnLabels[vKey], "%d tiles" % vSteps if vSteps >= 0 else "FAIL: no route"))
    if not sResult.arBarrierTests:
        return vOk
    print("\nBarrier tests (enemy side -> core side; closed = walls and allDeep only):")
    for dtTest in sResult.arBarrierTests:
        arClosed = set()
        for vName in dtTest["names"]:
            vMx, vMy = sResult.dtMarkers[vName]
            arClosed.update(i for i, _ in sGrid.fnDisc(vMx, vMy, dtTest["radius"]))
        fnInside = dtTest.get("region") or (lambda j: True)
        vStart = dtTest["start"][1] * vW + dtTest["start"][0]
        vEnd = dtTest["goal"][1] * vW + dtTest["goal"][0]
        vOpen = sGrid.fnBfs(vStart, lambda j: fnWalkable(j) and fnInside(j))[vEnd] >= 0
        vLeak = sGrid.fnBfs(vStart, lambda j: j not in arClosed and fnPathable(j) and fnInside(j))[vEnd] >= 0
        vGood = vOpen and not vLeak
        vOk &= vGood
        print("  %-26s crossings open: %-9s crossings closed: %-9s %s"
              % (dtTest["label"], "reachable" if vOpen else "BLOCKED", "LEAKS" if vLeak else "sealed",
                 "OK" if vGood else "FAIL  <- " + ", ".join(dtTest["names"])))
    return vOk


def _fnGroundPvp(sGrid, sResult, fnWalkable):
    """Every wave spawn reaches every base (the RTS AI may send a squad anywhere), every base every other."""
    vW = sGrid.vWidth
    vOk = True
    arGoals = [((d["y"] - 3) * vW + d["x"], d) for d in sResult.arTeamCores]
    print("\nGround routes (wave spawn -> every base):")
    for vKey, (vSx, vSy) in sResult.dtSpawns.items():
        arDist = sGrid.fnBfs(vSy * vW + vSx, fnWalkable)
        arSteps = [(d["label"], arDist[g]) for g, d in arGoals]
        vGood = all(v >= 0 for _, v in arSteps)
        vOk &= vGood
        print("  %-30s %s  %s" % (sResult.dtSpawnLabels[vKey], ", ".join("%s %s" % (k, v if v >= 0 else "none")
                                                                        for k, v in arSteps), "OK" if vGood else "FAIL"))
    print("\nGround routes between bases:")
    for vGoal, d in arGoals:
        arDist = sGrid.fnBfs(vGoal, fnWalkable)
        arSteps = [(e["label"], arDist[g]) for g, e in arGoals if e is not d]
        vGood = all(v >= 0 for _, v in arSteps)
        vOk &= vGood
        print("  %-30s %s  %s" % (d["label"], ", ".join("%s %s" % (k, v if v >= 0 else "none") for k, v in arSteps),
                                  "OK" if vGood else "FAIL"))
    return vOk


def _fnPvp(dtInfo, sGrid, sResult, arFloor, arWall, dtRules):
    """Cores, PvP rules, the defender bots' processor and fortress squares, resources per base."""
    vW, vH = sGrid.vWidth, sGrid.vHeight
    vOk = True
    print("\nPvP setup:")
    arCores = sorted((b["team"], b["x"], b["y"]) for b in dtInfo["buildings"] if b["block"] == sys_config.cCoreBlock)
    arWanted = sorted((d["team"], d["x"], d["y"]) for d in sResult.arTeamCores)
    vGood = arCores == arWanted
    vOk &= vGood
    print("  cores: %s  %s" % (", ".join("team %d at (%d, %d)" % c for c in arCores), "OK" if vGood else "FAIL"))
    vWave = dtRules.get("waveTeam")
    dtWaveRules = dtRules.get("teams", {}).get(str(vWave), {})
    vGood = (dtRules.get("pvp") is True and dtRules.get("attackMode") is True and dtRules.get("waves") is True
             and vWave == sys_config.cPvpWaveTeam and dtWaveRules.get("rtsAi") is True
             and dtRules.get("airUseSpawns") is True and vWave not in [d["team"] for d in sResult.arTeamCores])
    vOk &= vGood
    print("  rules: pvp %s, attack mode %s, waves %s, wave team %s with RTS AI %s, flyers from the spawns %s  %s"
          % (dtRules.get("pvp"), dtRules.get("attackMode"), dtRules.get("waves"), vWave, dtWaveRules.get("rtsAi"),
             dtRules.get("airUseSpawns"), "OK" if vGood else "FAIL"))

    arLogic = [b for b in dtInfo["buildings"] if b["block"] == sys_config.cWorldProcessor]
    if len(arLogic) != 1:
        print("  FAIL: %d world processors (want 1)" % len(arLogic))
        return False
    dtLogic = arLogic[0]
    arProblems, vInstructions, dtContent = cm_bot.fnCheckProgram(dtLogic["code"])
    arLines = [v.strip() for v in dtLogic["code"].split("\n")]
    dtTeamNames = {vId: vName for vName, vId in sys_config.cdtPvpTeams.items()}
    for d in sResult.arTeamCores:
        arBlock = ["set team @%s" % dtTeamNames[d["team"]], "set cx %d" % d["x"], "set cy %d" % d["y"]]
        vFound = sum(1 for k in range(len(arLines) - 2) if arLines[k:k + 3] == arBlock)
        if vFound != 2:
            arProblems.append("the %s core is looked after %d times (want 2: decide, maintain)" % (d["label"], vFound))
    if dtLogic["team"] != sys_config.cPvpWaveTeam:
        arProblems.append("processor team %d, want %d (derelict buildings never update)" % (dtLogic["team"], sys_config.cPvpWaveTeam))
    vGood = not arProblems
    vOk &= vGood
    print("  defender bots: world processor at (%d, %d), team %d, %d instructions, %d ipt, builds %s, loads %s, "
          "guards %s  %s" % (dtLogic["x"], dtLogic["y"], dtLogic["team"], vInstructions, dtLogic["ipt"],
                             ", ".join(sorted(dtContent["block"])), ", ".join(sorted(dtContent["item"])),
                             ", ".join(sorted(dtContent["unit"])), "OK" if vGood else "FAIL"))
    for vProblem in arProblems:
        print("  FAIL: " + vProblem)

    vKeep = sys_config.cBotKeep
    for d in sResult.arTeamCores:
        vMx, vMy = d["x"] + 0.5, d["y"] + 0.5
        vBad = 0
        for vY in range(int(vMy - vKeep), int(vMy + vKeep) + 1):
            for vX in range(int(vMx - vKeep), int(vMx + vKeep) + 1):
                if not (0 <= vX < vW and 0 <= vY < vH):
                    vBad += 1
                    continue
                i = vY * vW + vX
                if d["x"] - 1 <= vX <= d["x"] + 2 and d["y"] - 1 <= vY <= d["y"] + 2:
                    continue                                   # the core itself
                if ((arWall[i] is not None and arWall[i] not in sys_config.carNonSolidBlocks)
                        or arFloor[i] in sys_config.carLiquidFloors):
                    vBad += 1
        vOk &= vBad == 0
        print("  fortress square of %-22s %s" % (d["label"], "clear  OK" if vBad == 0 else "%d blocked tiles  FAIL" % vBad))

    dtRes = sResult.dtResourceRules
    if dtRes:
        arShared = dtRes.get("sharedRange", (1, dtRes["pocketCap"]))
        print("\nResources per base (usable tiles; home groups need %d+, foreign groups 1..%d, groups without a "
              "home %d..%d):" % (dtRes["homeMin"], dtRes["pocketCap"], arShared[0], arShared[1]))
        dtCount = {}
        for i, vRegion in enumerate(sResult.arRegion):
            if arWall[i] is not None and arWall[i] not in sys_config.carNonSolidBlocks:
                continue                                       # under a wall: never seen, mined or pumped
            vFloor = arFloor[i]
            for vGroup, arMembers in sys_config.cdtResourceFloors.items():
                if vFloor in arMembers:
                    dtCount[(vRegion, vGroup)] = dtCount.get((vRegion, vGroup), 0) + 1
        for vRegion in dtRes["bases"]:
            arParts, vGood = [], True
            for vGroup in sys_config.cdtResourceFloors:
                vTiles = dtCount.get((vRegion, vGroup), 0)
                vHome = dtRes["homes"][vGroup] == vRegion
                if dtRes["homes"][vGroup] is None:
                    vFits = arShared[0] <= vTiles <= arShared[1]
                else:
                    vFits = vTiles >= dtRes["homeMin"] if vHome else 1 <= vTiles <= dtRes["pocketCap"]
                vGood &= vFits
                arParts.append("%s%s %d%s" % ("*" if vHome else "", vGroup.split(" ")[0], vTiles, "" if vFits else "!"))
            vOk &= vGood
            print("  %-20s %s  %s" % (sResult.arRegionNames[vRegion], ", ".join(arParts), "OK" if vGood else "FAIL"))
    return vOk


def _fnNavalLinks(sGrid, sResult, arFloor, arWall):
    """PvP naval links: boats from each link's start come to rest within reach of that base's core."""
    if not sResult.arNavalLinks:
        return True
    vW = sGrid.vWidth
    arCost = sGrid.fnNavalCosts(arFloor, arWall)
    vOffset = 0.5 if sys_config.cCoreSize % 2 == 0 else 0.0
    vOk = True
    print("\nNaval links (boats follow the naval flow field toward a base):")
    for dtLink in sResult.arNavalLinks:
        vCx, vCy = dtLink["core"]
        arField = sGrid.fnFlowField(vCy * vW + vCx, arCost)
        vSx, vSy = dtLink["start"]
        arPath = sGrid.fnNavalStop(vSy * vW + vSx, arField, arCost)
        vRest = arPath[-1]
        vReach = math.hypot(vRest % vW - vCx - vOffset, vRest // vW - vCy - vOffset)
        vLimit = dtLink.get("reach", cNavalReach)
        vGood = arFloor[vSy * vW + vSx] in sys_config.carLiquidFloors and vReach <= vLimit
        vOk &= vGood
        print("  %-40s %4d tiles along the flow field, rests %.1f tiles from the core (%g allowed)  %s"
              % (dtLink["label"], len(arPath) - 1, vReach, vLimit, "OK" if vGood else "FAIL"))
    return vOk


def _fnNaval(sGrid, sResult, arFloor, arWall):
    """Naval spawns: shallow liquid under the spawn ring, and a resting place within reach of the core."""
    if not sResult.arNavalSpawnKeys:
        return True
    vW = sGrid.vWidth
    arCost = sGrid.fnNavalCosts(arFloor, arWall)
    vCx, vCy = sResult.arCore
    arField = sGrid.fnFlowField(vCy * vW + vCx, arCost)
    vCoreX = vCx + (0.5 if sys_config.cCoreSize % 2 == 0 else 0.0)
    vCoreY = vCy + (0.5 if sys_config.cCoreSize % 2 == 0 else 0.0)
    vOk = True
    print("\nNaval routes (boats follow the naval flow field toward the core):")
    for vKey in sResult.arNavalSpawnKeys:
        vSx, vSy = sResult.dtSpawns[vKey]
        arRing = [arFloor[i] for i, _ in sGrid.fnDisc(vSx, vSy, cSpawnSpread)]
        vDry = sum(1 for f in arRing if f not in sys_config.carLiquidFloors)
        vDeep = sum(1 for f in arRing if f in sys_config.carDeepFloors)
        arPath = sGrid.fnNavalStop(vSy * vW + vSx, arField, arCost)
        vRest = arPath[-1]
        vReach = math.hypot(vRest % vW - vCoreX, vRest // vW - vCoreY)
        vGood = vDry == 0 and vDeep == 0 and vReach <= cNavalReach
        vOk &= vGood
        print("  %-34s %4d tiles along the flow field, rests %.1f tiles from the core, spawn ring %s  %s"
              % (sResult.dtSpawnLabels[vKey], len(arPath) - 1, vReach,
                 "shallow" if not (vDry or vDeep) else "%d dry / %d deep tiles" % (vDry, vDeep),
                 "OK" if vGood else "FAIL"))
    return vOk


def fnCheckMap(vMapPath, sResult):
    """Runs every shared check on the written map; True when all pass."""
    dtInfo = msav.validate_msav(vMapPath)
    sGrid = cm_terrain.clGrid(dtInfo["width"], dtInfo["height"])
    vOk, arFloor, arWall, dtRules = _fnContent(dtInfo, sResult)
    vOk &= _fnFilters(dtInfo)
    vOk &= _fnPatches(dtInfo, arFloor, arWall)
    if sResult.sMatch == "pvp":
        vOk &= _fnPvp(dtInfo, sGrid, sResult, arFloor, arWall, dtRules)
    vOk &= _fnGround(sGrid, sResult, arFloor, arWall)
    vOk &= _fnNaval(sGrid, sResult, arFloor, arWall)
    vOk &= _fnNavalLinks(sGrid, sResult, arFloor, arWall)
    print("\nAll checks passed." if vOk else "\nSome checks failed.")
    return bool(vOk)
