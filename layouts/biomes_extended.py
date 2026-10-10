"""Biomes Extended Remastered: the original layout, run unchanged from generate_map.py.

The terrain comes from generate_map.MapBuilder, step for step as generate_map.main runs it (only the ore
preview moved to the shared pipeline), so both entry points write the same map. The map has no naval
spawns, so its boats are swapped for land units, and it keeps its own barrier tests in check_map.py.
"""

import time

import check_map
import cm_layout
import generate_map


class clBiomesExtended(cm_layout.clLayout):
    cKey = "biomes-extended"
    cName = generate_map.MAP_NAME
    cSummary = "Five biomes around the core, sealed choke points; no naval routes (boats become land units)"
    cDefaultSeed = generate_map.DEFAULT_SEED
    cOrder = 10

    def fnBuild(self, vSeed):
        sBuilder = generate_map.MapBuilder(vSeed)
        arSteps = (
            ("noise fields", sBuilder.build_noise), ("polar grid", sBuilder.build_polar),
            ("biomes", sBuilder.build_biomes), ("floors", sBuilder.paint_floors),
            ("volcano", sBuilder.volcano_features), ("forest", sBuilder.forest_features),
            ("frozen", sBuilder.frozen_features), ("semi-arid", sBuilder.semiarid_features),
            ("desert", sBuilder.desert_features), ("keep-clear zones", sBuilder.keep_clear),
            ("natural walls", sBuilder.natural_walls), ("structural walls", sBuilder.structural_walls),
            ("outpost pads", sBuilder.place_pads), ("spawns and core plaza", sBuilder.clear_spawns_and_core),
            ("decorations", sBuilder.decorate), ("connectivity", sBuilder.ensure_connectivity),
        )
        for vLabel, vsStep in arSteps:
            vTs = time.time()
            vsStep()
            print("  %-22s %6.1fs" % (vLabel, time.time() - vTs))
        arRegion = [generate_map.BASIN if vBiome == generate_map.BASIN else vSector
                    for vBiome, vSector in zip(sBuilder.BI, sBuilder.CB)]
        return cm_layout.clLayoutResult(
            vName=generate_map.MAP_NAME, vDescription=generate_map.DESCRIPTION,
            vWidth=generate_map.W, vHeight=generate_map.H,
            arFloor=sBuilder.floor, arOverlay=sBuilder.ore, arWall=sBuilder.wall,
            arCore=(generate_map.CX, generate_map.CY),
            dtSpawns=generate_map.SPAWNS, dtSpawnLabels=generate_map.SPAWN_LABELS,
            dtRouteColors=generate_map.ROUTE_COLORS,
            arRegion=arRegion, arRegionNames=generate_map.BIOME_NAMES,
            dtMarkers=sBuilder.markers, arPads=sBuilder.pads, arNotes=sBuilder.notes)

    def fnCheck(self, vMapPath, sResult):
        return check_map.main(vMapPath) == 0
