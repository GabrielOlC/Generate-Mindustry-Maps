"""Common configuration layer shared by every map type.

A layout generator only paints terrain. Everything else a map carries is configured here, or in the
shared system this file points to: the game and mod targets, which floors count as liquid or deep, the
lava data patches, the match and difficulty rules, the floor conventions the ore filters rely on and the
preview palette. The ore filters live in ores.py and the spawn groups in waves.py; both read their
shared values from here. cm_pipeline.py combines a layout with this configuration.
"""

import json
import os

import ores

# ----------------------------------------------------------------------------------------------
# Game and mod targets
# ----------------------------------------------------------------------------------------------

cGameLabel = "Mindustry v8 build 159.7 (save version 13)"
cGameBuild = "159"
cModLabel = "Exogenesis Old (exogenesisold 1.9.1)"
cMapAuthor = "DecONagi"
cDefaultOut = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maps")

# Exogenesis Old terrain. Mod content is registered as "<mod name>-<file name>", so these are written
# to the map with the prefix (ContentLoader.getByName does no prefixing of its own).
carModBlocks = {"pyromagma", "siratla-stone", "siratla-stone-wall", "siratla-crystal", "glowingvein",
                "siratla-stone-boulder", "ore-dytrix", "ore-siradamite", "ore-stellar-steel", "ore-urbium"}
cModPrefix = "exogenesisold-"


def fnFileBlockName(vName):
    return cModPrefix + vName if vName in carModBlocks else vName


# ----------------------------------------------------------------------------------------------
# Floors and blocks as the game treats them
# ----------------------------------------------------------------------------------------------

# Floor.isLiquid (boats float, ores never spawn) and Floor.isDeep (drownTime > 0) @ v159.7.
carLiquidFloors = {"deep-water", "shallow-water", "sand-water", "darksand-water", "tar", "pooled-cryofluid",
                   "molten-slag", "pyromagma"}
carDeepFloors = {"deep-water", "tar", "pooled-cryofluid", "molten-slag"}
# Boulders and spore clusters: drawn on the wall layer, but units walk through them.
carNonSolidBlocks = {"boulder", "snow-boulder", "sand-boulder", "dacite-boulder", "basalt-boulder",
                     "shale-boulder", "spore-cluster", "siratla-stone-boulder"}

# Lava: floors drawn as lava, and Attribute.heat per floor (Blocks.java @ v159.7; Exogenesis Old 1.9.1
# gives none of its floors any heat). Thermal generators need heat > 0 under their 2x2.
carLavaFloors = {"molten-slag", "pyromagma"}
cdtFloorHeat = {"molten-slag": 0.85, "magmarock": 0.75, "hotrock": 0.5}

# Map data patches (embedded in the save, applied by the game only while the map is loaded).
# 1. The thermal generator is already `floating`, but Build.validPlace also wants it to touch non-deep
#    ground (contactsShallows), so it only fit along the banks of the molten slag. `placeableLiquid`
#    lifts that rule. Only heat floors pass ThermalGenerator.canPlaceOn, so this opens up lava and
#    nothing else.
# 2. Exogenesis' pyromagma is drawn as lava but has no heat at all, so no thermal generator could stand
#    on it. It gets the heat of molten slag. This is a separate asset with a dotted path: without the
#    mod the path does not resolve, and the game only logs a warning for it.
carDataPatches = (
    ("thermal-generators-on-lava.json", json.dumps({
        "name": "Thermal generators on lava",
        "block": {"thermal-generator": {"placeableLiquid": True}},
    })),
    ("pyromagma-heat.json", json.dumps({
        "name": "Pyromagma gives heat",
        "block.%s.attributes.heat" % fnFileBlockName("pyromagma"): cdtFloorHeat["molten-slag"],
    })),
)

# The static wall that matches each floor (vanilla look; mod walls only where the floor is a mod floor).
cdtNaturalWall = {
    "stone": "stone-wall", "crater-stone": "stone-wall", "char": "dune-wall", "basalt": "dune-wall",
    "hotrock": "dune-wall", "magmarock": "dune-wall", "sand-floor": "sand-wall", "darksand": "dune-wall",
    "salt": "salt-wall", "shale": "shale-wall", "dirt": "dirt-wall", "mud": "dirt-wall", "grass": "dirt-wall",
    "moss": "stone-wall", "spore-moss": "spore-wall", "dacite": "dacite-wall", "snow": "snow-wall",
    "ice-snow": "snow-wall", "ice": "ice-wall", "siratla-stone": "siratla-stone-wall",
    "metal-floor-damaged": "dark-metal",
}

# Floors kept free of ore by the last ore filters (ores.CLEAR_FLOORS): every layout paints its outpost
# pads and its core plaza with exactly these.
cPadFloor = "core-zone"
cPadRingFloor = "dark-panel-3"
cPlazaFloor = "metal-floor"
cPlazaBorderFloor = "dark-panel-4"
assert {cPadFloor, cPadRingFloor, cPlazaFloor, cPlazaBorderFloor} == set(ores.CLEAR_FLOORS)

cCoreBlock = "core-foundation"
cCoreSize = 4
cSpawnOverlay = "spawn"

# Special floors counted per region in the report.
cdtResourceFloors = {
    "water": {"deep-water", "shallow-water", "sand-water", "darksand-water"},
    "cryofluid": {"pooled-cryofluid"}, "oil (tar)": {"tar"}, "oil-rich ground (shale)": {"shale"},
    "slag (lava)": {"molten-slag"}, "pyroplasma (pyromagma)": {"pyromagma"},
    "cold plasma (glowing vein)": {"glowingvein"},
    "heat (hotrock/magmarock)": {"hotrock", "magmarock"}, "spore moss": {"spore-moss"},
    "sand floor (sand/darksand)": {"sand-floor", "darksand"},
}

# ----------------------------------------------------------------------------------------------
# Difficulty and match rules (Survival / PvE). waves.py adds the spawn groups of each map.
# ----------------------------------------------------------------------------------------------

cdtMatchRules = {
    "waves": True,
    "waveTimer": True,
    "waveSending": True,
    "waitEnemies": False,
    "waveSpacing": 9000.0,          # 150 s between waves
    "initialWaveSpacing": 25200.0,  # 7 min to set up before wave 1
    "winWave": 0,                   # endless
    "attackMode": False,
    "pvp": False,
    "hideSpawns": False,
    "unitCap": 24,                  # + core bonus (foundation +16)
    "unitCapVariable": True,
    "dropZoneRadius": 300.0,
    # Planet "<Any>" of the rules dialog (CustomRulesDialog @ v159.7): Planets.sun enables mixed tech, so
    # Serpulo, Erekir and mod blocks can all be built (UnlockableContent.isOnPlanet). Env and attributes
    # keep their defaults, as that button sets them.
    "planet": "sun",
    "loadout": [
        {"item": "copper", "amount": 700},
        {"item": "lead", "amount": 300},
    ],
}

# Difficulty levels, easiest to hardest, with the multipliers of Mindustry's own Difficulty enum @ v159.7
# (game/Difficulty.java). The game applies them only in the campaign (CampaignRules.apply, WaveSpawner,
# Logic), so each map carries its level itself: the enemy health multiplier goes into the wave team's
# rules (Rules.unitHealth divides the damage those units take, shields included), the wave timer and the
# delay before wave 1 are scaled, and the enemy spawn multiplier is baked into the spawn groups
# (waves.fnApplyDifficulty). "normal" is the waves as designed and keeps the plain map name; the last
# (hardest) level is the default when none is chosen.
cdtDifficulties = {
    "casual": {"label": "Casual", "health": 0.5, "spawn": 0.5, "waveTime": 2.0},
    "easy": {"label": "Easy", "health": 1.0, "spawn": 0.75, "waveTime": 1.5},
    "normal": {"label": "Normal", "health": 1.0, "spawn": 1.0, "waveTime": 1.0},
    "hard": {"label": "Hard", "health": 1.25, "spawn": 1.5, "waveTime": 0.8},
    "eradication": {"label": "Eradication", "health": 1.5, "spawn": 2.0, "waveTime": 0.6},
}
cBaseDifficulty = "normal"
cDefaultDifficulty = list(cdtDifficulties)[-1]
cWaveTeam = 2              # Team.crux, the default Rules.waveTeam

# ----------------------------------------------------------------------------------------------
# PvP maps (a layout result with sMatch "pvp"). Game rules as of v159.7.
# ----------------------------------------------------------------------------------------------

# Player slots: the editor's five base teams (Team.baseTeams without derelict). NetServer's team assigner
# puts every joining player on the team that has a core and the fewest players.
cdtPvpTeams = {"sharded": 1, "crux": 2, "malis": 3, "green": 4, "blue": 5}
cdtTeamColors = {1: (255, 211, 127), 2: (242, 85, 85), 3: (162, 124, 229), 4: (84, 214, 125), 5: (108, 135, 253),
                 6: (224, 84, 56)}      # Team.java colours

# Waves on a PvP map come from a sixth team, neoplastic (6): red like crux and free of the unit cap.
# Team.isAI() is false for every team in PvP, so wave units get CommandAI and would stand at the spawn.
# The RTS AI (team rule rtsAi, which Logic runs in PvP too) sends every idle squad at a target picked
# from all players' cores, drills, generators, factories and batteries (RtsAI.findTarget: 15 shuffled
# candidates, easiest kill first). A minimum weight of 0 makes every squad attack as soon as it spawns.
cPvpWaveTeam = 6
cdtPvpRules = {
    "pvp": True,
    "attackMode": True,        # Logic.checkGameState: the last team with a core wins only in attack mode
    "waveSending": False,      # no player can call the next wave onto everyone else
    "waveTeam": cPvpWaveTeam,
    # Flyers too rise from the spawn tiles (in the middle). By default WaveSpawner.eachFlyerSpawn puts
    # them on the map edge in the spawn's direction, which here would be behind the bases.
    "airUseSpawns": True,
}
cdtPvpWaveTeamRules = {"rtsAi": True, "rtsMinSquad": 1, "rtsMinWeight": 0.0}

# Defender bots. A world processor (team 6, privileged, indestructible) waits for the join window, then
# turns every player team that still has a core but no player into a fortress that never attacks:
# setrule raises its block/unit health and damage (Rules.blockHealth and unitHealth divide the damage
# taken, so the core gets tougher at once), setblock builds the turrets and a ring of walls around its
# core, setprop loads the turrets' ammo (ItemTurret.handleStack) and spawn adds guards. Units of a
# non-AI team get CommandAI, so the guards hold position and shoot what comes in range. Every refresh
# the processor reloads ammo and replaces lost guards; when a player joins a bot team later, that
# team's multipliers go back to 1 and the processor stops looking after it. Multipliers are given at
# Normal and scale with the difficulty's enemy health factor. Vanilla blocks and units only.
cdtBotRules = {
    "joinWindow": 180,         # seconds after the map starts before empty slots become bots
    "refresh": 15,             # seconds between ammo reloads, guard top-ups and late-joiner checks
    "multipliers": {"blockHealth": 4.0, "blockDamage": 2.0, "unitHealth": 3.0, "unitDamage": 2.0},
    # block, ammo, (dx, dy) of the block's centre tile from the core's centre tile. Placed like the game
    # places blocks: an odd size n covers dx-(n-1)/2..dx+(n-1)/2, an even one dx-(n/2-1)..dx+n/2, so the
    # pattern is symmetric about the core's middle (dx + 0.5) with -dx for even and 1-dx for odd sizes.
    "turrets": (
        ("spectre", "thorium", (-13, -13)), ("spectre", "thorium", (13, -13)),
        ("spectre", "thorium", (-13, 13)), ("spectre", "thorium", (13, 13)),
        ("ripple", "plastanium", (-14, -5)), ("ripple", "plastanium", (15, 6)),
        ("ripple", "plastanium", (6, -14)), ("ripple", "plastanium", (-5, 15)),
        ("cyclone", "surge-alloy", (-14, 6)), ("cyclone", "surge-alloy", (15, -5)),
        ("cyclone", "surge-alloy", (-5, -14)), ("cyclone", "surge-alloy", (6, 15)),
    ),
    "ammo": 1000,              # setprop target; the turret takes what fits (ItemTurret.acceptStack)
    "wall": "thorium-wall-large",
    "wallRing": 20,            # the 2x2 walls cover the square band 19..21 tiles from the core's centre
    "guards": (("fortress", 4), ("scepter", 1)),   # unit, how many the processor keeps alive
    "guardSpot": (0, -6),     # where they spawn, from the core's centre tile (inside the wall ring)
    "ipt": 100,                # instructions per tick of the world processor (its block allows 1000)
}
cBotKeep = 23                  # Chebyshev half-size of the clear square every PvP core needs for a fortress
cdtBlockSizes = {"core-foundation": 4, "spectre": 4, "ripple": 3, "cyclone": 3, "thorium-wall-large": 2,
                 "world-processor": 1}
cWorldProcessor = "world-processor"


def fnMapName(vName, vDifficulty):
    """In-game name and file name of a map at a difficulty: the plain name at normal, "Name (Level)" otherwise."""
    if vDifficulty == cBaseDifficulty:
        return vName
    return "%s (%s)" % (vName, cdtDifficulties[vDifficulty]["label"])


def fnDifficultyNote(vDifficulty):
    """One line for the map description, in the game's own terms (Difficulty.info)."""
    dtLevel = cdtDifficulties[vDifficulty]
    arParts = []
    for vKey, vText in (("health", "enemy health"), ("spawn", "enemy units"), ("waveTime", "time between waves")):
        vPercent = int(round(dtLevel[vKey] * 100 - 100))
        if vPercent:
            arParts.append("%s %+d%%" % (vText, vPercent))
    return "Difficulty: %s (%s)." % (dtLevel["label"], ", ".join(arParts) or "no modifiers")

# ----------------------------------------------------------------------------------------------
# Preview palette (map colours of floors, walls and ores)
# ----------------------------------------------------------------------------------------------

cdtPreviewColors = {
    "stone": (92, 92, 98), "crater-stone": (80, 80, 88), "char": (58, 52, 50), "basalt": (52, 50, 56),
    "hotrock": (128, 72, 52), "magmarock": (196, 96, 44), "molten-slag": (255, 132, 36),
    "pyromagma": (255, 70, 20), "sand-floor": (222, 196, 138), "darksand": (150, 118, 88),
    "salt": (232, 226, 214), "shale": (132, 98, 78), "dirt": (142, 110, 80), "mud": (100, 84, 70),
    "dacite": (164, 152, 142), "grass": (88, 140, 70), "moss": (70, 112, 62), "spore-moss": (112, 82, 142),
    "snow": (236, 240, 246), "ice": (176, 208, 240), "ice-snow": (208, 224, 240),
    "siratla-stone": (150, 172, 196), "siratla-crystal": (120, 205, 245), "glowingvein": (160, 230, 255),
    "deep-water": (38, 68, 140), "shallow-water": (72, 112, 182), "sand-water": (122, 150, 170),
    "darksand-water": (90, 110, 132), "tar": (28, 28, 34), "pooled-cryofluid": (96, 200, 232),
    "core-zone": (230, 186, 60), "metal-floor": (112, 112, 122), "metal-floor-damaged": (96, 96, 102),
    "dark-panel-1": (66, 66, 72), "dark-panel-2": (62, 62, 70), "dark-panel-3": (72, 72, 80),
    "dark-panel-4": (60, 60, 66), "dark-panel-5": (64, 64, 70), "dark-panel-6": (58, 58, 64),
    "stone-wall": (58, 58, 64), "sand-wall": (176, 146, 98), "salt-wall": (196, 190, 180),
    "shale-wall": (98, 74, 60), "dirt-wall": (98, 74, 54), "dacite-wall": (118, 108, 100),
    "snow-wall": (188, 198, 210), "ice-wall": (136, 166, 200), "dune-wall": (64, 48, 42),
    "spore-wall": (80, 60, 100), "dark-metal": (40, 40, 48), "siratla-stone-wall": (104, 126, 150),
    "pine": (36, 88, 40), "snow-pine": (58, 106, 82), "spore-pine": (92, 58, 122), "shrubs": (58, 100, 50),
    "white-tree-dead": (112, 100, 90),
    "ore-copper": (218, 142, 92), "ore-lead": (142, 132, 176), "ore-scrap": (136, 134, 124),
    "ore-coal": (30, 30, 30), "ore-titanium": (140, 162, 232), "ore-thorium": (240, 150, 200),
    "ore-beryllium": (58, 143, 100), "ore-tungsten": (118, 138, 154), "ore-dytrix": (115, 255, 174),
    "ore-siradamite": (169, 216, 255), "ore-stellar-steel": (102, 177, 255), "ore-urbium": (64, 64, 84),
}
