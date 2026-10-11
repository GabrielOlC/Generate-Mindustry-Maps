"""Layout contract for map types, and the discovery of layout generators.

A map type is one module in the `layouts` folder holding one subclass of `clLayout`. The pipeline only
talks to this contract and never imports a layout by name, so a new map type needs no change anywhere
else. A layout paints terrain and names its places; ores, waves, match rules, data patches, rendering,
the report and the shared checks come from the shared systems (sys_config, ores, waves, cm_pipeline,
cm_render, cm_checks).
"""

import importlib
import pkgutil

import cm_checks

cLayoutsPackage = "layouts"


class clLayoutResult:
    """What a layout hands to the pipeline. Tiles are row-major indexes, y = 0 is the bottom row.

    arFloor / arWall     block names per tile (arWall None = no wall); boulders count as non-solid walls
    arOverlay            per tile; only "spawn" marks (ores are rolled by the game from the shared filters)
    arCore               centre tile (x, y) of the core block (sys_config.cCoreBlock)
    dtSpawns             {key: (x, y)} of every spawn tile; dtSpawnLabels {key: label}
    arNavalSpawnKeys     spawns on water that boats can sail from (naval wave groups are pinned to them)
    dtSpawnAliases       {spawn key used by the shared wave groups: this map's own key}, if keys differ
    arRegion             region index per tile, arRegionNames[index] its name (statistics, ore report)
    dtMarkers            {choke point name: (x, y)}; arPads [{"name", "biome", "x", "y"}] outpost pads
    arBarrierTests       [{"label", "names": [choke points], "radius", "start": (x, y), "goal": (x, y),
                           "region": fnInside(tile) or None}]: closing the named choke points (discs of
                           `radius`) must cut every ground path from start to goal inside the region
    dtRouteColors        {spawn key: (r, g, b)} for the routes image

    PvP maps (sMatch "pvp") also give:
    arTeamCores          [{"team": id, "key", "label", "x", "y", "region"}]: one core per player slot
                         (sys_config.cdtPvpTeams); arCore is then only the camera position. Every core needs
                         a clear square of sys_config.cBotKeep around it for a defender-bot fortress
    arNavalLinks         [{"label", "start": (x, y), "core": (x, y), "reach": tiles}]: boats starting at
                         `start` must come to rest within `reach` tiles of that core (naval raids between
                         bases; cm_checks.cNavalReach when not given)
    dtResourceRules      {"homes": {resource group: region index}, "bases": [region index],
                          "pocketCap": tiles, "homeMin": tiles}: every base region holds every group of
                          sys_config.cdtResourceFloors, at most pocketCap tiles of each foreign one and at
                          least homeMin of each of its own
    """

    def __init__(self, vName, vDescription, vWidth, vHeight, arFloor, arOverlay, arWall, arCore, dtSpawns,
                 dtSpawnLabels, dtRouteColors, arRegion, arRegionNames, dtMarkers=None, arPads=None,
                 arNavalSpawnKeys=(), dtSpawnAliases=None, arBarrierTests=(), arNotes=None, sMatch="survival",
                 arTeamCores=(), arNavalLinks=(), dtResourceRules=None):
        self.vName = vName
        self.vDescription = vDescription
        self.vWidth = vWidth
        self.vHeight = vHeight
        self.arFloor = arFloor
        self.arOverlay = arOverlay
        self.arWall = arWall
        self.arCore = arCore
        self.dtSpawns = dtSpawns
        self.dtSpawnLabels = dtSpawnLabels
        self.dtRouteColors = dtRouteColors
        self.arRegion = arRegion
        self.arRegionNames = arRegionNames
        self.dtMarkers = dtMarkers or {}
        self.arPads = arPads or []
        self.arNavalSpawnKeys = tuple(arNavalSpawnKeys)
        self.dtSpawnAliases = dtSpawnAliases or {}
        self.arBarrierTests = list(arBarrierTests)
        self.arNotes = arNotes or []
        self.sMatch = sMatch
        self.arTeamCores = list(arTeamCores)
        self.arNavalLinks = list(arNavalLinks)
        self.dtResourceRules = dtResourceRules

    def fnCores(self):
        """[{"team", "x", "y", ...}] of every core block to write: the player cores of a PvP map, else the
        one sharded core."""
        if self.sMatch == "pvp":
            return self.arTeamCores
        return [{"team": 1, "key": None, "label": "Core", "x": self.arCore[0], "y": self.arCore[1]}]


class clLayout:
    """Base class of every layout generator (one per map type)."""

    cKey = None          # id on the command line, e.g. "biomes-confluence"
    cName = None         # map name: in-game title and output file names
    cSummary = ""        # one line for the controller's menu
    cDefaultSeed = 0
    cOrder = 100         # position in the controller's menu

    def fnBuild(self, vSeed):
        """Paints the terrain for `vSeed` and returns a clLayoutResult."""
        raise NotImplementedError

    def fnCheck(self, vMapPath, sResult):
        """Verifies the written map; True when every check passes. Defaults to the shared checks."""
        return cm_checks.fnCheckMap(vMapPath, sResult)


def fnFindLayouts():
    """{cKey: layout class} for every clLayout subclass in the layouts package, in menu order."""
    sPackage = importlib.import_module(cLayoutsPackage)
    dtFound = {}
    for sInfo in sorted(pkgutil.iter_modules(sPackage.__path__), key=lambda s: s.name):
        sModule = importlib.import_module("%s.%s" % (cLayoutsPackage, sInfo.name))
        for sValue in vars(sModule).values():
            if not (isinstance(sValue, type) and issubclass(sValue, clLayout) and sValue is not clLayout
                    and sValue.__module__ == sModule.__name__):
                continue
            if not sValue.cKey or not sValue.cName:
                raise ValueError("%s.%s needs cKey and cName" % (sModule.__name__, sValue.__name__))
            if sValue.cKey in dtFound:
                raise ValueError("Two layouts use the key '%s'" % sValue.cKey)
            dtFound[sValue.cKey] = sValue
    return dict(sorted(dtFound.items(), key=lambda kv: (kv[1].cOrder, kv[1].cName)))
