"""Biomes Warfront: five-player PvP over five biomes, with waves rising from the Rift in the middle.

Each player slot (sys_config.cdtPvpTeams) owns one biome sector and a walled base in it: a Foundation
core on a plaza, a clear square for a defender-bot fortress, four outpost pads, a rampart with three
gates and a resource garden. All bases sit at the same distance from the centre and have the same rampart,
garden and pads; only the biome around them differs.

Resources: every floor resource of sys_config.cdtResourceFloors has one home biome, where there is a
lot of it. Every other base gets exactly one 3x3 pocket of it in its garden, and the biome palettes never
paint a foreign resource floor anywhere else. Ores are rolled by the game on every load, as on the other
maps.

The Rift is a neutral basin around Confluence Lagoon. The five wave spawns stand on its shore, one facing
each base; the RTS AI of the wave team sends every squad at a target it picks among all players
(sys_config.cdtPvpRules). Greenwater (water) and Rimeflow (cryofluid) run from harbours inside the forest
and frozen ramparts to the lagoon, so boats can raid between those two bases and the centre. Separator
ridges between the sectors have one flank pass each, so neighbours can also meet without crossing the
Rift.
"""

import math
import random
import time
from array import array

import cm_layout
import cm_terrain
import sys_config

cWidth = cHeight = 800
cCx = cCy = 400
cDeg = math.pi / 180.0

cFrozen, cSemiarid, cDesert, cVolcano, cForest, cRift = range(6)
carRegionNames = ("Frozen (N)", "Semi-arid (E)", "Desert (SE)", "Volcano (SW)", "Forest (W)", "The Rift")
carBiomes = (cFrozen, cSemiarid, cDesert, cVolcano, cForest)

# Base axes (degrees counter-clockwise from east; +y is north). Sector borders lie halfway between.
cdtAxis = {cFrozen: 90.0, cSemiarid: 18.0, cDesert: 306.0, cVolcano: 234.0, cForest: 162.0}
carBorders = (54.0, 126.0, 198.0, 270.0, 342.0)
cCoreRadius = 270.0           # every core stands this far from the centre, on its sector's axis
cRiftRadius = 120.0           # the Rift: neutral basin; separator ridges start at its rim
cSpawnRadius = 62.0           # wave spawns on the lagoon shore, one on each base's axis

cdtBases = {  # biome: (spawn key, team, label, short name)
    cFrozen: ("frozen", sys_config.cdtPvpTeams["blue"], "Frozen base (blue)", "Frozen"),
    cSemiarid: ("semiarid", sys_config.cdtPvpTeams["malis"], "Semi-arid base (purple)", "Steppe"),
    cDesert: ("desert", sys_config.cdtPvpTeams["sharded"], "Desert base (yellow)", "Desert"),
    cVolcano: ("volcano", sys_config.cdtPvpTeams["crux"], "Volcano base (red)", "Volcano"),
    cForest: ("forest", sys_config.cdtPvpTeams["green"], "Forest base (green)", "Forest"),
}
cdtRouteColors = {"frozen": (0, 190, 255), "semiarid": (190, 120, 255), "desert": (235, 215, 0),
                  "forest": (40, 200, 60), "volcano": (255, 50, 50)}

# A base, in local polar coordinates around its core: phi in degrees from the direction to the map
# centre (counter-clockwise), d in tiles.
cRampartRadius = 66.0          # inner edge of the rampart band (about 11-15 tiles thick)
cdtGatePhi = {"Rift": 0.0, "left": 100.0, "right": -100.0}   # left faces the neighbour at axis - 72
cGateHalf = 8.0
carPadPhi = (40.0, -40.0, 145.0, -145.0)
cPadDistance = 50.0
cGardenDistance = 48.0         # resource garden behind the core (phi 180): 3x3 grid of 3x3 pockets
cGardenStep = 6
cHarbourDistance = 44.0
cHarbourPool = 8.0
cHarbourReach = 40.0           # boats raiding a river base come to rest in its harbour, this close to the core
cRoadHalf = 5.0                # cleared road from each Rift spawn to its base's Rift gate (equal wave distances)
cBaseReach = 84.0              # liquids of the biome features stay outside this distance from a core

cdtHomes = {  # resource group (sys_config.cdtResourceFloors) -> home biome
    "water": cForest, "cryofluid": cFrozen, "oil (tar)": cDesert, "oil-rich ground (shale)": cSemiarid,
    "slag (lava)": cVolcano, "pyroplasma (pyromagma)": cVolcano, "cold plasma (glowing vein)": cFrozen,
    "heat (hotrock/magmarock)": cVolcano, "spore moss": cForest, "sand floor (sand/darksand)": cDesert,
}
cdtPocketFloor = {
    "water": "shallow-water", "cryofluid": "pooled-cryofluid", "oil (tar)": "tar",
    "oil-rich ground (shale)": "shale", "slag (lava)": "molten-slag", "pyroplasma (pyromagma)": "pyromagma",
    "cold plasma (glowing vein)": "glowingvein", "heat (hotrock/magmarock)": "magmarock",
    "spore moss": "spore-moss", "sand floor (sand/darksand)": "darksand",
}
cPocketCap = 9                 # one 3x3 pocket
cHomeMin = 300                 # usable tiles of each home resource, at least

# Rivers: from a harbour inside the forest / frozen rampart to Confluence Lagoon (set up in fnRiverPoints).
cLagoonRadius = 26.0
cdtRivers = {"Greenwater": (cForest, 72.0, 140.0), "Rimeflow": (cFrozen, -72.0, 110.0)}  # base, harbour phi, Rift entry angle
# Shallow water fords inside the Rift (neutral ground), so the land around the lagoon stays one ring. The
# sectors need none: each river base connects both banks through its own gates, and a ford of shallow
# water in the frozen sector would be a foreign resource there.
cdtFords = {"Rift Ford (Greenwater)": "Greenwater", "Rift Ford (Rimeflow)": "Rimeflow"}
cFordRadius = 88.0
cdtFlankPasses = {54.0: "Hoarwind Pass", 126.0: "Frostwood Pass", 198.0: "Ashgrove Pass", 270.0: "Cinderdune Pass",
                  342.0: "Saltsteppe Pass"}
cFlankRadius = 300.0

# Home features of each biome (global angle, radius from the centre, size).
carCraterLake = (217.0, 178.0, 16.0)
carLavaPools = ((214.0, 335.0, 7.0), (254.0, 335.0, 7.0), (246.0, 190.0, 6.0))
carPyroCreeks = (((212.0, 190.0), (210.0, 240.0), (214.0, 290.0)), ((256.0, 200.0), (258.0, 250.0), (255.0, 300.0)))
carTarPits = ((284.0, 195.0, 10.0), (328.0, 200.0, 10.0), (290.0, 360.0, 9.0), (324.0, 355.0, 9.0))
carSaltPan = (306.0, 165.0, 24.0)
carWreck = (322.0, 380.0, 22.0)
carSporeGrove = (190.0, 345.0, 38.0)
carSporeGrove2 = (140.0, 220.0, 22.0)

cdtBiomeFloor = {cFrozen: "snow", cSemiarid: "dirt", cDesert: "sand-floor", cVolcano: "basalt", cForest: "grass",
                 cRift: "stone"}
cdtBoulders = {cFrozen: "snow-boulder", cSemiarid: "dacite-boulder", cDesert: "sand-boulder", cVolcano: "basalt-boulder",
               cForest: "boulder", cRift: "boulder"}
carNoDecorFloors = sys_config.carLiquidFloors | {"glowingvein", "core-zone", "metal-floor", "metal-floor-damaged",
                                                 "dark-panel-1", "dark-panel-2", "dark-panel-3", "dark-panel-4",
                                                 "dark-panel-5", "dark-panel-6"}

cDescription = (
    "[accent]800x800 PvP for 5 players, built for Exogenesis Old.[]\n"
    "Five bases, one per biome: frozen north, semi-arid east, desert south-east, volcano south-west and "
    "forest west. Every base has every floor resource: plenty of its own biome's, and one small pocket of "
    "each other in its resource garden. Waves rise from the Rift in the middle and strike any base. "
    "Boats sail Greenwater and Rimeflow between the forest and frozen bases. A slot nobody takes becomes a "
    "defender fortress after %d minutes; it never attacks, but must be destroyed to win. Ore nodes are "
    "re-rolled every time the map is loaded; thermal generators work anywhere on lava."
) % round(sys_config.cdtBotRules["joinWindow"] / 60.0)


def _fnAngDiff(vA, vB):
    return (vA - vB + 180.0) % 360.0 - 180.0


def _fnSector(vAngle):
    for vBiome in carBiomes:
        if abs(_fnAngDiff(vAngle, cdtAxis[vBiome])) <= 36.0:
            return vBiome
    return cFrozen


def _fnPolar(vAngle, vRadius):
    return int(round(cCx + vRadius * math.cos(vAngle * cDeg))), int(round(cCy + vRadius * math.sin(vAngle * cDeg)))


def fnCore(vBiome):
    return _fnPolar(cdtAxis[vBiome], cCoreRadius)


def fnLocal(vBiome, vPhi, vDistance):
    """Tile at local angle `vPhi` and distance `vDistance` from a base's core."""
    vX, vY = fnCore(vBiome)
    vA = (cdtAxis[vBiome] + 180.0 + vPhi) * cDeg
    return vX + vDistance * math.cos(vA), vY + vDistance * math.sin(vA)


def fnNeighbourGates(vBiome):
    """{gate key: gate name} of a base: toward the Rift and toward each neighbour. Local phi > 0 turns
    counter-clockwise from "toward the centre", so the left gate faces the neighbour at axis - 72."""
    vShort = cdtBases[vBiome][3]
    dtByAxis = {cdtAxis[b]: b for b in carBiomes}
    vLeft = dtByAxis[(cdtAxis[vBiome] - 72.0) % 360.0]
    vRight = dtByAxis[(cdtAxis[vBiome] + 72.0) % 360.0]
    return {"Rift": "%s Rift Gate" % vShort, "left": "%s %s Gate" % (vShort, cdtBases[vLeft][3]),
            "right": "%s %s Gate" % (vShort, cdtBases[vRight][3])}


class clWarfrontTerrain:
    """Paints the map step by step. arProt: 0 free, 1 liquid or bank, 2 forced open, 3 structural wall."""

    def __init__(self, vSeed):
        self.vSeed = vSeed
        self.sGrid = cm_terrain.clGrid(cWidth, cHeight)
        vTiles = cWidth * cHeight
        self.vTiles = vTiles
        self.arFloor = ["stone"] * vTiles
        self.arOre = [None] * vTiles
        self.arWall = [None] * vTiles
        self.arProt = bytearray(vTiles)
        self.arKeep = bytearray(vTiles)
        self.arChannel = bytearray(vTiles)
        self.arSpore = bytearray(vTiles)
        self.arWreck = bytearray(vTiles)
        self.dtMarkers = {}
        self.arPads = []
        self.arNotes = []
        self.dtRivers = {}
        self.dtSpawns = {}
        self.dtGarden = {}

    # -- setup -----------------------------------------------------------------------------------

    def vsNoise(self):
        vS, sGrid = self.vSeed, self.sGrid
        self.arWarp = sGrid.fnFbm(vS + 1, 190, 3)
        self.arN1 = sGrid.fnFbm(vS + 2, 42, 3)
        self.arN2 = sGrid.fnFbm(vS + 3, 13, 2)
        self.arN3 = sGrid.fnFbm(vS + 4, 100, 3)
        self.arThick = sGrid.fnFbm(vS + 6, 36, 3)
        self.arRock = sGrid.fnFbm(vS + 7, 30, 4)
        self.arGrove = sGrid.fnFbm(vS + 8, 15, 3)
        self.arDune = sGrid.fnFbm(vS + 9, 16, 3, vStretchY=4.0)
        self.arVein = sGrid.fnFbm(vS + 10, 38, 3)
        self.arFine = sGrid.fnFbm(vS + 11, 4, 1)
        self.arEdge = sGrid.fnFbm(vS + 12, 24, 2)
        self.arShale = sGrid.fnFbm(vS + 13, 26, 3)

    def vsPolar(self):
        self.arR = array("f", bytes(4 * self.vTiles))
        self.arT = array("f", bytes(4 * self.vTiles))
        self.arTW = array("f", bytes(4 * self.vTiles))
        self.arCB = bytearray(self.vTiles)
        self.arRegion = bytearray(self.vTiles)
        i = 0
        for vY in range(cHeight):
            vDy = vY - cCy
            for vX in range(cWidth):
                vDx = vX - cCx
                vR = math.hypot(vDx, vDy)
                vT = math.degrees(math.atan2(vDy, vDx)) % 360.0
                vTw = (vT + 12.0 * (self.arWarp[i] - 0.5)) % 360.0
                self.arR[i], self.arT[i], self.arTW[i] = vR, vT, vTw
                vBiome = _fnSector(vTw)
                self.arCB[i] = vBiome
                self.arRegion[i] = cRift if vR < cRiftRadius else vBiome
                i += 1
        self.dtCores = {b: fnCore(b) for b in carBiomes}
        # flank passes open where the warped border crosses cFlankRadius
        self.dtPasses = {}
        for vBorder, vName in cdtFlankPasses.items():
            arBest = None
            for k in range(-200, 201):
                vA = vBorder + k * 0.05
                vX, vY = _fnPolar(vA, cFlankRadius)
                vMiss = abs(_fnAngDiff(self.arTW[vY * cWidth + vX], vBorder))
                if arBest is None or vMiss < arBest[0]:
                    arBest = (vMiss, (vX, vY))
            self.dtPasses[vBorder] = arBest[1]

    def vsRoads(self):
        """A cleared road from every Rift spawn to its base's Rift gate: no natural walls or liquid features
        on it, so the waves have the same way to walk to every base."""
        for vBiome in carBiomes:
            vSx, vSy = _fnPolar(cdtAxis[vBiome], cSpawnRadius)
            vGx, vGy = fnLocal(vBiome, 0.0, cRampartRadius + 14.0)
            dtField, _ = self.sGrid.fnPolylineField(((vSx, vSy), (vGx, vGy)), cRoadHalf)
            for i in dtField:
                self.arKeep[i] = 1

    def fnBaseDistance(self, i):
        """Distance from tile i to the core of the biome sector it lies in."""
        vX, vY = self.dtCores[self.arCB[i]]
        return math.hypot(i % cWidth - vX - 0.5, i // cWidth - vY - 0.5)

    # -- floors ----------------------------------------------------------------------------------

    def fnPalette(self, vRegion, i):
        """Floors of each biome. No palette paints a resource floor of another biome (cdtHomes)."""
        vA, vC, vD = self.arN1[i], self.arN2[i], self.arN3[i]
        if vRegion == cRift:
            if vA > 0.80:
                return "crater-stone"
            if vC > 0.86:
                return "dirt"
            return "stone"
        if vRegion == cDesert:
            if vA > 0.74:
                return "darksand"
            return "sand-floor"
        if vRegion == cSemiarid:
            if self.arShale[i] > 0.62:
                return "shale"
            if vD < 0.12:
                return "salt"
            if vA > 0.66:
                return "dacite"
            return "dirt"
        if vRegion == cFrozen:
            if self.fnGlacier(i):
                if vA > 0.82:
                    return "ice"
                if vA < 0.62:
                    return "siratla-stone"
                return "ice-snow"
            if vA > 0.80:
                return "ice"
            if vA > 0.56:
                return "ice-snow"
            return "snow"
        if vRegion == cForest:
            if vA > 0.64:
                return "moss"
            if vC > 0.85:
                return "dirt"
            if vD < 0.14 and vC > 0.45:
                return "mud"
            return "grass"
        if vD < 0.15:
            return "crater-stone"
        if vC > 0.95:
            return "magmarock"
        if vC > 0.84:
            return "hotrock"
        if vA > 0.72:
            return "char"
        return "basalt"

    def fnGlacier(self, i):
        return (self.arCB[i] == cFrozen and self.arR[i] > 330.0 + 30.0 * (self.arN3[i] - 0.5)
                and self.fnBaseDistance(i) > 30.0)

    def vsFloors(self):
        for i in range(self.vTiles):
            self.arFloor[i] = self.fnPalette(self.arRegion[i], i)

    def vsSetFloor(self, i, vFloor, vProt=None):
        self.arFloor[i] = vFloor
        if vProt is not None and self.arProt[i] < vProt:
            self.arProt[i] = vProt

    # -- water -----------------------------------------------------------------------------------

    def fnRiverPoints(self, vName):
        """Control points from the harbour inside the base rampart to the lagoon edge: straight out through
        the rampart between the outpost pad and the side gate, then along the Rift-gate side of the sector."""
        vBiome, vHarbourPhi, vEntry = cdtRivers[vName]
        vSide = 1.0 if vHarbourPhi > 0 else -1.0
        arPoints = [fnLocal(vBiome, vHarbourPhi, cHarbourDistance),
                    fnLocal(vBiome, vHarbourPhi + vSide * 2.0, cRampartRadius - 6.0),
                    fnLocal(vBiome, vHarbourPhi - vSide * 2.0, cRampartRadius + 18.0),
                    fnLocal(vBiome, vHarbourPhi - vSide * 27.0, cRampartRadius + 46.0)]
        vX, vY = arPoints[-1]
        vR0 = math.hypot(vX - cCx, vY - cCy)
        vA0 = math.degrees(math.atan2(vY - cCy, vX - cCx)) % 360.0
        for vF in (0.25, 0.5, 0.75):
            vR = vR0 + (cRiftRadius - vR0) * vF
            vA = vA0 + _fnAngDiff(vEntry, vA0) * vF
            arPoints.append(_fnPolar(vA, vR))
        arPoints += [_fnPolar(vEntry, cRiftRadius), _fnPolar(vEntry, (cRiftRadius + cLagoonRadius) / 2.0),
                     _fnPolar(vEntry, cLagoonRadius - 6.0)]
        return [(float(x), float(y)) for x, y in arPoints]

    def vsRivers(self):
        """Greenwater (deep water, shallow and sand banks) and Rimeflow (cryofluid, ice banks)."""
        for vName, vSeed in (("Greenwater", 30), ("Rimeflow", 31)):
            arPoints = self.fnRiverPoints(vName)
            dtField, arDense = self.sGrid.fnPolylineField(arPoints, 16.0, vAmplitude=6.0, vScale=40.0,
                                                          vSeed=self.vSeed + vSeed)
            self.dtRivers[vName] = (dtField, arDense)
            for i, vD in dtField.items():
                vHalf = 3.6 + 1.6 * self.arN1[i]                 # deep channel 7-10 tiles wide
                vS = vD - vHalf
                if vName == "Greenwater":
                    if vS <= 0.0:
                        self.vsSetFloor(i, "deep-water", 1)
                        self.arChannel[i] = 1
                    elif vS <= 3.0:
                        self.vsSetFloor(i, "shallow-water", 1)
                    elif vS <= 5.0:
                        self.vsSetFloor(i, "sand-water" if self.arN2[i] > 0.45 else "darksand-water", 1)
                    elif vS <= 8.0 and self.arFloor[i] not in sys_config.carLiquidFloors:
                        self.vsSetFloor(i, "mud")
                else:
                    if vS <= 0.0:
                        self.vsSetFloor(i, "pooled-cryofluid", 1)
                        self.arChannel[i] = 1
                    elif vS <= 3.0:
                        self.vsSetFloor(i, "ice", 1)
                    elif vS <= 6.0 and self.arFloor[i] not in sys_config.carLiquidFloors:
                        self.vsSetFloor(i, "ice-snow")

    def vsLagoon(self):
        """Confluence Lagoon in the Rift and the harbour pools at the rivers' heads."""
        for i, vD in self.sGrid.fnDisc(cCx, cCy, cLagoonRadius + 4.0):
            vS = vD - (cLagoonRadius + 4.0 * (self.arN3[i] - 0.5))
            if vS <= -8.0:
                self.vsSetFloor(i, "deep-water", 1)
                self.arChannel[i] = 1
            elif vS <= -2.0:
                self.vsSetFloor(i, "shallow-water", 1)
                self.arChannel[i] = 0
            elif vS <= 1.0:
                self.vsSetFloor(i, "sand-water", 1)
                self.arChannel[i] = 0
        self.dtHarbours = {}
        for vName, (vBiome, vPhi, _) in cdtRivers.items():
            vHx, vHy = fnLocal(vBiome, vPhi, cHarbourDistance)
            vHx, vHy = int(round(vHx)), int(round(vHy))
            self.dtHarbours[vBiome] = (vHx, vHy)
            self.dtMarkers["%s Harbour" % cdtBases[vBiome][3]] = (vHx, vHy)
            vLiquid = "shallow-water" if vName == "Greenwater" else "pooled-cryofluid"
            for i, vD in self.sGrid.fnDisc(vHx, vHy, cHarbourPool + 3.0):
                if vD <= cHarbourPool - 3.0 and vName == "Rimeflow":
                    self.vsSetFloor(i, vLiquid, 1)
                    self.arChannel[i] = 0
                elif vD <= cHarbourPool:
                    self.vsSetFloor(i, "shallow-water" if vName == "Greenwater" else "ice", 1)
                    if vName == "Rimeflow" and vD > cHarbourPool - 3.0:
                        self.vsSetFloor(i, "pooled-cryofluid", 1)
                    self.arChannel[i] = 0
                elif self.arFloor[i] not in sys_config.carLiquidFloors:
                    self.vsSetFloor(i, "sand-water" if vName == "Greenwater" else "ice", 1)

    def vsFords(self):
        for vName, vRiver in cdtFords.items():
            dtField, arDense = self.dtRivers[vRiver]
            arNominal = min(arDense, key=lambda p: abs(math.hypot(p[0] - cCx, p[1] - cCy) - cFordRadius))
            arCentre, arTiles = self.sGrid.fnAcross(dtField, arDense, arNominal, 6.0)
            self.dtMarkers[vName] = arCentre
            for i, _ in self.sGrid.fnDisc(arCentre[0], arCentre[1], 14.0):
                self.arKeep[i] = 1
            for i in arTiles:
                if self.arFloor[i] in sys_config.carDeepFloors:
                    self.vsSetFloor(i, "shallow-water")
                    self.arChannel[i] = 0
                    self.arProt[i] = 2

    # -- biome features --------------------------------------------------------------------------

    def fnFeatureOk(self, i, vBiome):
        """Liquid features stay in their own sector, outside the base and off the ridges."""
        if self.arCB[i] != vBiome or self.arRegion[i] == cRift or self.arProt[i] or self.arKeep[i]:
            return False
        if self.fnBaseDistance(i) < cBaseReach:
            return False
        return min(abs(_fnAngDiff(self.arTW[i], b)) for b in carBorders) * cDeg * self.arR[i] > 18.0

    def vsVolcano(self):
        vLx, vLy = _fnPolar(carCraterLake[0], carCraterLake[1])
        vLr = carCraterLake[2]
        for i, vD in self.sGrid.fnDisc(vLx, vLy, vLr + 7.0):
            if not self.fnFeatureOk(i, cVolcano):
                continue
            vS = vD - vLr * (0.85 + 0.3 * self.arFine[i])
            if vS < -2.0:
                self.vsSetFloor(i, "molten-slag", 1)
            elif vS < 1.5:
                self.vsSetFloor(i, "magmarock", 1)
            elif vS < 5.0:
                self.vsSetFloor(i, "hotrock")
        self.dtMarkers["Crater Lake"] = (vLx, vLy)
        for vA, vR, vPr in carLavaPools:
            vPx, vPy = _fnPolar(vA, vR)
            for i, vD in self.sGrid.fnDisc(vPx, vPy, vPr + 3.5):
                if not self.fnFeatureOk(i, cVolcano):
                    continue
                if vD < vPr - 2:
                    self.vsSetFloor(i, "molten-slag", 1)
                elif vD < vPr + 1.5:
                    self.vsSetFloor(i, "magmarock", 1)
                elif self.arFloor[i] not in sys_config.carLiquidFloors:
                    self.vsSetFloor(i, "hotrock")
        for k, arCreek in enumerate(carPyroCreeks):
            dtCreek, _ = self.sGrid.fnPolylineField([_fnPolar(a, r) for a, r in arCreek], 6.0, vAmplitude=3.0,
                                                    vScale=20.0, vSeed=self.vSeed + 41 + k)
            for i, vD in dtCreek.items():
                if not self.fnFeatureOk(i, cVolcano) or self.arFloor[i] in sys_config.carDeepFloors:
                    continue
                if vD <= 2.2:
                    self.vsSetFloor(i, "pyromagma", 1)
                elif vD <= 4.5:
                    self.vsSetFloor(i, "hotrock")

    def vsFrozen(self):
        for i in range(self.vTiles):
            if self.fnGlacier(i) and not self.arProt[i] and self.arFloor[i] not in sys_config.carLiquidFloors:
                if 1.0 - abs(2.0 * self.arVein[i] - 1.0) > 0.972:
                    self.arFloor[i] = "glowingvein"

    def vsDesert(self):
        dtTar = {}
        for vA, vR, vTr in carTarPits:
            vTx, vTy = _fnPolar(vA, vR)
            for i, vD in self.sGrid.fnDisc(vTx, vTy, vTr + 6.0):
                vS = vD - vTr * (0.85 + 0.3 * self.arFine[i])
                if vS < dtTar.get(i, 99.0):
                    dtTar[i] = vS
        for i, vS in dtTar.items():
            if not self.fnFeatureOk(i, cDesert):
                continue
            if vS < -1.5:
                self.vsSetFloor(i, "tar", 1)
            elif vS < 4.0 and self.arFloor[i] not in sys_config.carLiquidFloors:
                self.vsSetFloor(i, "darksand", 1 if vS < 1.0 else None)
        vWx, vWy = _fnPolar(carWreck[0], carWreck[1])
        vWr = carWreck[2]
        for i, vD in self.sGrid.fnDisc(vWx, vWy, vWr):
            if self.fnFeatureOk(i, cDesert) and vD < vWr * (0.7 + 0.3 * self.arN3[i]):
                vC = self.arN2[i]
                if vC > 0.55:
                    self.arFloor[i] = "metal-floor-damaged"
                elif vC > 0.42:
                    self.arFloor[i] = "dark-panel-%d" % (1 + int(self.arFine[i] * 5.99))
                self.arWreck[i] = 1
        self.dtMarkers["Wreck Field"] = (vWx, vWy)
        vPx, vPy = _fnPolar(carSaltPan[0], carSaltPan[1])
        vPr = carSaltPan[2]
        for i, vD in self.sGrid.fnDisc(vPx, vPy, vPr):
            if self.arCB[i] == cDesert and self.arRegion[i] != cRift and not self.arProt[i] \
                    and vD < vPr * (0.75 + 0.25 * self.arN3[i]):
                self.arFloor[i] = "salt"

    def vsForest(self):
        for vA, vR, vSize in (carSporeGrove, carSporeGrove2):
            vGx, vGy = _fnPolar(vA, vR)
            for i, vD in self.sGrid.fnDisc(vGx, vGy, vSize):
                if (self.arCB[i] != cForest or self.arRegion[i] == cRift or self.arProt[i] or self.arKeep[i]
                        or self.arFloor[i] in sys_config.carLiquidFloors or self.fnBaseDistance(i) < cBaseReach):
                    continue
                if vD < vSize * (0.72 + 0.28 * self.arN3[i]):
                    self.arFloor[i] = "spore-moss" if self.arN2[i] > 0.3 else "moss"
                    self.arSpore[i] = 1

    # -- walls -----------------------------------------------------------------------------------

    def fnStructural(self, i):
        """Vanilla wall for a structural barrier on tile i (so the layout holds without the mod)."""
        vWall = sys_config.cdtNaturalWall.get(self.arFloor[i], "stone-wall")
        if vWall in sys_config.carModBlocks or vWall == "dark-metal":
            return "ice-wall" if self.arFloor[i] in ("siratla-stone", "glowingvein") else "stone-wall"
        return vWall

    def vsPutWall(self, i, vWall=None):
        self.arWall[i] = vWall or self.fnStructural(i)
        self.arProt[i] = 3

    def vsOpen(self, i):
        if self.arWall[i] is not None and self.arWall[i] not in sys_config.carNonSolidBlocks:
            self.arWall[i] = None
        if self.arProt[i] != 1:
            self.arProt[i] = 2
        self.arKeep[i] = 1

    def fnKeepSquare(self, vBiome):
        """Tiles of a base's fortress square (Chebyshev sys_config.cBotKeep around the core's middle)."""
        vX, vY = self.dtCores[vBiome]
        vK = sys_config.cBotKeep
        return [(vTy * cWidth + vTx) for vTy in range(int(vY + 0.5 - vK), int(vY + 0.5 + vK) + 1)
                for vTx in range(int(vX + 0.5 - vK), int(vX + 0.5 + vK) + 1)]

    def fnGardenSlots(self, vBiome):
        """Centres of the nine 3x3 pocket slots of a base's resource garden, nearest first."""
        vGx, vGy = fnLocal(vBiome, 180.0, cGardenDistance)
        vA = (cdtAxis[vBiome] + 180.0 + 180.0) * cDeg        # outward
        vUx, vUy = math.cos(vA), math.sin(vA)
        arSlots = []
        for vI in (0, -1, 1):
            for vJ in (0, -1, 1):
                vSx = vGx + vI * cGardenStep * vUx - vJ * cGardenStep * vUy
                vSy = vGy + vI * cGardenStep * vUy + vJ * cGardenStep * vUx
                arSlots.append((int(round(vSx)), int(round(vSy))))
        return arSlots

    def vsKeepClear(self):
        for vBiome in carBiomes:
            for i in self.fnKeepSquare(vBiome):
                self.arKeep[i] = 1
            for vSx, vSy in self.fnGardenSlots(vBiome):
                for i, _ in self.sGrid.fnDisc(vSx, vSy, 4.5):
                    self.arKeep[i] = 1
            for vPhi in carPadPhi:
                vPx, vPy = fnLocal(vBiome, vPhi, cPadDistance)
                for i, _ in self.sGrid.fnDisc(vPx, vPy, 10.0):
                    self.arKeep[i] = 1
            for vKey, vPhi in cdtGatePhi.items():
                for vD in range(10, int(cRampartRadius + 26), 2):
                    vX, vY = fnLocal(vBiome, vPhi, vD)
                    for i, _ in self.sGrid.fnDisc(vX, vY, 5.0):
                        self.arKeep[i] = 1
        for vBiome in carBiomes:
            vSx, vSy = _fnPolar(cdtAxis[vBiome], cSpawnRadius)
            for i, _ in self.sGrid.fnDisc(vSx, vSy, 18.0):
                self.arKeep[i] = 1
        for vPx, vPy in self.dtPasses.values():
            for i, _ in self.sGrid.fnDisc(vPx, vPy, 22.0):
                self.arKeep[i] = 1

    def vsNaturalWalls(self):
        """Rocks, dunes and trees per biome; none inside a rampart, so every base has the same room to build."""
        for i in range(self.vTiles):
            if self.arWall[i] is not None or self.arProt[i] or self.arKeep[i]:
                continue
            if self.arRegion[i] != cRift and self.fnBaseDistance(i) < cRampartRadius + 2.0:
                continue
            vFloor = self.arFloor[i]
            if vFloor in sys_config.carLiquidFloors:
                continue
            vRegion = self.arRegion[i]
            vRock, vGrove = self.arRock[i], self.arGrove[i]
            vWall = None
            if vRegion == cRift:
                if self.arR[i] > 40.0 and vRock > 0.955:
                    vWall = sys_config.cdtNaturalWall.get(vFloor, "stone-wall")
            elif vRegion == cVolcano:
                if vRock > 0.90:
                    vWall = sys_config.cdtNaturalWall.get(vFloor, "dune-wall")
            elif vRegion == cFrozen:
                if self.fnGlacier(i):
                    if vRock > 0.88:
                        vWall = "ice-wall" if vFloor in ("siratla-stone", "glowingvein") else \
                            sys_config.cdtNaturalWall.get(vFloor, "ice-wall")
                elif vRock > 0.915:
                    vWall = sys_config.cdtNaturalWall.get(vFloor, "snow-wall")
                elif vGrove > 0.94:
                    vWall = "snow-pine"
            elif vRegion == cSemiarid:
                if vRock > 0.93:
                    vWall = "dacite-wall" if vFloor == "dacite" else sys_config.cdtNaturalWall.get(vFloor, "dirt-wall")
                elif vGrove > 0.97 and vFloor == "dirt":
                    vWall = "shrubs"
            elif vRegion == cDesert:
                if self.arWreck[i]:
                    if vRock > 0.9:
                        vWall = "dark-metal"
                elif self.arDune[i] > 0.935 or vRock > 0.965:
                    vWall = sys_config.cdtNaturalWall.get(vFloor, "sand-wall")
            elif vRegion == cForest:
                if vGrove > 0.80:
                    vWall = "spore-pine" if self.arSpore[i] else "pine"
                elif vRock > 0.97:
                    vWall = sys_config.cdtNaturalWall.get(vFloor, "stone-wall")
            if vWall is not None:
                self.arWall[i] = vWall

    def vsRidges(self):
        """Separator ridges on the warped sector borders, 14-20 tiles thick, one flank pass each."""
        for i in range(self.vTiles):
            vR = self.arR[i]
            if vR < cRiftRadius:
                continue
            vHalf = 7.0 + 3.0 * self.arThick[i]
            for vBorder in carBorders:
                if abs(_fnAngDiff(self.arTW[i], vBorder)) * cDeg * vR <= vHalf:
                    if abs(vR - cFlankRadius) <= 8.0:
                        self.vsOpen(i)
                        if self.arFloor[i] in sys_config.carLiquidFloors:
                            self.arFloor[i] = cdtBiomeFloor[self.arCB[i]]
                    else:
                        self.vsPutWall(i)
                    break
        for vBorder, vName in cdtFlankPasses.items():
            self.dtMarkers[vName] = self.dtPasses[vBorder]

    def vsRamparts(self):
        """A wall ring around every core, with a gate toward the Rift and one toward each neighbour. A river
        crosses it only in its deep channel (a sluice), which the seal step closes to ground units."""
        for vBiome in carBiomes:
            vCx, vCy = self.dtCores[vBiome]
            vIn = (cdtAxis[vBiome] + 180.0) % 360.0
            dtNames = fnNeighbourGates(vBiome)
            for i, vD in self.sGrid.fnDisc(vCx + 0.5, vCy + 0.5, cRampartRadius + 20.0):
                vInner = cRampartRadius + 6.0 * (self.arN3[i] - 0.5)
                if not (vInner <= vD <= vInner + 11.0 + 4.0 * (self.arThick[i] - 0.5)):
                    continue
                vPhi = _fnAngDiff(math.degrees(math.atan2(i // cWidth - vCy - 0.5, i % cWidth - vCx - 0.5)), vIn)
                vGate = any(abs(_fnAngDiff(vPhi, g)) * cDeg * vD < cGateHalf for g in cdtGatePhi.values())
                if vGate:
                    self.vsOpen(i)
                    if self.arFloor[i] in sys_config.carLiquidFloors:
                        self.arFloor[i] = cdtBiomeFloor[vBiome]
                elif not self.arChannel[i]:
                    self.vsPutWall(i)
            for vKey, vPhi in cdtGatePhi.items():
                vX, vY = fnLocal(vBiome, vPhi, cRampartRadius + 5.0)
                self.dtMarkers[dtNames[vKey]] = (int(round(vX)), int(round(vY)))
        for vName, (vBiome, _, _) in cdtRivers.items():
            _, arDense = self.dtRivers[vName]
            vCx, vCy = self.dtCores[vBiome]
            vX, vY = min(arDense, key=lambda p: abs(math.hypot(p[0] - vCx, p[1] - vCy) - cRampartRadius - 5.0))
            self.dtMarkers["%s Sluice" % vName] = (int(round(vX)), int(round(vY)))

    def vsBorder(self):
        for i in range(self.vTiles):
            vX, vY = i % cWidth, i // cWidth
            if min(vX, vY, cWidth - 1 - vX, cHeight - 1 - vY) < 3.0 + 8.0 * self.arEdge[i]:
                self.vsPutWall(i)

    # -- open areas ------------------------------------------------------------------------------

    def vsPads(self):
        for vBiome in carBiomes:
            for k, vPhi in enumerate(carPadPhi):
                vNx, vNy = fnLocal(vBiome, vPhi, cPadDistance)
                vX, vY = int(round(vNx)), int(round(vNy))
                for vDy in range(-6, 7):
                    for vDx in range(-6, 7):
                        i = (vY + vDy) * cWidth + vX + vDx
                        if self.arFloor[i] in sys_config.carLiquidFloors:
                            self.arNotes.append("Outpost pad of %s on liquid at (%d, %d)" % (carRegionNames[vBiome], vX, vY))
                        self.vsOpen(i)
                        if max(abs(vDx), abs(vDy)) <= 3:
                            self.arFloor[i] = sys_config.cPadFloor
                        elif max(abs(vDx), abs(vDy)) == 4:
                            self.arFloor[i] = sys_config.cPadRingFloor
                        elif self.arFloor[i] in sys_config.carLiquidFloors:
                            self.arFloor[i] = cdtBiomeFloor[vBiome]
                self.arPads.append({"name": "%s Outpost %d" % (cdtBases[vBiome][3], k + 1),
                                    "biome": carRegionNames[vBiome], "x": vX, "y": vY})

    def vsGardens(self):
        """One 3x3 pocket of every foreign resource in each base's garden."""
        for vBiome in carBiomes:
            arForeign = [g for g in sys_config.cdtResourceFloors if cdtHomes[g] != vBiome]
            arSlots = self.fnGardenSlots(vBiome)
            dtGarden = {}
            for vGroup, (vSx, vSy) in zip(arForeign, arSlots):
                for vDy in (-1, 0, 1):
                    for vDx in (-1, 0, 1):
                        i = (vSy + vDy) * cWidth + vSx + vDx
                        self.vsOpen(i)
                        self.arFloor[i] = cdtPocketFloor[vGroup]
                        if self.arFloor[i] in sys_config.carLiquidFloors:
                            self.arProt[i] = 1
                dtGarden[vGroup] = (vSx, vSy)
            self.dtGarden[vBiome] = dtGarden
            vGx, vGy = fnLocal(vBiome, 180.0, cGardenDistance)
            self.dtMarkers["%s Garden" % cdtBases[vBiome][3]] = (int(round(vGx)), int(round(vGy)))

    def vsSpawnsAndPlazas(self):
        for vBiome in carBiomes:
            vKey = cdtBases[vBiome][0]
            vSx, vSy = _fnPolar(cdtAxis[vBiome], cSpawnRadius)
            self.dtSpawns[vKey] = (vSx, vSy)
            for i, _ in self.sGrid.fnDisc(vSx, vSy, 15.0):
                self.vsOpen(i)
                if self.arFloor[i] in sys_config.carLiquidFloors:
                    self.arFloor[i] = cdtBiomeFloor[cRift]
            self.arOre[vSy * cWidth + vSx] = sys_config.cSpawnOverlay
            vCx, vCy = self.dtCores[vBiome]
            for i in self.fnKeepSquare(vBiome):
                self.vsOpen(i)
            for vY in range(vCy - 8, vCy + 10):
                for vX in range(vCx - 8, vCx + 10):
                    i = vY * cWidth + vX
                    vEdge = vX in (vCx - 8, vCx + 9) or vY in (vCy - 8, vCy + 9)
                    self.arFloor[i] = sys_config.cPlazaBorderFloor if vEdge else sys_config.cPlazaFloor

    def vsDecorate(self):
        sRng = random.Random(self.vSeed + 99)
        for i in range(self.vTiles):
            if self.arWall[i] is not None or self.arOre[i] is not None or self.arProt[i] or self.arKeep[i]:
                continue
            if self.arFloor[i] in carNoDecorFloors or self.arR[i] < 32.0:
                continue
            vRegion = self.arRegion[i]
            vRoll = sRng.random()
            if self.arSpore[i] and vRoll < 0.02:
                self.arWall[i] = "spore-cluster"
            elif vRoll < (0.004 if vRegion == cRift else 0.011):
                self.arWall[i] = ("siratla-stone-boulder" if self.arFloor[i] == "siratla-stone"
                                  else cdtBoulders[vRegion])

    # -- finishing -------------------------------------------------------------------------------

    def fnWalkable(self, i):
        vWall = self.arWall[i]
        return ((vWall is None or vWall in sys_config.carNonSolidBlocks)
                and self.arFloor[i] not in sys_config.carDeepFloors)

    def fnCoreGoal(self, vBiome):
        vX, vY = self.dtCores[vBiome]
        return (vY - 3) * cWidth + vX

    def vsConnectivity(self):
        """Every spawn and every other base must reach each base on foot. Natural walls may be cut for
        that; structural walls and liquids never are, so a layout fault shows up in the checks."""
        for vBiome in carBiomes:
            vGoal = self.fnCoreGoal(vBiome)
            arDist = self.sGrid.fnBfs(vGoal, self.fnWalkable)
            arStarts = [(k, v[1] * cWidth + v[0]) for k, v in self.dtSpawns.items()]
            arStarts += [(carRegionNames[b], self.fnCoreGoal(b)) for b in carBiomes if b != vBiome]
            for vLabel, vStart in arStarts:
                if arDist[vStart] >= 0:
                    continue

                def fnStepCost(j):
                    if self.fnWalkable(j):
                        return 1
                    if self.arProt[j] == 0 and self.arFloor[j] not in sys_config.carDeepFloors:
                        return 30
                    return None

                arPath = self.sGrid.fnCheapestPath(vStart, vGoal, fnStepCost)
                vCut = 0
                for j in arPath:
                    for k, _ in self.sGrid.fnDisc(j % cWidth, j // cWidth, 2.0):
                        if not self.fnWalkable(k) and self.arProt[k] == 0 and self.arFloor[k] not in sys_config.carDeepFloors:
                            self.arWall[k] = None
                            vCut += 1
                self.arNotes.append("Cut %d natural wall tiles to connect %s to the %s"
                                    % (vCut, vLabel, carRegionNames[vBiome]) if arPath
                                    else "No ground route from %s to the %s" % (vLabel, carRegionNames[vBiome]))
                arDist = self.sGrid.fnBfs(vGoal, self.fnWalkable)

    def vsSeal(self):
        self.sGrid.vsSealDeepWalls(self.arFloor, self.arWall, sys_config.carDeepFloors, sys_config.carNonSolidBlocks)

    def fnNearestWalkable(self, arNominal, fnInside):
        for vRad in range(0, 40):
            arFound = [(vD, i) for i, vD in self.sGrid.fnDisc(arNominal[0], arNominal[1], vRad + 0.5)
                       if self.fnWalkable(i) and fnInside(i)]
            if arFound:
                i = min(arFound)[1]
                return i % cWidth, i // cWidth
        return arNominal

    def fnBarrierTests(self):
        """Per base: with its three gates closed, the Rift spawn facing it cannot reach the core (rampart and
        sluice hold). Per ridge: with its flank pass closed, its two sectors cannot reach each other
        outside the Rift (the test stays in those two sectors; the other ridges halve along the borders)."""
        arTests = []
        for vBiome in carBiomes:
            vKey, _, vLabel, _ = cdtBases[vBiome]
            vX, vY = self.dtCores[vBiome]
            arTests.append({"label": "%s rampart" % cdtBases[vBiome][3], "names": list(fnNeighbourGates(vBiome).values()),
                            "radius": 13, "start": self.dtSpawns[vKey], "goal": (vX, vY - 3), "region": None})

        for vBorder, vName in cdtFlankPasses.items():
            arSides = sorted(carBiomes, key=lambda b: abs(_fnAngDiff(cdtAxis[b], vBorder)))[:2]

            def fnInside(j, arSides=arSides):
                return self.arCB[j] in arSides and self.arR[j] > cRiftRadius + 8.0

            arPoints = [self.fnNearestWalkable(_fnPolar(cdtAxis[b], 170.0),
                                               lambda j, b=b: self.arCB[j] == b and fnInside(j)) for b in arSides]
            arTests.append({"label": "%s ridge" % vName.replace(" Pass", ""), "names": [vName], "radius": 14,
                            "start": arPoints[0], "goal": arPoints[1], "region": fnInside})
        return arTests

    def fnResult(self, vName):
        arCores = []
        for vBiome in carBiomes:
            vKey, vTeam, vLabel, _ = cdtBases[vBiome]
            vX, vY = self.dtCores[vBiome]
            arCores.append({"team": vTeam, "key": vKey, "label": vLabel, "x": vX, "y": vY, "region": vBiome})
        arLinks = []
        for vFrom, vTo in ((cForest, cFrozen), (cFrozen, cForest)):
            arLinks.append({"label": "Boats %s -> %s" % (cdtBases[vFrom][3], cdtBases[vTo][3]),
                            "start": self.dtHarbours[vFrom], "core": self.dtCores[vTo], "reach": cHarbourReach})
        dtColors = dict(cdtRouteColors)
        dtColors["Boats Forest -> Frozen"] = (40, 120, 255)
        dtColors["Boats Frozen -> Forest"] = (0, 220, 220)
        dtLabels = {cdtBases[b][0]: "Rift spawn toward %s" % carRegionNames[b].split(" (")[0] for b in carBiomes}
        return cm_layout.clLayoutResult(
            vName=vName, vDescription=cDescription, vWidth=cWidth, vHeight=cHeight,
            arFloor=self.arFloor, arOverlay=self.arOre, arWall=self.arWall, arCore=(cCx, cCy),
            dtSpawns=dict(self.dtSpawns), dtSpawnLabels=dtLabels, dtRouteColors=dtColors,
            arRegion=list(self.arRegion), arRegionNames=carRegionNames, dtMarkers=self.dtMarkers,
            arPads=self.arPads, arBarrierTests=self.fnBarrierTests(), arNotes=self.arNotes, sMatch="pvp",
            arTeamCores=arCores, arNavalLinks=arLinks,
            dtResourceRules={"homes": dict(cdtHomes), "bases": list(carBiomes), "pocketCap": cPocketCap,
                             "homeMin": cHomeMin})


class clBiomesWarfront(cm_layout.clLayout):
    cKey = "biomes-warfront"
    cName = "Biomes Warfront"
    cSummary = "PvP for 5: one base per biome, waves rise from the Rift, empty slots become defender bots"
    cDefaultSeed = 2027
    cOrder = 30

    def fnBuild(self, vSeed):
        sTerrain = clWarfrontTerrain(vSeed)
        arSteps = (
            ("noise fields", sTerrain.vsNoise), ("polar grid", sTerrain.vsPolar), ("roads", sTerrain.vsRoads),
            ("floors", sTerrain.vsFloors),
            ("rivers", sTerrain.vsRivers), ("lagoon and harbours", sTerrain.vsLagoon), ("fords", sTerrain.vsFords),
            ("volcano", sTerrain.vsVolcano), ("frozen", sTerrain.vsFrozen), ("desert", sTerrain.vsDesert),
            ("forest", sTerrain.vsForest), ("keep-clear zones", sTerrain.vsKeepClear),
            ("natural walls", sTerrain.vsNaturalWalls), ("ridges", sTerrain.vsRidges),
            ("ramparts", sTerrain.vsRamparts), ("map border", sTerrain.vsBorder), ("outpost pads", sTerrain.vsPads),
            ("resource gardens", sTerrain.vsGardens), ("spawns and plazas", sTerrain.vsSpawnsAndPlazas),
            ("decorations", sTerrain.vsDecorate), ("connectivity", sTerrain.vsConnectivity),
            ("sealed sluices", sTerrain.vsSeal),
        )
        for vLabel, vsStep in arSteps:
            vTs = time.time()
            vsStep()
            print("  %-22s %6.1fs" % (vLabel, time.time() - vTs))
        return sTerrain.fnResult(self.cName)
