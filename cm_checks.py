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
"""

import json
import math

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
        print("  building: %s at (%d, %d), team %d" % (dtBuilding["block"], dtBuilding["x"], dtBuilding["y"],
                                                      dtBuilding["team"]))
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

    vCx, vCy = sResult.arCore
    vGoal = (vCy - 3) * vW + vCx
    arDist = sGrid.fnBfs(vGoal, fnWalkable)
    vOk = True
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
    vOk, arFloor, arWall, _ = _fnContent(dtInfo, sResult)
    vOk &= _fnFilters(dtInfo)
    vOk &= _fnPatches(dtInfo, arFloor, arWall)
    vOk &= _fnGround(sGrid, sResult, arFloor, arWall)
    vOk &= _fnNaval(sGrid, sResult, arFloor, arWall)
    print("\nAll checks passed." if vOk else "\nSome checks failed.")
    return bool(vOk)
