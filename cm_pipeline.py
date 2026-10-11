"""Shared generation pipeline: turns any layout into a finished map.

    layout.fnBuild -> result checks -> ore filters + simulated rolls -> statistics -> ground and naval
    routes -> block table, tags, rules (waves) -> .msav + re-decode -> preview and routes PNGs -> report
    -> layout.fnCheck (the shared checks unless the layout brings its own)

Nothing here depends on a particular layout: every map type runs through the same steps with the same
shared configuration (sys_config), ore filters (ores), spawn groups (waves) and writer (msav). The chosen
difficulty (sys_config.cdtDifficulties) changes the waves, the match rules and the map's name only (and,
on a PvP map, the strength of the defender bots).

A PvP layout (result sMatch "pvp") gets one core per player slot, the PvP rules (waves from the PvP wave
team under the RTS AI) and the world processor that runs the defender bots (cm_bot).
"""

import json
import math
import os
import time

import cm_bot
import cm_render
import cm_terrain
import msav
import ores
import sys_config
import waves

cReportWaves = (1, 10, 20, 30, 40, 50, 60, 75, 90, 100, 120, 150, 200, 250, 300)
cCurve = (1, 310, 10)      # first wave, last wave, window of the difficulty curve in the report
cRouteSlack = 0.02         # near-shortest corridors: routes up to 2% (+4 tiles) longer than the best
cProcessorTile = (1, 1)    # world processor of a PvP map: inside the dark map border, out of everyone's way


def _vsValidateResult(sResult):
    """Refuses a layout result the rest of the pipeline could not write correctly."""
    vTiles = sResult.vWidth * sResult.vHeight
    for vName in ("arFloor", "arOverlay", "arWall", "arRegion"):
        if len(getattr(sResult, vName)) != vTiles:
            raise ValueError("%s has %d entries for %d tiles" % (vName, len(getattr(sResult, vName)), vTiles))
    arMarks = {(i % sResult.vWidth, i // sResult.vWidth) for i, o in enumerate(sResult.arOverlay) if o}
    if {o for o in sResult.arOverlay if o} - {sys_config.cSpawnOverlay}:
        raise ValueError("Only spawn marks may be written as overlays; ores come from the shared filters")
    if arMarks != set(sResult.dtSpawns.values()):
        raise ValueError("Spawn marks %s do not match dtSpawns" % sorted(arMarks))
    for vKey in sResult.dtSpawns:
        if vKey not in sResult.dtSpawnLabels or vKey not in sResult.dtRouteColors:
            raise ValueError("Spawn '%s' needs a label and a route colour" % vKey)
    if not set(sResult.arNavalSpawnKeys) <= set(sResult.dtSpawns):
        raise ValueError("Naval spawn keys must be spawn keys")
    if max(sResult.arRegion) >= len(sResult.arRegionNames):
        raise ValueError("A region index has no name")
    vCx, vCy = sResult.arCore
    if not (0 <= vCx < sResult.vWidth and 0 <= vCy < sResult.vHeight):
        raise ValueError("The core lies outside the map")
    if sResult.sMatch not in ("survival", "pvp"):
        raise ValueError("Unknown match type '%s'" % sResult.sMatch)
    if sResult.sMatch == "pvp":
        arTeams = [d["team"] for d in sResult.arTeamCores]
        if (len(arTeams) < 2 or len(set(arTeams)) != len(arTeams)
                or not set(arTeams) <= set(sys_config.cdtPvpTeams.values())):
            raise ValueError("A PvP map needs cores of 2+ different player teams %s"
                             % sorted(sys_config.cdtPvpTeams.values()))
        for d in sResult.arTeamCores:
            if not (sys_config.cBotKeep < d["x"] < sResult.vWidth - sys_config.cBotKeep - 1
                    and sys_config.cBotKeep < d["y"] < sResult.vHeight - sys_config.cBotKeep - 1):
                raise ValueError("The %s core is too close to the map edge for a bot fortress" % d["label"])


def _fnRollOres(sResult, vSeed, vOreRolls):
    """Runs the shared ore filters the way the game does on every load. Nothing here is written to the
    map; the first roll feeds the preview and all rolls feed the report."""
    arFilters = ores.build_filters(sys_config.carModBlocks)
    arProblems = ores.check_filters(arFilters, sys_config.carModBlocks)
    assert not arProblems, arProblems
    arOpen = [i for i, w in enumerate(sResult.arWall) if w is None or w in sys_config.carNonSolidBlocks]
    arRolls, arPreview = [], None
    for sRng in ores.roll_seeds(vSeed, vOreRolls):
        arFloor, arOverlay = ores.roll(arFilters, sResult.vWidth, sResult.arFloor, sResult.arOverlay, arOpen,
                                       sys_config.carLiquidFloors, sRng)
        if arPreview is None:
            arPreview = (arFloor, arOverlay)
        arRolls.append(ores.measure(sResult.vWidth, sResult.vHeight, arFloor, arOverlay, sResult.arRegion,
                                    sResult.arRegionNames))
    return arFilters, arRolls, arPreview


def _fnWalkable(sResult):
    """Ground passability used for routes: no solid wall, no deep liquid."""
    arFloor, arWall = sResult.arFloor, sResult.arWall
    return lambda i: ((arWall[i] is None or arWall[i] in sys_config.carNonSolidBlocks)
                      and arFloor[i] not in sys_config.carDeepFloors)


def _fnCorridor(sGrid, sResult, arFromStart, arFromEnd, vEnd):
    """Every tile on a near-shortest route between two BFS fields, and the choke points along it.
    Mindustry's flow field uses 4-way steps, so many staircase routes tie; the corridor shows them all."""
    vBest = arFromStart[vEnd]
    vLimit = vBest * (1.0 + cRouteSlack) + 4
    arTiles = bytearray(sGrid.vTiles)
    for i in range(sGrid.vTiles):
        vA, vB = arFromStart[i], arFromEnd[i]
        if vA >= 0 and vB >= 0 and vA + vB <= vLimit:
            arTiles[i] = 1
    arHits = []
    for vName, (vMx, vMy) in sResult.dtMarkers.items():
        arReach = [arFromStart[j] for j, _ in sGrid.fnDisc(vMx, vMy, 20.0) if arTiles[j]]
        if arReach:
            arHits.append((min(arReach), vName))
    return vBest, [vName for _, vName in sorted(arHits)], arTiles


def _fnRoutesPvp(sGrid, sResult):
    """PvP: each wave spawn's corridor to the base it faces (its key; the RTS AI may pick any base), the
    distances between the bases, and the water of every naval link."""
    vW = sGrid.vWidth
    fnWalkable = _fnWalkable(sResult)
    dtFromCore = {}
    for d in sResult.arTeamCores:
        dtFromCore[d["team"]] = sGrid.fnBfs((d["y"] - 3) * vW + d["x"], fnWalkable)
    dtCorridors, dtRoutes = {}, {}
    for vKey, (vSx, vSy) in sResult.dtSpawns.items():
        arFromSpawn = sGrid.fnBfs(vSy * vW + vSx, fnWalkable)
        arFaced = [d for d in sResult.arTeamCores if d["key"] == vKey] or sResult.arTeamCores
        dtCore = min(arFaced, key=lambda d: (d["x"] - vSx) ** 2 + (d["y"] - vSy) ** 2)
        vGoal = (dtCore["y"] - 3) * vW + dtCore["x"]
        vLength, arHits, arTiles = _fnCorridor(sGrid, sResult, arFromSpawn, dtFromCore[dtCore["team"]], vGoal)
        dtCorridors[vKey] = (vLength, arHits, arTiles)
        dtRoutes[sResult.dtSpawnLabels[vKey]] = {
            "toward": dtCore["label"], "straight_line_tiles": round(math.hypot(dtCore["x"] - vSx, dtCore["y"] - vSy), 1),
            "shortest_ground_path_tiles": vLength,
            "choke_points_on_near_shortest_routes": arHits,
            "ground_path_tiles_to_every_base": {d["label"]: arFromSpawn[(d["y"] - 3) * vW + d["x"]]
                                                for d in sResult.arTeamCores}}
    dtBases = {}
    for d in sResult.arTeamCores:
        arField = dtFromCore[d["team"]]
        dtBases[d["label"]] = {e["label"]: {"ground_path_tiles": arField[(e["y"] - 3) * vW + e["x"]],
                                            "straight_line_tiles": round(math.hypot(e["x"] - d["x"], e["y"] - d["y"]), 1)}
                               for e in sResult.arTeamCores if e is not d}
    dtNavalCorridors, dtNavalRoutes = {}, {}
    if sResult.arNavalLinks:
        arCost = sGrid.fnNavalCosts(sResult.arFloor, sResult.arWall)

        def fnSailable(i):
            return arCost[i] < cm_terrain.cNavalDryCost

        vOffset = 0.5 if sys_config.cCoreSize % 2 == 0 else 0.0
        for dtLink in sResult.arNavalLinks:
            vCx, vCy = dtLink["core"]
            arField = sGrid.fnFlowField(vCy * vW + vCx, arCost)
            vSx, vSy = dtLink["start"]
            arSailed = sGrid.fnNavalStop(vSy * vW + vSx, arField, arCost)
            vRest = arSailed[-1]
            arFromStart = sGrid.fnBfs(vSy * vW + vSx, fnSailable)
            arFromRest = sGrid.fnBfs(vRest, fnSailable)
            vLength, arHits, arTiles = _fnCorridor(sGrid, sResult, arFromStart, arFromRest, vRest)
            dtNavalCorridors[dtLink["label"]] = (vLength, arHits, arTiles)
            dtNavalRoutes[dtLink["label"]] = {
                "flow_field_path_tiles": len(arSailed) - 1, "shortest_water_path_tiles": vLength,
                "rests_at": [vRest % vW, vRest // vW],
                "rest_tiles_from_core": round(math.hypot(vRest % vW - vCx - vOffset, vRest // vW - vCy - vOffset), 1),
                "choke_points_on_route": arHits}
    return dtCorridors, dtRoutes, dtNavalCorridors, dtNavalRoutes, dtBases


def _fnRoutes(sGrid, sResult):
    """Near-shortest ground corridor of every spawn, and the water every naval spawn's boats sail."""
    vW = sGrid.vWidth
    vCx, vCy = sResult.arCore
    vGoal = (vCy - 3) * vW + vCx
    fnWalkable = _fnWalkable(sResult)
    arFromCore = sGrid.fnBfs(vGoal, fnWalkable)
    dtCorridors, dtRoutes = {}, {}
    for vKey, (vSx, vSy) in sResult.dtSpawns.items():
        arFromSpawn = sGrid.fnBfs(vSy * vW + vSx, fnWalkable)
        vLength, arHits, arTiles = _fnCorridor(sGrid, sResult, arFromSpawn, arFromCore, vGoal)
        dtCorridors[vKey] = (vLength, arHits, arTiles)
        dtRoutes[sResult.dtSpawnLabels[vKey]] = {"shortest_ground_path_tiles": vLength,
                                                 "choke_points_on_near_shortest_routes": arHits}
    dtNavalCorridors, dtNavalRoutes = {}, {}
    if sResult.arNavalSpawnKeys:
        arCost = sGrid.fnNavalCosts(sResult.arFloor, sResult.arWall)
        arField = sGrid.fnFlowField(vCy * vW + vCx, arCost)

        def fnSailable(i):
            return arCost[i] < cm_terrain.cNavalDryCost

        vCoreX = vCx + (0.5 if sys_config.cCoreSize % 2 == 0 else 0.0)
        vCoreY = vCy + (0.5 if sys_config.cCoreSize % 2 == 0 else 0.0)
        for vKey in sResult.arNavalSpawnKeys:
            vSx, vSy = sResult.dtSpawns[vKey]
            arSailed = sGrid.fnNavalStop(vSy * vW + vSx, arField, arCost)
            vRest = arSailed[-1]
            arFromSpawn = sGrid.fnBfs(vSy * vW + vSx, fnSailable)
            arFromRest = sGrid.fnBfs(vRest, fnSailable)
            vLength, arHits, arTiles = _fnCorridor(sGrid, sResult, arFromSpawn, arFromRest, vRest)
            dtNavalCorridors[vKey] = (vLength, arHits, arTiles)
            dtNavalRoutes[sResult.dtSpawnLabels[vKey]] = {
                "flow_field_path_tiles": len(arSailed) - 1, "shortest_water_path_tiles": vLength,
                "rests_at": [vRest % vW, vRest // vW],
                "rest_tiles_from_core": round(((vRest % vW - vCoreX) ** 2 + (vRest // vW - vCoreY) ** 2) ** 0.5, 1),
                "choke_points_on_route": arHits}
    return dtCorridors, dtRoutes, dtNavalCorridors, dtNavalRoutes


def _fnStatistics(sResult):
    """Terrain written to the map (ores and siratla crystal are rolled in-game, see _fnOreStatistics)."""
    arNames = sResult.arRegionNames
    arTiles, arOpen = [0] * len(arNames), [0] * len(arNames)
    dtResources = {}
    fnWalkable = _fnWalkable(sResult)
    for i, vRegion in enumerate(sResult.arRegion):
        arTiles[vRegion] += 1
        if fnWalkable(i):
            arOpen[vRegion] += 1
        vFloor = sResult.arFloor[i]
        for vGroup, arMembers in sys_config.cdtResourceFloors.items():
            if vFloor in arMembers:
                dtResources.setdefault(arNames[vRegion], {}).setdefault(vGroup, 0)
                dtResources[arNames[vRegion]][vGroup] += 1
    return {
        "biome_tiles": {arNames[k]: arTiles[k] for k in range(len(arNames))},
        "walkable_tiles": {arNames[k]: arOpen[k] for k in range(len(arNames))},
        "special_floors": dtResources,
    }


def _fnOreStatistics(arRolls, arRegionNames):
    """Averages over the simulated rolls: patches (6+ tiles) and ore tiles per region, patch sizes."""
    vRolls = len(arRolls)
    dtTiles, dtCount, arSizes = {}, {}, []
    for dtRollTiles, dtRollCount, arRollSizes in arRolls:
        for dtTotal, dtPart in ((dtTiles, dtRollTiles), (dtCount, dtRollCount)):
            for vRegion, dtKinds in dtPart.items():
                for vKind, vValue in dtKinds.items():
                    dtTotal.setdefault(vRegion, {}).setdefault(vKind, 0)
                    dtTotal[vRegion][vKind] += vValue / vRolls
        arSizes += arRollSizes
    arSizes.sort()

    def fnTidy(dtTable):
        return {r: dict(sorted(((k, round(v)) for k, v in dtTable.get(r, {}).items()), key=lambda kv: -kv[1]))
                for r in arRegionNames}

    return {
        "rolls": vRolls,
        "patches_per_game": round(len(arSizes) / vRolls),
        "patch_tiles": {"median": arSizes[len(arSizes) // 2], "p10": arSizes[len(arSizes) // 10],
                        "p90": arSizes[len(arSizes) * 9 // 10], "smallest_counted": 6},
        "patches_per_biome": {r: round(sum(dtCount.get(r, {}).values())) for r in arRegionNames},
        "patches": fnTidy(dtCount),
        "ore_tiles": fnTidy(dtTiles),
    }


def _fnBlockTable(sResult):
    arUsed = (set(sResult.arFloor) | {o for o in sResult.arOverlay if o} | {w for w in sResult.arWall if w}
              | {sys_config.cCoreBlock})
    if sResult.sMatch == "pvp":
        arUsed.add(sys_config.cWorldProcessor)
    arTable = list(msav.RUNTIME_BLOCK_PREFIX)
    arTable += sorted(arUsed - set(arTable))
    return arTable


def _fnTags(sResult, vMapName, vDescription, dtRules, arFilters):
    vCx, vCy = sResult.arCore
    return {
        "name": vMapName, "author": sys_config.cMapAuthor, "description": vDescription,
        "rules": json.dumps(dtRules, separators=(",", ":")),
        "width": str(sResult.vWidth), "height": str(sResult.vHeight), "build": sys_config.cGameBuild,
        "saved": str(int(time.time() * 1000)),
        "playtime": "0", "mapname": vMapName, "wave": "1", "tick": "0.0", "wavetime": "0.0",
        "stats": "{}", "locales": "{}", "mods": "[]", "controlGroups": "null",
        "viewpos": "(%.1f,%.1f)" % (vCx * 8 + 4, vCy * 8 + 4),
        "controlledType": "null", "nocores": "false", "playerteam": "1", "hasExternalAssets": "false",
        "sectorPreset": "", "genfilters": ores.to_json(arFilters, sys_config.fnFileBlockName),
    }


def _fnWriteMap(sResult, vPath, arTable, dtTags, sProgram=None):
    """Writes the .msav and re-decodes it with the game's own region checks. `sProgram` is the defender
    bots' code of a PvP map, written into a world processor."""
    dtIndex = {vName: k for k, vName in enumerate(arTable)}
    arFloors = [dtIndex[f] for f in sResult.arFloor]
    arOverlays = [dtIndex[o] if o else 0 for o in sResult.arOverlay]
    arWalls = [dtIndex[w] if w else 0 for w in sResult.arWall]
    arBuildings = [{"x": d["x"], "y": d["y"], "size": sys_config.cCoreSize, "block": dtIndex[sys_config.cCoreBlock],
                    "chunk": msav.core_chunk(d["team"])} for d in sResult.fnCores()]
    if sProgram is not None:
        arBuildings.append({"x": cProcessorTile[0], "y": cProcessorTile[1], "size": 1,
                            "block": dtIndex[sys_config.cWorldProcessor],
                            "chunk": msav.fnLogicChunk(sProgram, sys_config.cPvpWaveTeam,
                                                       sys_config.cdtBotRules["ipt"])})
    arFileTable = [sys_config.fnFileBlockName(vName) for vName in arTable]
    vRawSize, vFileSize = msav.write_msav(vPath, sResult.vWidth, sResult.vHeight, arFileTable, arFloors,
                                          arOverlays, arWalls, arBuildings, dtTags, sys_config.carDataPatches)
    dtCheck = msav.validate_msav(vPath, known_blocks=set(arFileTable))
    assert dtCheck["blocks"] == arFileTable
    assert dtCheck["width"] == sResult.vWidth and dtCheck["height"] == sResult.vHeight
    assert [arTable[k] for k in dtCheck["floors"]] == sResult.arFloor
    assert all((arTable[k] if k else None) == (o if o else None) for k, o in zip(dtCheck["overlays"], sResult.arOverlay))
    assert {arTable[k] for k in dtCheck["overlays"] if k} == {sys_config.cSpawnOverlay}
    arCores = [b for b in dtCheck["buildings"] if b["block"] == sys_config.cCoreBlock]
    assert (sorted((b["x"], b["y"], b["team"]) for b in arCores)
            == sorted((d["x"], d["y"], d["team"]) for d in sResult.fnCores()))
    arLogic = [b for b in dtCheck["buildings"] if b["block"] == sys_config.cWorldProcessor]
    assert len(arCores) + len(arLogic) == len(dtCheck["buildings"])
    if sProgram is None:
        assert not arLogic
    else:
        assert len(arLogic) == 1 and arLogic[0]["code"] == sProgram and arLogic[0]["links"] == 0
        assert arLogic[0]["team"] == sys_config.cPvpWaveTeam and arLogic[0]["ipt"] == sys_config.cdtBotRules["ipt"]
    assert [(p["path"], p["text"]) for p in dtCheck["patches"]] == list(sys_config.carDataPatches)
    assert json.loads(dtCheck["tags"]["genfilters"]) == json.loads(dtTags["genfilters"])
    assert json.loads(dtCheck["tags"]["rules"]) == json.loads(dtTags["rules"])
    return vRawSize, vFileSize


def fnGenerate(sLayout, vSeed, vOut, vOreRolls=1, vDifficulty=sys_config.cDefaultDifficulty):
    """Builds, writes, renders, reports and checks one map at one difficulty. Returns True when the checks
    pass. The difficulty only changes the waves and match rules; the terrain depends on the seed alone."""
    vT0 = time.time()
    os.makedirs(vOut, exist_ok=True)
    dtLevel = sys_config.cdtDifficulties[vDifficulty]
    print("Map type: %s (%s), difficulty %s, seed %d" % (sLayout.cName, sLayout.cKey, dtLevel["label"], vSeed))
    sResult = sLayout.fnBuild(vSeed)
    _vsValidateResult(sResult)
    sGrid = cm_terrain.clGrid(sResult.vWidth, sResult.vHeight)
    vPvp = sResult.sMatch == "pvp"

    vTs = time.time()
    arFilters, arRolls, arPreview = _fnRollOres(sResult, vSeed, max(1, vOreRolls))
    print("  %-22s %6.1fs" % ("ore rolls (preview)", time.time() - vTs))
    dtBases = None
    if vPvp:
        dtCorridors, dtRoutes, dtNavalCorridors, dtNavalRoutes, dtBases = _fnRoutesPvp(sGrid, sResult)
    else:
        dtCorridors, dtRoutes, dtNavalCorridors, dtNavalRoutes = _fnRoutes(sGrid, sResult)

    vMapName = sys_config.fnMapName(sResult.vName, vDifficulty)
    vDescription = sResult.vDescription
    if vDifficulty != sys_config.cBaseDifficulty:
        vDescription += "\n" + sys_config.fnDifficultyNote(vDifficulty)
    if vPvp:
        dtMult = cm_bot.fnBotMultipliers(vDifficulty)
        vDescription += ("\nDefender bots: block health x%g, block damage x%g, unit health x%g, unit damage x%g."
                         % (dtMult["blockHealth"], dtMult["blockDamage"], dtMult["unitHealth"], dtMult["unitDamage"]))
    dtRules = waves.fnBuildRules(sResult.dtSpawns, sResult.arNavalSpawnKeys, sResult.dtSpawnAliases, vDifficulty,
                                 sResult.sMatch)
    dtTags = _fnTags(sResult, vMapName, vDescription, dtRules, arFilters)
    vMapPath = os.path.join(vOut, vMapName + ".msav")
    sProgram = cm_bot.fnBuildProgram(sResult.arTeamCores, vDifficulty, vMapName) if vPvp else None
    if sProgram is not None:
        arProblems, vInstructions, dtBotContent = cm_bot.fnCheckProgram(sProgram)
        assert not arProblems, arProblems
    vRawSize, vFileSize = _fnWriteMap(sResult, vMapPath, _fnBlockTable(sResult), dtTags, sProgram)

    vPreviewPath = os.path.join(vOut, vMapName + " - preview.png")
    cm_render.vsRenderPreview(sResult, arPreview[0], arPreview[1], vPreviewPath)
    vRoutesPath = os.path.join(vOut, vMapName + (" - routes.png" if vPvp else " - enemy routes.png"))
    cm_render.vsRenderRoutes(sResult, dtCorridors, dtNavalCorridors, vRoutesPath)

    arGroups = waves.fnExpandGroups(waves.build_groups(), sResult.dtSpawns, sResult.arNavalSpawnKeys,
                                    sResult.dtSpawnAliases, vDifficulty)
    vSpawnCount = len(sResult.dtSpawns)
    dtReport = {
        "map": vMapName, "map_type": sLayout.cKey,
        "difficulty": dict(dtLevel, key=vDifficulty), "seed": vSeed, "size": [sResult.vWidth, sResult.vHeight],
        "game": sys_config.cGameLabel, "mod": sys_config.cModLabel, "file": vMapPath,
        "file_bytes": vFileSize, "uncompressed_bytes": vRawSize,
        "spawns": {sResult.dtSpawnLabels[k]: v for k, v in sResult.dtSpawns.items()},
        "routes": dtRoutes, "naval_routes": dtNavalRoutes, "outposts": sResult.arPads,
        "choke_points": {k: v for k, v in sorted(sResult.dtMarkers.items())},
        "statistics": _fnStatistics(sResult),
        "ore_rolls": _fnOreStatistics(arRolls, sResult.arRegionNames),
        "ore_filters": json.loads(dtTags["genfilters"]), "genfilters_bytes": len(dtTags["genfilters"]),
        "data_patches": [{"path": p, "patch": json.loads(t)} for p, t in sys_config.carDataPatches],
        "rules": {k: v for k, v in dtRules.items() if k != "spawns"}, "spawn_groups": len(dtRules["spawns"]),
        "rules_json_bytes": len(dtTags["rules"]),
        "wave_summary": waves.fnWaveSummary(cReportWaves, arGroups, vSpawnCount, dtLevel["health"]),
        "wave_curve": waves.fnWaveCurve(*cCurve, arGroups, vSpawnCount, dtLevel["health"]),
        "notes": sResult.arNotes,
    }
    if vPvp:
        dtBot = sys_config.cdtBotRules
        dtReport["match"] = "pvp"
        dtReport["teams"] = {d["label"]: {"team": d["team"], "core": [d["x"], d["y"]]} for d in sResult.arTeamCores}
        dtReport["wave_team"] = sys_config.cPvpWaveTeam
        dtReport["ground_path_tiles_between_bases"] = dtBases
        dtReport["defender_bots"] = {
            "join_window_s": dtBot["joinWindow"], "refresh_s": dtBot["refresh"],
            "multipliers": cm_bot.fnBotMultipliers(vDifficulty),
            "turrets": [{"block": b, "ammo": a, "offset": list(o)} for b, a, o in dtBot["turrets"]],
            "wall": dtBot["wall"], "wall_ring": dtBot["wallRing"], "guards": dict(dtBot["guards"]),
            "processor": {"tile": list(cProcessorTile), "team": sys_config.cPvpWaveTeam,
                          "instructions": vInstructions, "code_bytes": len(sProgram.encode("utf-8")),
                          "content": {k: sorted(v) for k, v in dtBotContent.items()}}}
        if sResult.dtResourceRules:
            dtReport["resource_rules"] = {
                "homes": {g: sResult.arRegionNames[r] for g, r in sResult.dtResourceRules["homes"].items()},
                "pocket_cap_tiles": sResult.dtResourceRules["pocketCap"],
                "home_min_tiles": sResult.dtResourceRules["homeMin"]}
    vReportPath = os.path.join(vOut, vMapName + " - report.json")
    with open(vReportPath, "w", encoding="utf-8") as sFile:
        json.dump(dtReport, sFile, indent=2)

    print("\nMap written:   %s (%d KB, %d KB uncompressed)" % (vMapPath, vFileSize // 1024, vRawSize // 1024))
    print("Preview:       %s" % vPreviewPath)
    print(("Routes:        %s" if vPvp else "Enemy routes:  %s") % vRoutesPath)
    print("Report:        %s" % vReportPath)
    for vLabel, dtInfo in dtRoutes.items():
        print("  %-34s %4d tiles via %s" % (vLabel + (" -> " + dtInfo["toward"] if "toward" in dtInfo else ""),
                                           dtInfo["shortest_ground_path_tiles"],
                                           ", ".join(dtInfo["choke_points_on_near_shortest_routes"])))
    for vLabel, dtOthers in (dtBases or {}).items():
        print("  %-34s %s" % (vLabel, ", ".join("%s %d" % (k, v["ground_path_tiles"]) for k, v in dtOthers.items())))
    for vLabel, dtInfo in dtNavalRoutes.items():
        print("  %-34s %4d tiles along the naval flow field (shortest water path %d), rests %.1f tiles from the core"
              % (vLabel + " [naval]", dtInfo["flow_field_path_tiles"], dtInfo["shortest_water_path_tiles"],
                 dtInfo["rest_tiles_from_core"]))
    dtOres = dtReport["ore_rolls"]
    print("Ores: %d in-game filters, ~%d patches per game (median %d tiles; %d simulated roll%s)"
          % (len(arFilters), dtOres["patches_per_game"], dtOres["patch_tiles"]["median"], dtOres["rolls"],
             "" if dtOres["rolls"] == 1 else "s"))
    for vNote in sResult.arNotes:
        print("  note: " + vNote)
    print("Done in %.1fs\n" % (time.time() - vT0))
    return sLayout.fnCheck(vMapPath, sResult)
