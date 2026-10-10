"""Biomes Confluence: five biome lanes around a harbour core, with two navigable rivers.

The core stands on the shore of Confluence Lagoon. Greenwater (water) runs to it from the forest spawn in
the west and Rimeflow (cryofluid) from the frozen spawn in the north. Both spawns sit in a shallow pool at
their river's head, so boats spawned there can sail all the way to the lagoon and a shallow inlet that
touches the core plaza, while ground units walk ashore. Every biome is a lane of its own between sealed
ridges: spawn -> biome barrier with named choke points -> gate in the Harbour Wall -> core. Rivers cross
walls only through sluices, deep channels whose banks are walls standing on the same liquid, so they stay
closed to ground units (Pathfinder allDeep) and open to boats.
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

cDesert, cSemiarid, cFrozen, cForest, cVolcano, cBasin = range(6)
carRegionNames = ("Desert (E)", "Semi-arid (NE)", "Frozen (N)", "Forest (W)", "Volcano (SW)", "Confluence Basin")

# Biome borders (degrees counter-clockwise from east; +y is north), each sealed by a ridge.
carBorders = (22.0, 68.0, 135.0, 205.0, 285.0)

cdtSpawns = {
    "frozen": (380, 764),      # harbour: head of Rimeflow
    "semiarid": (730, 730),
    "desert": (776, 360),
    "forest": (38, 455),       # harbour: head of Greenwater
    "volcano": (70, 70),
}
carNavalSpawnKeys = ("forest", "frozen")
cdtSpawnLabels = {"frozen": "North spawn (Frozen, harbour)", "semiarid": "North-east spawn (Semi-arid)",
                  "desert": "East spawn (Desert)", "forest": "West spawn (Forest, harbour)",
                  "volcano": "South-west spawn (Volcano)"}
cdtRouteColors = {"frozen": (0, 190, 255), "semiarid": (255, 150, 0), "desert": (235, 215, 0),
                  "forest": (40, 200, 60), "volcano": (255, 50, 50)}

# Navigable rivers, from their spawn pool to the lagoon: control points, liquid, bank floors.
carGreenwater = ((38, 455), (80, 445), (125, 460), (165, 436), (205, 446), (250, 426), (296, 416), (330, 421))
carRimeflow = ((380, 764), (370, 720), (386, 680), (367, 642), (379, 600), (368, 560), (382, 522), (380, 498),
               (364, 470), (352, 446))
carLagoon = (352, 420, 30)                     # centre x, y and radius of Confluence Lagoon
carInlet = ((362, 416), (378, 408), (391, 401))  # shallow inlet from the lagoon to the plaza's west edge
cHarbourPool = 9.0                             # radius of the shallow pool around each harbour spawn

cdtFords = {"Old Ford": ("Greenwater", (112, 455)), "Mill Ford": ("Greenwater", (222, 440)),
            "Thaw Ford": ("Rimeflow", (373, 575))}

# Harbour Wall around the basin: land gates (angle) and the radius band.
cHarbourRadius = 98.0
cdtGates = {"East Gate": 350.0, "North-east Gate": 45.0, "North Gate": 87.0, "West Gate": 187.0,
            "South-west Gate": 245.0}

# Biome barriers (wall arcs across a lane): radius, half thickness, passes (angle, half width, name).
carBarriers = (
    {"name": "Thornwood", "biome": cForest, "r": 239.0, "half": 7.0,
     "passes": ((151.0, 8.0, "North Thorn Pass"), (191.0, 8.0, "South Thorn Pass"))},
    {"name": "Glacier Wall", "biome": cFrozen, "r": 245.0, "half": 7.0,
     "passes": ((80.0, 8.0, "Rime Pass"), (123.0, 8.0, "Hoarfrost Pass"))},
    {"name": "Ochre Mesa", "biome": cSemiarid, "r": 240.0, "half": 22.0,
     "passes": ((33.0, 6.5, "Ochre Canyon"), (57.0, 5.5, "Wind Gap"))},
    {"name": "Dune Wall", "biome": cDesert, "r": 256.0, "half": 6.5,
     "passes": ((300.0, 6.5, "Glass Gap"), (334.0, 6.5, "Mirage Pass"), (8.0, 6.5, "Saltwind Breach"))},
)

# Volcano: a lava river arc across the lane with two basalt bridges, a crater and pyromagma creeks.
cLavaRadius = 225.0
cdtBridges = {"Cinder Bridge": 226.0, "Obsidian Bridge": 264.0}
carCrater = (232, 132, 38)
carPyroCreeks = (((300, 300), (322, 278), (338, 252), (346, 222)), ((300, 322), (282, 296), (270, 268)))
carLavaPools = ((300, 230, 7), (250, 268, 6), (322, 232, 6))

carTarPits = ((680, 250, 12), (705, 430, 10), (585, 300, 8), (600, 450, 9))
carWreck = (705, 340, 30)
carSaltPan = (560, 160, 40)
carOasis = (45.0, 330.0)
carSporeGrove = (148.0, 300.0, 42.0)          # angle, radius from the core, size

carOutposts = (  # name, biome, nominal angle and radius of a 7x7 core-zone pad
    ("Meltwater Outpost", cFrozen, 84.0, 185.0), ("Siratla Outpost", cFrozen, 117.0, 330.0),
    ("Steppe Outpost", cSemiarid, 45.0, 170.0), ("Oasis Outpost", cSemiarid, 38.0, 335.0),
    ("Dunewatch Outpost", cDesert, 338.0, 180.0), ("Wreckage Outpost", cDesert, 12.0, 330.0),
    ("Millrace Outpost", cForest, 188.0, 165.0), ("Sporewood Outpost", cForest, 152.0, 330.0),
    ("Ember Outpost", cVolcano, 240.0, 165.0), ("Ashfall Outpost", cVolcano, 262.0, 330.0),
)

cdtBiomeFloor = {cDesert: "sand-floor", cSemiarid: "dirt", cFrozen: "snow", cForest: "grass", cVolcano: "basalt",
                 cBasin: "stone"}
cdtBoulders = {cDesert: "sand-boulder", cSemiarid: "dacite-boulder", cFrozen: "snow-boulder", cForest: "boulder",
               cVolcano: "basalt-boulder", cBasin: "boulder"}
carNoDecorFloors = sys_config.carLiquidFloors | {"glowingvein", "core-zone", "metal-floor", "metal-floor-damaged",
                                                 "dark-panel-1", "dark-panel-2", "dark-panel-3", "dark-panel-4",
                                                 "dark-panel-5", "dark-panel-6"}

cDescription = (
    "[accent]800x800 PvE survival for 4-8 players, built for Exogenesis Old.[]\n"
    "Defend the harbour core of Confluence Lagoon. Five biome lanes lead to it: the frozen north, the "
    "semi-arid north-east, the eastern desert, the western forest and the volcano in the south-west. "
    "Boats sail down Greenwater from the forest and Rimeflow, the cryofluid river, from the north, and can "
    "reach the core from the lagoon. Ore nodes are re-rolled every time the map is loaded. Thermal "
    "generators can be built anywhere on lava. Claim the core-zone outposts to expand. Bosses from wave 40; "
    "sagittarius from wave 300."
)


def _fnAngDiff(vA, vB):
    return (vA - vB + 180.0) % 360.0 - 180.0


def _fnSector(vAngle):
    if 22.0 <= vAngle < 68.0:
        return cSemiarid
    if 68.0 <= vAngle < 135.0:
        return cFrozen
    if 135.0 <= vAngle < 205.0:
        return cForest
    if 205.0 <= vAngle < 285.0:
        return cVolcano
    return cDesert


def _fnPolar(vAngle, vRadius):
    return int(round(cCx + vRadius * math.cos(vAngle * cDeg))), int(round(cCy + vRadius * math.sin(vAngle * cDeg)))


class clConfluenceTerrain:
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
        self.arChannel = bytearray(vTiles)     # deep channel of a navigable river (stays open in sluices)
        self.arSpore = bytearray(vTiles)
        self.arWreck = bytearray(vTiles)
        self.dtMarkers = {}
        self.arPads = []
        self.arNotes = []
        self.dtRivers = {}

    # -- setup -----------------------------------------------------------------------------------

    def vsNoise(self):
        vS, sGrid = self.vSeed, self.sGrid
        self.arWarp = sGrid.fnFbm(vS + 1, 190, 3)
        self.arN1 = sGrid.fnFbm(vS + 2, 42, 3)
        self.arN2 = sGrid.fnFbm(vS + 3, 13, 2)
        self.arN3 = sGrid.fnFbm(vS + 4, 100, 3)
        self.arBlend = sGrid.fnFbm(vS + 5, 7, 2)
        self.arThick = sGrid.fnFbm(vS + 6, 36, 3)
        self.arRock = sGrid.fnFbm(vS + 7, 30, 4)
        self.arGrove = sGrid.fnFbm(vS + 8, 15, 3)
        self.arDune = sGrid.fnFbm(vS + 9, 16, 3, vStretchY=4.0)
        self.arVein = sGrid.fnFbm(vS + 10, 38, 3)
        self.arFine = sGrid.fnFbm(vS + 11, 4, 1)
        self.arEdge = sGrid.fnFbm(vS + 12, 24, 2)

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
                self.arRegion[i] = cBasin if vR < cHarbourRadius + 6.0 else vBiome
                i += 1

    # -- floors ----------------------------------------------------------------------------------

    def fnPalette(self, vBiome, i):
        vA, vC, vD = self.arN1[i], self.arN2[i], self.arN3[i]
        vR = self.arR[i]
        if vBiome == cBasin:
            if vD > 0.84:
                return "darksand"
            if vA > 0.74:
                return "grass"
            if vC > 0.84:
                return "dirt"
            if vA < 0.10:
                return "crater-stone"
            return "stone"
        if vBiome == cDesert:
            if vD < 0.13 and vR > 230:
                return "salt"
            if vC > 0.88 and vA > 0.35:
                return "shale"
            if vA > 0.78:
                return "darksand"
            return "sand-floor"
        if vBiome == cSemiarid:
            if vD > 0.86 and vC > 0.45:
                return "shale"
            if vD < 0.12:
                return "salt"
            if vA > 0.66:
                return "dacite"
            if vC > 0.84:
                return "darksand"
            return "dirt"
        if vBiome == cFrozen:
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
        if vBiome == cForest:
            if vA > 0.64:
                return "moss"
            if vC > 0.85:
                return "dirt"
            if vD < 0.14 and vC > 0.45:
                return "mud"
            return "grass"
        if vD < 0.15:
            return "crater-stone"
        vHot = math.hypot(i % cWidth - carCrater[0], i // cWidth - carCrater[1]) < 80.0
        if vC > (0.92 if vHot else 0.965):
            return "magmarock"
        if vC > (0.75 if vHot else 0.89):
            return "hotrock"
        if vA > 0.72:
            return "char"
        return "basalt"

    def fnGlacier(self, i):
        return self.arCB[i] == cFrozen and self.arR[i] > 300.0 + 30.0 * (self.arN3[i] - 0.5)

    def vsFloors(self):
        for i in range(self.vTiles):
            vBiome = self.arRegion[i]
            if vBiome != cBasin:
                # biomes blend into each other across their borders (behind the ridges anyway)
                vBand = abs(_fnAngDiff(self.arTW[i], min(carBorders, key=lambda b: abs(_fnAngDiff(self.arTW[i], b)))))
                if vBand * cDeg * self.arR[i] < 14.0 and self.arBlend[i] < 0.3:
                    vBiome = _fnSector((self.arTW[i] + 15.0 * (1 if self.arBlend[i] < 0.15 else -1)) % 360.0)
            self.arFloor[i] = self.fnPalette(vBiome, i)

    def vsSetFloor(self, i, vFloor, vProt=None):
        self.arFloor[i] = vFloor
        if vProt is not None and self.arProt[i] < vProt:
            self.arProt[i] = vProt

    # -- water -----------------------------------------------------------------------------------

    def vsRivers(self):
        """Greenwater (deep water, shallow and sand banks) and Rimeflow (cryofluid, ice banks)."""
        for vName, arPoints, vSeed in (("Greenwater", carGreenwater, 30), ("Rimeflow", carRimeflow, 31)):
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
                        self.vsSetFloor(i, "darksand" if self.arN2[i] > 0.55 else "mud")
                else:
                    if vS <= 0.0:
                        self.vsSetFloor(i, "pooled-cryofluid", 1)
                        self.arChannel[i] = 1
                    elif vS <= 3.0:
                        self.vsSetFloor(i, "ice", 1)
                    elif vS <= 6.0 and self.arFloor[i] not in sys_config.carLiquidFloors:
                        self.vsSetFloor(i, "ice-snow")

    def vsLagoon(self):
        """Confluence Lagoon in the basin, the shallow inlet to the plaza and the harbour spawn pools."""
        vLx, vLy, vLr = carLagoon
        for i, vD in self.sGrid.fnDisc(vLx, vLy, vLr + 4.0):
            vS = vD - (vLr + 4.0 * (self.arN3[i] - 0.5))
            if vS <= -8.0:
                self.vsSetFloor(i, "deep-water", 1)
                self.arChannel[i] = 1
            elif vS <= -2.0:
                self.vsSetFloor(i, "shallow-water", 1)
                self.arChannel[i] = 0
            elif vS <= 1.0:
                self.vsSetFloor(i, "sand-water", 1)
                self.arChannel[i] = 0
        dtField, _ = self.sGrid.fnPolylineField(carInlet, 4.0)
        for i, vD in dtField.items():
            if vD <= 2.6:
                self.vsSetFloor(i, "shallow-water", 1)
            elif vD <= 3.6 and self.arFloor[i] not in sys_config.carLiquidFloors:
                self.vsSetFloor(i, "sand-water", 1)
        for vKey in carNavalSpawnKeys:
            vSx, vSy = cdtSpawns[vKey]
            for i, vD in self.sGrid.fnDisc(vSx, vSy, cHarbourPool + 3.0):
                if vD <= cHarbourPool:
                    self.vsSetFloor(i, "shallow-water", 1)
                    self.arChannel[i] = 0
                elif self.arFloor[i] not in sys_config.carLiquidFloors:
                    self.vsSetFloor(i, "sand-water", 1)

    def vsFords(self):
        for vName, (vRiver, arNominal) in cdtFords.items():
            dtField, arDense = self.dtRivers[vRiver]
            arCentre, arTiles = self.sGrid.fnAcross(dtField, arDense, arNominal, 6.0)
            self.dtMarkers[vName] = arCentre
            for i, _ in self.sGrid.fnDisc(arCentre[0], arCentre[1], 16.0):
                self.arKeep[i] = 1
            for i in arTiles:
                if self.arFloor[i] in sys_config.carDeepFloors:
                    self.vsSetFloor(i, "shallow-water")
                    self.arChannel[i] = 0
                    self.arProt[i] = 2

    # -- biome features --------------------------------------------------------------------------

    def vsVolcano(self):
        arPoints = [_fnPolar(vA, cLavaRadius + 7.0 * math.sin(vA / 9.0)) for vA in range(196, 297, 5)]
        dtField, arDense = self.sGrid.fnPolylineField(arPoints, 14.0, vAmplitude=4.0, vScale=30.0,
                                                      vSeed=self.vSeed + 40)
        for i, vD in dtField.items():
            if self.arCB[i] != cVolcano:
                continue
            vHalf = 4.2 + 2.0 * self.arN1[i]                     # 8-12 tiles of slag
            if vD <= vHalf:
                self.vsSetFloor(i, "molten-slag", 1)
            elif vD <= vHalf + 2.5:
                self.vsSetFloor(i, "magmarock", 1)
            elif vD <= vHalf + 5.0 and self.arFloor[i] not in sys_config.carLiquidFloors:
                self.vsSetFloor(i, "hotrock", 1)
        for vName, vAngle in cdtBridges.items():
            arCentre, arTiles = self.sGrid.fnAcross(dtField, arDense, _fnPolar(vAngle, cLavaRadius), 7.0)
            self.dtMarkers[vName] = arCentre
            for i in arTiles:
                if dtField[i] <= 4.2 + 2.0 * self.arN1[i] + 5.0 and self.arCB[i] == cVolcano:
                    vCore = dtField[i] <= 4.2 + 2.0 * self.arN1[i] + 2.5
                    self.vsSetFloor(i, "basalt" if vCore else "hotrock")
                    self.arProt[i] = 2
                    self.arKeep[i] = 1
        for k, arCreek in enumerate(carPyroCreeks):
            dtCreek, _ = self.sGrid.fnPolylineField(arCreek, 6.0, vAmplitude=3.0, vScale=20.0,
                                                    vSeed=self.vSeed + 41 + k)
            for i, vD in dtCreek.items():
                if self.arFloor[i] in sys_config.carDeepFloors:
                    continue
                if vD <= 2.2:
                    self.vsSetFloor(i, "pyromagma", 1)
                elif vD <= 4.5:
                    self.vsSetFloor(i, "hotrock", 1)
        for vPx, vPy, vPr in carLavaPools:
            for i, vD in self.sGrid.fnDisc(vPx, vPy, vPr + 3.5):
                if vD < vPr - 2:
                    self.vsSetFloor(i, "molten-slag", 1)
                elif vD < vPr + 1.5:
                    self.vsSetFloor(i, "magmarock", 1)
                elif self.arFloor[i] not in sys_config.carLiquidFloors:
                    self.vsSetFloor(i, "hotrock", 1)

    def vsFrozen(self):
        for i in range(self.vTiles):
            if self.fnGlacier(i) and not self.arProt[i] and self.arFloor[i] not in sys_config.carLiquidFloors:
                if 1.0 - abs(2.0 * self.arVein[i] - 1.0) > 0.972:
                    self.arFloor[i] = "glowingvein"

    def vsSemiarid(self):
        vOx, vOy = _fnPolar(*carOasis)
        for i, vD in self.sGrid.fnDisc(vOx, vOy, 18.0):
            if vD < 4.5:
                self.vsSetFloor(i, "deep-water", 1)
            elif vD < 8.5:
                self.vsSetFloor(i, "shallow-water", 1)
            elif vD < 11.0:
                self.vsSetFloor(i, "sand-water", 1)
            elif vD < 17.0:
                self.vsSetFloor(i, "grass" if self.arN2[i] > 0.35 else "moss")
        self.dtMarkers["Last Oasis"] = (vOx, vOy)

    def vsDesert(self):
        dtTar = {}
        for vTx, vTy, vTr in carTarPits:
            for i, vD in self.sGrid.fnDisc(vTx, vTy, vTr + 6.0):
                vS = vD - vTr * (0.85 + 0.3 * self.arFine[i])
                if vS < dtTar.get(i, 99.0):
                    dtTar[i] = vS
        for i, vS in dtTar.items():
            if self.arCB[i] != cDesert or self.arProt[i]:
                continue
            if vS < -1.5:
                self.vsSetFloor(i, "tar", 1)
            elif vS < 4.0 and self.arFloor[i] not in sys_config.carLiquidFloors:
                self.vsSetFloor(i, "shale", 1 if vS < 1.0 else None)
        vWx, vWy, vWr = carWreck
        for i, vD in self.sGrid.fnDisc(vWx, vWy, vWr):
            if self.arCB[i] == cDesert and not self.arProt[i] and vD < vWr * (0.7 + 0.3 * self.arN3[i]):
                vC = self.arN2[i]
                if vC > 0.55:
                    self.arFloor[i] = "metal-floor-damaged"
                elif vC > 0.42:
                    self.arFloor[i] = "dark-panel-%d" % (1 + int(self.arFine[i] * 5.99))
                else:
                    self.arFloor[i] = "darksand"
                self.arWreck[i] = 1
        vPx, vPy, vPr = carSaltPan
        for i, vD in self.sGrid.fnDisc(vPx, vPy, vPr):
            if self.arCB[i] == cDesert and not self.arProt[i] and vD < vPr * (0.75 + 0.25 * self.arN3[i]):
                self.arFloor[i] = "salt"

    def vsForest(self):
        vGx, vGy = _fnPolar(carSporeGrove[0], carSporeGrove[1])
        for i, vD in self.sGrid.fnDisc(vGx, vGy, carSporeGrove[2]):
            if self.arCB[i] != cForest or self.arProt[i] or self.arFloor[i] in sys_config.carLiquidFloors:
                continue
            if vD < carSporeGrove[2] * (0.72 + 0.28 * self.arN3[i]):
                self.arFloor[i] = "spore-moss" if self.arN2[i] > 0.3 else "moss"
                self.arSpore[i] = 1

    # -- walls -----------------------------------------------------------------------------------

    def fnStructural(self, i):
        """Vanilla wall for a structural barrier on tile i (so the layout holds without the mod)."""
        vWall = sys_config.cdtNaturalWall.get(self.arFloor[i], "stone-wall")
        if vWall in sys_config.carModBlocks or vWall == "dark-metal":
            return "ice-wall" if self.arFloor[i] == "siratla-stone" else "stone-wall"
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

    def vsKeepClear(self):
        for vSx, vSy in cdtSpawns.values():
            for i, _ in self.sGrid.fnDisc(vSx, vSy, 24.0):
                self.arKeep[i] = 1
        for i, _ in self.sGrid.fnDisc(cCx + 0.5, cCy + 0.5, 16.0):
            self.arKeep[i] = 1

    def vsNaturalWalls(self):
        for i in range(self.vTiles):
            if self.arWall[i] is not None or self.arProt[i] or self.arKeep[i] or self.arR[i] < 118.0:
                continue
            vFloor = self.arFloor[i]
            if vFloor in sys_config.carLiquidFloors:
                continue
            vBiome = self.arCB[i]
            vRock, vGrove = self.arRock[i], self.arGrove[i]
            vWall = None
            if vBiome == cVolcano:
                if vRock > 0.90:
                    vWall = sys_config.cdtNaturalWall.get(vFloor, "dune-wall")
            elif vBiome == cFrozen:
                if self.fnGlacier(i):
                    if vRock > 0.88:
                        vWall = sys_config.cdtNaturalWall.get(vFloor, "ice-wall")
                elif vRock > 0.915:
                    vWall = sys_config.cdtNaturalWall.get(vFloor, "snow-wall")
                elif vGrove > 0.94:
                    vWall = "snow-pine"
            elif vBiome == cSemiarid:
                if vRock > 0.95:
                    vWall = sys_config.cdtNaturalWall.get(vFloor, "dirt-wall")
                elif vGrove > 0.97 and vFloor in ("grass", "dirt"):
                    vWall = "shrubs"
            elif vBiome == cDesert:
                if self.arWreck[i]:
                    if vRock > 0.9:
                        vWall = "dark-metal"
                elif self.arDune[i] > 0.935 or vRock > 0.965:
                    vWall = sys_config.cdtNaturalWall.get(vFloor, "sand-wall")
            elif vBiome == cForest:
                if vGrove > 0.80:
                    vWall = "spore-pine" if self.arSpore[i] else ("snow-pine" if vFloor == "snow" else "pine")
                elif vGrove > 0.775 and self.arBlend[i] > 0.5:
                    vWall = "shrubs"
                elif vRock > 0.97:
                    vWall = sys_config.cdtNaturalWall.get(vFloor, "stone-wall")
            if vWall is not None:
                self.arWall[i] = vWall

    def vsBand(self, i, vInPass):
        """A barrier tile: open in a pass and in a river's deep channel (a sluice), a wall elsewhere."""
        if vInPass:
            self.vsOpen(i)
            if self.arFloor[i] in sys_config.carLiquidFloors:
                self.arFloor[i] = cdtBiomeFloor[self.arCB[i]]
        elif not self.arChannel[i]:
            self.vsPutWall(i)

    def vsRidges(self):
        """Separator ridges along every warped biome border, 14-20 tiles thick (legSolid), with no pass."""
        for i in range(self.vTiles):
            vR = self.arR[i]
            if vR < cHarbourRadius:
                continue
            vHalf = 7.0 + 3.0 * self.arThick[i]
            for vBorder in carBorders:
                if abs(_fnAngDiff(self.arTW[i], vBorder)) * cDeg * vR <= vHalf:
                    self.vsPutWall(i)
                    break

    def vsHarbourWall(self):
        for i, _ in self.sGrid.fnDisc(cCx, cCy, cHarbourRadius + 20.0):
            vR = self.arR[i]
            vIn = cHarbourRadius + 6.0 * (self.arN3[i] - 0.5)
            if not (vIn <= vR <= vIn + 11.0 + 4.0 * (self.arThick[i] - 0.5)):
                continue
            vGate = any(abs(_fnAngDiff(self.arT[i], vA)) * cDeg * vR < 8.0 for vA in cdtGates.values())
            self.vsBand(i, vGate)
        for vName, vAngle in cdtGates.items():
            self.dtMarkers[vName] = _fnPolar(vAngle, cHarbourRadius + 5.0)

    def vsBarriers(self):
        for dtBarrier in carBarriers:
            vRadius, vHalf = dtBarrier["r"], dtBarrier["half"]
            for i in range(self.vTiles):
                if self.arCB[i] != dtBarrier["biome"]:
                    continue
                vR = self.arR[i]
                vMid = vRadius + 8.0 * (self.arN3[i] - 0.5)
                if abs(vR - vMid) > vHalf + 2.0 * (self.arThick[i] - 0.5):
                    continue
                vPass = any(abs(_fnAngDiff(self.arT[i], vA)) * cDeg * vR <= vW for vA, vW, _ in dtBarrier["passes"])
                self.vsBand(i, vPass)
                if not vPass and dtBarrier["name"] == "Ochre Mesa" and self.arWall[i]:
                    self.arWall[i] = "dacite-wall" if self.arFloor[i] == "dacite" else "dirt-wall"
                elif not vPass and dtBarrier["name"] == "Dune Wall" and self.arWall[i]:
                    self.arWall[i] = "dune-wall" if self.arFloor[i] == "darksand" else "sand-wall"
            for vA, _, vName in dtBarrier["passes"]:
                self.dtMarkers[vName] = _fnPolar(vA, vRadius)
        for vRiver, vName, vRadius in (("Greenwater", "Greenwater Sluice", 239.0), ("Rimeflow", "Rimeflow Sluice", 245.0),
                                       ("Greenwater", "Greenwater Mouth", cHarbourRadius + 5.0),
                                       ("Rimeflow", "Rimeflow Mouth", cHarbourRadius + 5.0)):
            _, arDense = self.dtRivers[vRiver]
            vX, vY = min(arDense, key=lambda p: abs(math.hypot(p[0] - cCx, p[1] - cCy) - vRadius))
            self.dtMarkers[vName] = (int(round(vX)), int(round(vY)))

    def vsCrater(self):
        vVx, vVy, vVr = carCrater
        for i, vD in self.sGrid.fnDisc(vVx, vVy, vVr + 12.0):
            if self.arCB[i] != cVolcano:
                continue
            vOuter = vVr + 8.0 * (self.arRock[i] - 0.5)
            vNotch = abs(_fnAngDiff(math.degrees(math.atan2(i // cWidth - vVy, i % cWidth - vVx)) % 360.0, 45.0)) < 9.0
            if vD < 17.0:
                self.vsSetFloor(i, "molten-slag", 1)
                self.arWall[i] = None
            elif vD < 21.0:
                self.vsSetFloor(i, "magmarock", 1)
            elif vD < vOuter and not vNotch:
                self.vsPutWall(i, "dune-wall")

    def vsBorder(self):
        for i in range(self.vTiles):
            vX, vY = i % cWidth, i // cWidth
            if min(vX, vY, cWidth - 1 - vX, cHeight - 1 - vY) < 3.0 + 8.0 * self.arEdge[i]:
                self.vsPutWall(i)

    # -- open areas ------------------------------------------------------------------------------

    def fnPadFits(self, vX, vY, vBiome):
        if not (12 <= vX < cWidth - 12 and 12 <= vY < cHeight - 12) or self.arRegion[vY * cWidth + vX] != vBiome:
            return False
        for vDy in range(-7, 8):
            for vDx in range(-7, 8):
                i = (vY + vDy) * cWidth + vX + vDx
                if self.arProt[i] in (1, 3) or self.arFloor[i] in sys_config.carLiquidFloors:
                    return False
        return True

    def vsPads(self):
        for vName, vBiome, vAngle, vRadius in carOutposts:
            vNx, vNy = _fnPolar(vAngle, vRadius)
            arSpot = None
            for vStep in range(0, 60, 2):
                arTry = [(vNx, vNy)] if vStep == 0 else [
                    (int(vNx + vStep * math.cos(k * math.pi / 8)), int(vNy + vStep * math.sin(k * math.pi / 8)))
                    for k in range(16)]
                arSpot = next((p for p in arTry if self.fnPadFits(p[0], p[1], vBiome)), None)
                if arSpot:
                    break
            if arSpot is None:
                self.arNotes.append("Could not place %s" % vName)
                continue
            vX, vY = arSpot
            for vDy in range(-6, 7):
                for vDx in range(-6, 7):
                    i = (vY + vDy) * cWidth + vX + vDx
                    self.vsOpen(i)
                    if max(abs(vDx), abs(vDy)) <= 3:
                        self.arFloor[i] = sys_config.cPadFloor
                    elif max(abs(vDx), abs(vDy)) == 4:
                        self.arFloor[i] = sys_config.cPadRingFloor
            self.arPads.append({"name": vName, "biome": carRegionNames[vBiome], "x": vX, "y": vY})

    def vsSpawnsAndPlaza(self):
        for vKey, (vSx, vSy) in cdtSpawns.items():
            if vKey not in carNavalSpawnKeys:
                for i, _ in self.sGrid.fnDisc(vSx, vSy, 15.0):
                    self.vsOpen(i)
                    if self.arFloor[i] in sys_config.carLiquidFloors:
                        self.arFloor[i] = cdtBiomeFloor[self.arCB[i]]
            else:
                for i, _ in self.sGrid.fnDisc(vSx, vSy, cHarbourPool):
                    self.vsOpen(i)
            self.arOre[vSy * cWidth + vSx] = sys_config.cSpawnOverlay
        for vY in range(cCy - 8, cCy + 10):
            for vX in range(cCx - 8, cCx + 10):
                i = vY * cWidth + vX
                self.vsOpen(i)
                vEdge = vX in (cCx - 8, cCx + 9) or vY in (cCy - 8, cCy + 9)
                self.arFloor[i] = sys_config.cPlazaBorderFloor if vEdge else sys_config.cPlazaFloor

    def vsDecorate(self):
        sRng = random.Random(self.vSeed + 99)
        for i in range(self.vTiles):
            if self.arWall[i] is not None or self.arOre[i] is not None or self.arProt[i] or self.arKeep[i]:
                continue
            if self.arFloor[i] in carNoDecorFloors or self.arR[i] < 20.0:
                continue
            vBiome = self.arRegion[i]
            vRoll = sRng.random()
            if self.arSpore[i] and vRoll < 0.02:
                self.arWall[i] = "spore-cluster"
            elif vRoll < (0.004 if vBiome == cBasin else 0.011):
                self.arWall[i] = ("siratla-stone-boulder" if self.arFloor[i] == "siratla-stone"
                                  else cdtBoulders[vBiome])

    # -- finishing -------------------------------------------------------------------------------

    def fnWalkable(self, i):
        vWall = self.arWall[i]
        return ((vWall is None or vWall in sys_config.carNonSolidBlocks)
                and self.arFloor[i] not in sys_config.carDeepFloors)

    def vsConnectivity(self):
        """Every spawn must reach the core on foot. Natural walls may be cut for that; structural walls
        and liquids never are, so a layout fault shows up in the checks instead of being papered over."""
        vGoal = (cCy - 3) * cWidth + cCx
        arDist = self.sGrid.fnBfs(vGoal, self.fnWalkable)
        for vKey, (vSx, vSy) in cdtSpawns.items():
            vStart = vSy * cWidth + vSx
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
            self.arNotes.append("Cut %d natural wall tiles to connect the %s spawn" % (vCut, vKey)
                                if arPath else "No ground route from the %s spawn" % vKey)
            arDist = self.sGrid.fnBfs(vGoal, self.fnWalkable)

    def vsSeal(self):
        self.sGrid.vsSealDeepWalls(self.arFloor, self.arWall, sys_config.carDeepFloors, sys_config.carNonSolidBlocks)

    def fnNearestWalkable(self, arNominal, fnInside):
        """The walkable tile inside the region closest to `arNominal` (barrier-test goals)."""
        for vRad in range(0, 40):
            arFound = [(vD, i) for i, vD in self.sGrid.fnDisc(arNominal[0], arNominal[1], vRad + 0.5)
                       if self.fnWalkable(i) and fnInside(i)]
            if arFound:
                i = min(arFound)[1]
                return i % cWidth, i // cWidth
        return arNominal

    def fnBarrierTests(self):
        """Two tests per lane, over the whole map. Closing the lane's passes must cut its spawn off from the
        core (so the ridges between lanes hold too); closing its gate must cut the land behind the passes
        off from the core (so the Harbour Wall and the river sluices hold)."""
        vCore = (cCx, cCy - 3)
        arLanes = (
            ("Forest", cForest, "forest", ["North Thorn Pass", "South Thorn Pass"], 15, 196.0, "West Gate"),
            ("Frozen", cFrozen, "frozen", ["Rime Pass", "Hoarfrost Pass"], 15, 78.0, "North Gate"),
            ("Semi-arid", cSemiarid, "semiarid", ["Ochre Canyon", "Wind Gap"], 30, 45.0, "North-east Gate"),
            ("Desert", cDesert, "desert", ["Glass Gap", "Mirage Pass", "Saltwind Breach"], 15, 352.0, "East Gate"),
            ("Volcano", cVolcano, "volcano", list(cdtBridges), 17, 240.0, "South-west Gate"),
        )
        arTests = []
        for vLabel, vBiome, vSpawn, arPasses, vRadius, vInsideAngle, vGate in arLanes:
            arInside = self.fnNearestWalkable(_fnPolar(vInsideAngle, 150.0),
                                              lambda j, b=vBiome: self.arCB[j] == b and self.arR[j] > 120.0)
            arTests.append({"label": vLabel + " passes", "names": arPasses, "radius": vRadius,
                            "start": cdtSpawns[vSpawn], "goal": vCore, "region": None})
            arTests.append({"label": vLabel + " gate", "names": [vGate], "radius": 14,
                            "start": arInside, "goal": vCore, "region": None})
        return arTests


class clBiomesConfluence(cm_layout.clLayout):
    cKey = "biomes-confluence"
    cName = "Biomes Confluence"
    cSummary = "Five biome lanes to a harbour core; boats sail Greenwater (water) and Rimeflow (cryofluid) to it"
    cDefaultSeed = 2026
    cOrder = 20

    def fnBuild(self, vSeed):
        sTerrain = clConfluenceTerrain(vSeed)
        arSteps = (
            ("noise fields", sTerrain.vsNoise), ("polar grid", sTerrain.vsPolar), ("floors", sTerrain.vsFloors),
            ("rivers", sTerrain.vsRivers), ("lagoon and harbours", sTerrain.vsLagoon), ("fords", sTerrain.vsFords),
            ("volcano", sTerrain.vsVolcano), ("frozen", sTerrain.vsFrozen), ("semi-arid", sTerrain.vsSemiarid),
            ("desert", sTerrain.vsDesert), ("forest", sTerrain.vsForest), ("keep-clear zones", sTerrain.vsKeepClear),
            ("natural walls", sTerrain.vsNaturalWalls), ("ridges", sTerrain.vsRidges),
            ("harbour wall", sTerrain.vsHarbourWall), ("biome barriers", sTerrain.vsBarriers),
            ("crater", sTerrain.vsCrater), ("map border", sTerrain.vsBorder), ("outpost pads", sTerrain.vsPads),
            ("spawns and plaza", sTerrain.vsSpawnsAndPlaza), ("decorations", sTerrain.vsDecorate),
            ("connectivity", sTerrain.vsConnectivity), ("sealed sluices", sTerrain.vsSeal),
        )
        for vLabel, vsStep in arSteps:
            vTs = time.time()
            vsStep()
            print("  %-22s %6.1fs" % (vLabel, time.time() - vTs))
        return cm_layout.clLayoutResult(
            vName=self.cName, vDescription=cDescription, vWidth=cWidth, vHeight=cHeight,
            arFloor=sTerrain.arFloor, arOverlay=sTerrain.arOre, arWall=sTerrain.arWall, arCore=(cCx, cCy),
            dtSpawns=dict(cdtSpawns), dtSpawnLabels=dict(cdtSpawnLabels), dtRouteColors=dict(cdtRouteColors),
            arRegion=list(sTerrain.arRegion), arRegionNames=carRegionNames, dtMarkers=sTerrain.dtMarkers,
            arPads=sTerrain.arPads, arNavalSpawnKeys=carNavalSpawnKeys, arBarrierTests=sTerrain.fnBarrierTests(),
            arNotes=sTerrain.arNotes)
