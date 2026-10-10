"""Terrain toolkit shared by the layout generators.

Everything here works on a grid of any size (`clGrid`): smooth value noise, rank-normalised fractal noise,
discs, smoothed and meandering polylines (rivers, ridges), ground and naval reachability, and the sealing
step that keeps liquid barriers closed to ground units. Tiles are row-major indexes, y = 0 is the bottom
row and +y is north, as in the map file.
"""

import heapq
import math
import random
from array import array
from collections import deque

import sys_config

cNavalDryCost = 7000     # Pathfinder.costNaval for a tile boats cannot enter (6000+ is never stepped on)


def fnSmooth(vT):
    return vT * vT * (3.0 - 2.0 * vT)


class clNoise1D:
    """Smooth 1D value noise, used to wobble radii and river offsets."""

    def __init__(self, vSeed, vScale):
        sRng = random.Random(vSeed)
        self.arValues = [sRng.random() for _ in range(4096)]
        self.vScale = vScale

    def __call__(self, vT):
        vF = vT / self.vScale
        vK = int(math.floor(vF))
        vU = fnSmooth(vF - vK)
        vA = self.arValues[vK % 4096]
        vB = self.arValues[(vK + 1) % 4096]
        return vA + (vB - vA) * vU


def fnCatmullRom(arPoints, vStep=1.5):
    """Points along a Catmull-Rom spline through `arPoints`, about `vStep` tiles apart."""
    arPts = [arPoints[0]] + list(arPoints) + [arPoints[-1]]
    arOut = []
    for vK in range(1, len(arPts) - 2):
        arP0, arP1, arP2, arP3 = arPts[vK - 1], arPts[vK], arPts[vK + 1], arPts[vK + 2]
        vSteps = max(2, int(math.dist(arP1, arP2) / vStep))
        for vS in range(vSteps):
            vT = vS / vSteps
            vT2, vT3 = vT * vT, vT * vT * vT
            arOut.append(tuple(0.5 * (2 * arP1[c] + (-arP0[c] + arP2[c]) * vT
                                      + (2 * arP0[c] - 5 * arP1[c] + 4 * arP2[c] - arP3[c]) * vT2
                                      + (-arP0[c] + 3 * arP1[c] - 3 * arP2[c] + arP3[c]) * vT3) for c in (0, 1)))
    arOut.append(tuple(arPoints[-1]))
    return arOut


def fnMeander(arDense, vAmplitude, vScale, vSeed):
    """Shifts each point of a dense centreline sideways by smooth noise (rivers that wander)."""
    if vAmplitude <= 0:
        return list(arDense)
    sNoise = clNoise1D(vSeed, vScale)
    vTotal = sum(math.dist(arDense[k - 1], arDense[k]) for k in range(1, len(arDense)))
    arOut = []
    vLength = 0.0
    for vK, (vX, vY) in enumerate(arDense):
        arA = arDense[max(0, vK - 1)]
        arB = arDense[min(len(arDense) - 1, vK + 1)]
        vTx, vTy = arB[0] - arA[0], arB[1] - arA[1]
        vNorm = math.hypot(vTx, vTy) or 1.0
        if vK:
            vLength += math.dist(arDense[vK - 1], arDense[vK])
        # the wander fades out over the last 30 tiles at each end, so both ends stay where they were put
        vFade = min(1.0, vLength / 30.0, (vTotal - vLength) / 30.0)
        vOff = vAmplitude * vFade * (sNoise(vLength) - 0.5) * 2.0
        arOut.append((vX - vTy / vNorm * vOff, vY + vTx / vNorm * vOff))
    return arOut


class clGrid:
    """Geometry and noise on a vWidth x vHeight tile grid."""

    def __init__(self, vWidth, vHeight):
        self.vWidth = vWidth
        self.vHeight = vHeight
        self.vTiles = vWidth * vHeight

    # -- geometry --------------------------------------------------------------------------------

    def fnDisc(self, vCx, vCy, vRad):
        """(index, distance) for every tile within `vRad` of (vCx, vCy)."""
        vX0, vX1 = max(0, int(vCx - vRad) - 1), min(self.vWidth - 1, int(vCx + vRad) + 1)
        vY0, vY1 = max(0, int(vCy - vRad) - 1), min(self.vHeight - 1, int(vCy + vRad) + 1)
        vR2 = vRad * vRad
        for vY in range(vY0, vY1 + 1):
            vDy = vY - vCy
            vBase = vY * self.vWidth
            for vX in range(vX0, vX1 + 1):
                vDx = vX - vCx
                vDd = vDx * vDx + vDy * vDy
                if vDd <= vR2:
                    yield vBase + vX, math.sqrt(vDd)

    def fnNeighbours(self, i):
        """The 4-way neighbours of tile i that lie on the map."""
        vX = i % self.vWidth
        arOut = []
        if vX > 0:
            arOut.append(i - 1)
        if vX < self.vWidth - 1:
            arOut.append(i + 1)
        if i >= self.vWidth:
            arOut.append(i - self.vWidth)
        if i < self.vTiles - self.vWidth:
            arOut.append(i + self.vWidth)
        return arOut

    def fnPolylineField(self, arPoints, vMaxD, vAmplitude=0.0, vScale=40.0, vSeed=0):
        """({tile: distance to the smoothed, optionally meandering polyline}, dense centreline)."""
        arDense = fnMeander(fnCatmullRom(arPoints), vAmplitude, vScale, vSeed)
        dtField = {}
        for vK in range(len(arDense) - 1):
            vAx, vAy = arDense[vK]
            vBx, vBy = arDense[vK + 1]
            vVx, vVy = vBx - vAx, vBy - vAy
            vL2 = vVx * vVx + vVy * vVy or 1e-9
            vX0, vX1 = max(0, int(min(vAx, vBx) - vMaxD)), min(self.vWidth - 1, int(max(vAx, vBx) + vMaxD) + 1)
            vY0, vY1 = max(0, int(min(vAy, vBy) - vMaxD)), min(self.vHeight - 1, int(max(vAy, vBy) + vMaxD) + 1)
            for vY in range(vY0, vY1 + 1):
                for vX in range(vX0, vX1 + 1):
                    vT = ((vX - vAx) * vVx + (vY - vAy) * vVy) / vL2
                    vT = 0.0 if vT < 0.0 else (1.0 if vT > 1.0 else vT)
                    vDx, vDy = vX - (vAx + vVx * vT), vY - (vAy + vVy * vT)
                    vD = math.sqrt(vDx * vDx + vDy * vDy)
                    if vD <= vMaxD:
                        i = vY * self.vWidth + vX
                        vOld = dtField.get(i)
                        if vOld is None or vD < vOld:
                            dtField[i] = vD
        return dtField, arDense

    def fnNearestOnLine(self, arDense, arNominal):
        """Index of the centreline point closest to `arNominal`."""
        return min(range(len(arDense)),
                   key=lambda k: (arDense[k][0] - arNominal[0]) ** 2 + (arDense[k][1] - arNominal[1]) ** 2)

    def fnAcross(self, dtField, arDense, arNominal, vAlong):
        """Tiles of a polyline field within `vAlong` tiles, measured along the line, of the centreline point
        nearest `arNominal`: a band straight across the line (fords, bridges, sluices)."""
        vK = self.fnNearestOnLine(arDense, arNominal)
        vCx, vCy = arDense[vK]
        arA, arB = arDense[max(0, vK - 3)], arDense[min(len(arDense) - 1, vK + 3)]
        vTx, vTy = arB[0] - arA[0], arB[1] - arA[1]
        vNorm = math.hypot(vTx, vTy) or 1.0
        vTx, vTy = vTx / vNorm, vTy / vNorm
        arTiles = [i for i, _ in self.fnDisc(vCx, vCy, vAlong + 30.0)
                   if i in dtField and abs((i % self.vWidth - vCx) * vTx + (i // self.vWidth - vCy) * vTy) <= vAlong]
        return (int(round(vCx)), int(round(vCy))), arTiles

    # -- noise -----------------------------------------------------------------------------------

    def fnValueNoise(self, vSeed, vSx, vSy):
        """Smooth value noise over the whole grid, computed row-wise for speed."""
        sRng = random.Random(vSeed)
        vOx, vOy = sRng.uniform(0, 1000), sRng.uniform(0, 1000)
        vX0, vY0 = int(vOx / vSx), int(vOy / vSy)
        vGw = int((self.vWidth - 1 + vOx) / vSx) - vX0 + 2
        vGh = int((self.vHeight - 1 + vOy) / vSy) - vY0 + 2
        arLattice = [[sRng.random() for _ in range(vGw)] for _ in range(vGh)]
        arXi, arXt = [], []
        for vX in range(self.vWidth):
            vF = (vX + vOx) / vSx
            vK = int(vF)
            arXi.append(vK - vX0)
            arXt.append(fnSmooth(vF - vK))
        arRows = [[arRow[k] + (arRow[k + 1] - arRow[k]) * t for k, t in zip(arXi, arXt)] for arRow in arLattice]
        arOut = []
        for vY in range(self.vHeight):
            vF = (vY + vOy) / vSy
            vK = int(vF)
            vT = fnSmooth(vF - vK)
            arA, arB = arRows[vK - vY0], arRows[vK - vY0 + 1]
            arOut.extend([p + (q - p) * vT for p, q in zip(arA, arB)])
        return arOut

    def fnUniformize(self, arValues):
        """Rank-normalise to a uniform [0, 1] distribution so thresholds read as coverage fractions."""
        arOrder = sorted(range(self.vTiles), key=arValues.__getitem__)
        arOut = array("f", bytes(4 * self.vTiles))
        vStep = 1.0 / (self.vTiles - 1)
        for vRank, i in enumerate(arOrder):
            arOut[i] = vRank * vStep
        return arOut

    def fnFbm(self, vSeed, vScale, vOctaves=3, vStretchY=1.0):
        arTotal = None
        vAmp = 1.0
        for vO in range(vOctaves):
            vS = max(vScale / (2 ** vO), 2.0)
            arLayer = self.fnValueNoise(vSeed * 1009 + vO * 7919, vS, vS * vStretchY)
            arTotal = [v * vAmp for v in arLayer] if arTotal is None else [t + v * vAmp for t, v in zip(arTotal, arLayer)]
            vAmp *= 0.5
        return self.fnUniformize(arTotal)

    # -- reachability ----------------------------------------------------------------------------

    def fnBfs(self, vStart, fnPassable):
        """4-way step distance from `vStart` to every tile that `fnPassable` accepts (-1 = unreachable)."""
        arDist = array("i", [-1]) * self.vTiles
        arDist[vStart] = 0
        sQueue = deque([vStart])
        while sQueue:
            i = sQueue.popleft()
            vNext = arDist[i] + 1
            for j in self.fnNeighbours(i):
                if arDist[j] < 0 and fnPassable(j):
                    arDist[j] = vNext
                    sQueue.append(j)
        return arDist

    def fnCheapestPath(self, vSrc, vDst, fnStepCost):
        """Tiles of the cheapest 4-way path from vSrc to vDst; `fnStepCost(i)` is None where a step is
        impossible. Empty list if vDst cannot be reached."""
        dtBest = {vSrc: 0}
        dtPrev = {}
        arHeap = [(0, vSrc)]
        vTx, vTy = vDst % self.vWidth, vDst // self.vWidth
        while arHeap:
            vCost, i = heapq.heappop(arHeap)
            if i == vDst:
                break
            if vCost > dtBest.get(i, 1 << 60):
                continue
            for j in self.fnNeighbours(i):
                vStep = fnStepCost(j)
                if vStep is None:
                    continue
                vNew = vCost + vStep
                if vNew < dtBest.get(j, 1 << 60):
                    dtBest[j] = vNew
                    dtPrev[j] = i
                    vH = abs(j % self.vWidth - vTx) + abs(j // self.vWidth - vTy)
                    heapq.heappush(arHeap, (vNew + vH, j))
        if vDst not in dtBest:
            return []
        arPath = [vDst]
        while arPath[-1] in dtPrev:
            arPath.append(dtPrev[arPath[-1]])
        return arPath[::-1]

    # -- boats ------------------------------------------------------------------------------------

    def fnNavalCosts(self, arFloor, arWall):
        """Cost of entering each tile for wave boats, as Pathfinder.costNaval @ v159.7 prices it: 7000 for a
        dry or walled tile (the flow field crosses it, a boat never does), otherwise 1, +14 next to dry
        ground or a wall (4-way), +1 on a shallow liquid and +35 on lava (a floor that damages)."""
        arLiquid = bytearray(1 if f in sys_config.carLiquidFloors else 0 for f in arFloor)
        arSolid = bytearray(1 if w is not None and w not in sys_config.carNonSolidBlocks else 0 for w in arWall)
        arCost = array("i", [0]) * self.vTiles
        for i in range(self.vTiles):
            if not arLiquid[i] or arSolid[i]:
                arCost[i] = cNavalDryCost
                continue
            vCost = 1
            if any(not arLiquid[j] or arSolid[j] for j in self.fnNeighbours(i)):
                vCost += 14
            if arFloor[i] not in sys_config.carDeepFloors:
                vCost += 1
            if arFloor[i] in sys_config.carLavaFloors:
                vCost += 35
            arCost[i] = vCost
        return arCost

    def fnFlowField(self, vTarget, arCost):
        """Pathfinder flow field: cheapest total cost from every tile to `vTarget`, where stepping onto
        tile j costs arCost[j] (4-way, like Pathfinder.updateFrontier)."""
        arField = array("i", [-1]) * self.vTiles
        arField[vTarget] = 0
        arHeap = [(0, vTarget)]
        while arHeap:
            vCost, i = heapq.heappop(arHeap)
            if vCost > arField[i]:
                continue
            for j in self.fnNeighbours(i):
                vNew = vCost + arCost[j]
                if arField[j] < 0 or vNew < arField[j]:
                    arField[j] = vNew
                    heapq.heappush(arHeap, (vNew, j))
        return arField

    def fnNavalStop(self, vStart, arField, arCost):
        """Where a boat from `vStart` comes to rest: it keeps moving to the lowest-valued neighbour it can
        sail onto (Flowfield.passable refuses naval costs of 6000+) while that is lower than its own tile.
        Returns the tiles it passes, start and resting tile included."""
        arPath = [vStart]
        i = vStart
        while True:
            arNext = [j for j in self.fnNeighbours(i) if arCost[j] < cNavalDryCost and arField[j] < arField[i]]
            if not arNext:
                return arPath
            i = min(arNext, key=arField.__getitem__)
            arPath.append(i)

    # -- liquid barriers -------------------------------------------------------------------------

    def fnAllDeep(self, arFloor, carDeepFloors):
        """Pathfinder.packTile's allDeep flag per tile: the tile and every neighbour on the map (8-way)
        have a deep floor. Ground units cannot path over allDeep tiles; other deep tiles only cost more."""
        vW, vH = self.vWidth, self.vHeight
        arDeep = bytearray(1 if f in carDeepFloors else 0 for f in arFloor)
        arOut = bytearray(self.vTiles)
        for i in range(self.vTiles):
            if not arDeep[i]:
                continue
            vX, vY = i % vW, i // vW
            vAll = 1
            for vDy in (-1, 0, 1):
                vNy = vY + vDy
                if vNy < 0 or vNy >= vH:
                    continue
                vRow = vNy * vW
                for vDx in (-1, 0, 1):
                    vNx = vX + vDx
                    if 0 <= vNx < vW and not arDeep[vRow + vNx]:
                        vAll = 0
                        break
                if not vAll:
                    break
            arOut[i] = vAll
        return arOut

    def vsSealDeepWalls(self, arFloor, arWall, carDeepFloors, carNonSolidBlocks):
        """Gives every solid wall that touches a deep liquid (8-way) that liquid as its floor.

        Pathfinder.packTile decides allDeep from floors alone, so a deep tile next to a wall standing on dry
        floor stays passable for ground units (at a high cost). With the liquid carried under the wall,
        a river or lava band through a wall line is closed to ground units along its whole width, while
        boats still sail through it. The floor under a solid wall is never seen, mined or built on."""
        vW, vH = self.vWidth, self.vHeight
        # only the liquid that is really there spreads; floors set below must not spread further
        arLiquid = [i for i in range(self.vTiles) if arFloor[i] in carDeepFloors]
        for i in arLiquid:
            vLiquid = arFloor[i]
            vX, vY = i % vW, i // vW
            for vDy in (-1, 0, 1):
                for vDx in (-1, 0, 1):
                    vNx, vNy = vX + vDx, vY + vDy
                    if 0 <= vNx < vW and 0 <= vNy < vH:
                        j = vNy * vW + vNx
                        vWallName = arWall[j]
                        if (vWallName is not None and vWallName not in carNonSolidBlocks
                                and arFloor[j] not in carDeepFloors):
                            arFloor[j] = vLiquid
