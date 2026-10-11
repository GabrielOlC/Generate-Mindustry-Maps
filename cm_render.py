"""Preview and route images for any map type (standard-library PNG writer).

The preview shows the terrain with one simulated ore roll, spawns with their drop zones, outposts,
choke points and the core. The routes image shows every spawn's near-shortest ground corridor in the
spawn's colour; on maps with naval spawns, the water those spawns' boats sail along is tinted the same way.
On a PvP map every player core is drawn in its team's colour, with the square a defender-bot fortress
takes in the preview, and the routes image adds the naval links between the bases.
"""

import struct
import zlib

import cm_terrain
import sys_config

cCoreColor = (255, 150, 0)
cNavalSpawnColor = (40, 120, 255)


def fnWritePng(vPath, vWidth, vHeight, arPixels):
    arRaw = bytearray()
    for vY in range(vHeight):
        arRaw.append(0)
        arRaw += arPixels[vY * vWidth * 3:(vY + 1) * vWidth * 3]

    def fnChunk(vTag, arData):
        return struct.pack(">I", len(arData)) + vTag + arData + struct.pack(">I", zlib.crc32(vTag + arData) & 0xFFFFFFFF)

    arPng = b"\x89PNG\r\n\x1a\n" + fnChunk(b"IHDR", struct.pack(">IIBBBBB", vWidth, vHeight, 8, 2, 0, 0, 0))
    arPng += fnChunk(b"IDAT", zlib.compress(bytes(arRaw), 9)) + fnChunk(b"IEND", b"")
    with open(vPath, "wb") as sFile:
        sFile.write(arPng)


def _fnCoreCentres(sResult, arColor):
    """[(x, y, colour)] of the visual centre of every core block (an even-sized block is centred between
    tiles); PvE cores get `arColor`, PvP cores their team's colour."""
    vOffset = 0.5 if sys_config.cCoreSize % 2 == 0 else 0.0
    vPvp = sResult.sMatch == "pvp"
    return [(d["x"] + vOffset, d["y"] + vOffset, sys_config.cdtTeamColors[d["team"]] if vPvp else arColor)
            for d in sResult.fnCores()]


def _vsSquare(sGrid, arPixels, vCx, vCy, vHalf, arColor):
    """Outline of the square of Chebyshev half-size `vHalf` around (vCx, vCy)."""
    vW, vH = sGrid.vWidth, sGrid.vHeight
    for vX in range(int(vCx - vHalf), int(vCx + vHalf) + 1):
        for vY in range(int(vCy - vHalf), int(vCy + vHalf) + 1):
            if max(abs(vX - vCx), abs(vY - vCy)) >= vHalf - 1 and 0 <= vX < vW and 0 <= vY < vH:
                vK = ((vH - 1 - vY) * vW + vX) * 3
                arPixels[vK:vK + 3] = bytes(arColor)


def _vsDot(sGrid, arPixels, vCx, vCy, vRad, arColor, vRing=False):
    vW, vH = sGrid.vWidth, sGrid.vHeight
    for i, vD in sGrid.fnDisc(vCx, vCy, vRad):
        if vRing and vD < vRad - 1.5:
            continue
        vK = ((vH - 1 - i // vW) * vW + i % vW) * 3
        arPixels[vK:vK + 3] = bytes(arColor)


def vsRenderPreview(sResult, arFloor, arOverlay, vPath):
    """Top-down view with one simulated ore roll (every game rolls its own)."""
    vW, vH = sResult.vWidth, sResult.vHeight
    sGrid = cm_terrain.clGrid(vW, vH)
    dtColors = sys_config.cdtPreviewColors
    arPixels = bytearray(vW * vH * 3)
    for i in range(vW * vH):
        vX, vY = i % vW, i // vW
        vWall, vOre, vFloor = sResult.arWall[i], arOverlay[i], arFloor[i]
        if vWall is not None and vWall not in sys_config.carNonSolidBlocks:
            arColor = dtColors.get(vWall, (60, 60, 60))
        elif vOre is not None and vOre != sys_config.cSpawnOverlay:
            arColor = dtColors.get(vOre, (255, 0, 255))
        else:
            arColor = dtColors.get(vFloor, (255, 0, 255))
            if vWall is not None:
                arColor = tuple(int(v * 0.8) for v in arColor)
        vK = ((vH - 1 - vY) * vW + vX) * 3
        arPixels[vK:vK + 3] = bytes(arColor)
    vDropZone = sys_config.cdtMatchRules["dropZoneRadius"] / 8.0
    for vKey, (vSx, vSy) in sResult.dtSpawns.items():
        _vsDot(sGrid, arPixels, vSx, vSy, vDropZone, (255, 60, 60), vRing=True)
        _vsDot(sGrid, arPixels, vSx, vSy, 7, (230, 30, 30))
        if vKey in sResult.arNavalSpawnKeys:
            _vsDot(sGrid, arPixels, vSx, vSy, 4, cNavalSpawnColor)
    for dtPad in sResult.arPads:
        _vsDot(sGrid, arPixels, dtPad["x"], dtPad["y"], 6, (0, 230, 230), vRing=True)
    for vMx, vMy in sResult.dtMarkers.values():
        _vsDot(sGrid, arPixels, vMx, vMy, 3.5, (255, 230, 0))
    for vCx, vCy, arColor in _fnCoreCentres(sResult, cCoreColor):
        if sResult.sMatch == "pvp":
            _vsSquare(sGrid, arPixels, vCx, vCy, sys_config.cdtBotRules["wallRing"] + 1.5, arColor)
            _vsDot(sGrid, arPixels, vCx, vCy, 7, (0, 0, 0))
        _vsDot(sGrid, arPixels, vCx, vCy, 5, arColor)
    fnWritePng(vPath, vW, vH, arPixels)


def vsRenderRoutes(sResult, dtCorridors, dtNavalCorridors, vPath):
    """Grey terrain with each spawn's near-shortest ground corridor (and naval corridor) in its colour."""
    vW, vH = sResult.vWidth, sResult.vHeight
    sGrid = cm_terrain.clGrid(vW, vH)
    arLayers = [(sResult.dtRouteColors[k], arTiles) for k, (_, _, arTiles) in dtCorridors.items()]
    arLayers += [(sResult.dtRouteColors.get(k, cNavalSpawnColor), arTiles)
                 for k, (_, _, arTiles) in dtNavalCorridors.items()]
    arPixels = bytearray(vW * vH * 3)
    for i in range(vW * vH):
        vX, vY = i % vW, i // vW
        vWall, vFloor = sResult.arWall[i], sResult.arFloor[i]
        if vWall is not None and vWall not in sys_config.carNonSolidBlocks:
            arColor = (38, 38, 42)
        elif vFloor in sys_config.carDeepFloors:
            arColor = (40, 70, 130) if vFloor != "molten-slag" else (150, 60, 20)
        elif vFloor in sys_config.carLiquidFloors:
            arColor = (150, 175, 210)
        else:
            arColor = (196, 196, 200)
        arHit = [arRoute for arRoute, arTiles in arLayers if arTiles[i]]
        if arHit:
            vR = sum(h[0] for h in arHit) // len(arHit)
            vG = sum(h[1] for h in arHit) // len(arHit)
            vB = sum(h[2] for h in arHit) // len(arHit)
            arColor = ((arColor[0] + 2 * vR) // 3, (arColor[1] + 2 * vG) // 3, (arColor[2] + 2 * vB) // 3)
        vK = ((vH - 1 - vY) * vW + vX) * 3
        arPixels[vK:vK + 3] = bytes(arColor)
    for vMx, vMy in sResult.dtMarkers.values():
        _vsDot(sGrid, arPixels, vMx, vMy, 5, (0, 0, 0))
        _vsDot(sGrid, arPixels, vMx, vMy, 3, (255, 255, 255))
    for vKey, (vSx, vSy) in sResult.dtSpawns.items():
        _vsDot(sGrid, arPixels, vSx, vSy, 9, (0, 0, 0))
        _vsDot(sGrid, arPixels, vSx, vSy, 7, sResult.dtRouteColors[vKey])
        if vKey in sResult.arNavalSpawnKeys:
            _vsDot(sGrid, arPixels, vSx, vSy, 3, cNavalSpawnColor)
    for dtPad in sResult.arPads:
        _vsDot(sGrid, arPixels, dtPad["x"], dtPad["y"], 4, (0, 230, 230))
    for vCx, vCy, arColor in _fnCoreCentres(sResult, (255, 140, 0)):
        _vsDot(sGrid, arPixels, vCx, vCy, 7, (0, 0, 0))
        _vsDot(sGrid, arPixels, vCx, vCy, 5, arColor)
    fnWritePng(vPath, vW, vH, arPixels)
