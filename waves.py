"""Wave design shared by every map type.

The spawn groups copy the owner's BIOME FFA wave list group for group: same units, waves, growth
and shields. Each map gets them through `fnExpandGroups`: on a map with naval spawns (spawn tiles on
water) every naval group comes up each of those spawns; on a map without them its naval units are
swapped for land or air units of the same tier (`cdtNavalSwap`). Groups are written in the JSON format
that mindustry.game.SpawnGroup reads (v8 build 159.7):

    type, begin, end, spacing, max, scaling, shields, shieldScaling, amount, effect, spawn

`begin`/`end` are 0-based wave indexes in the file; this module uses human wave numbers
(wave 1 = first wave) and converts them. `scaling` counts *appearances* of the group, not waves:
units per spawn point = min(amount + int(appearances_so_far / scaling), max).
A group without a `spawn` position spawns at every spawn point of the map.
"""

import copy

import sys_config

EXO = "exogenesisold-"
NEVER = 2147483647

# Health values used only for the summary tables (vanilla: UnitTypes.java @ v159.7,
# Exogenesis Old: content/units/*.json @ AureusStratus/ExoGenesis main).
UNIT_HP = {
    "dagger": 150, "mace": 550, "fortress": 900, "scepter": 9000, "reign": 24000,
    "nova": 120, "pulsar": 320, "quasar": 640, "vela": 8200, "corvus": 18000,
    "crawler": 150, "atrax": 600, "spiroct": 1000, "arkyid": 8000, "toxopid": 22000,
    "flare": 70, "horizon": 340, "zenith": 700, "antumbra": 7200, "eclipse": 22000, "quad": 6000,
    "locus": 2100, "precept": 5000, "conquer": 22000, "tecta": 6500,
    # Genesux (cold faction)
    EXO + "b01-orion": 360, EXO + "b01-majoris": 300, EXO + "b02-galileo": 890, EXO + "b02-gacrux": 890,
    EXO + "b03-kuiper": 2600, EXO + "b03-kentaurus": 2000, EXO + "b04-oort": 12000, EXO + "b04-vega": 12950,
    EXO + "b05-sirius": 45000, EXO + "b05-centauri": 38400, EXO + "b06-eros": 79800, EXO + "b06-altair": 82400,
    EXO + "b07-atlas": 190000, EXO + "b07-universalis": 174000, EXO + "sagittarius": 10000000,
    EXO + "drone-B": 700,
    # Solran (molten faction)
    EXO + "sol": 900, EXO + "heat": 950, EXO + "corona": 1300, EXO + "molten": 2400, EXO + "photosphere": 3200,
    EXO + "magma": 5300, EXO + "radiative": 9000, EXO + "lava": 14000, EXO + "core": 50000,
    EXO + "eruption": 50000, EXO + "Fusion": 66000, EXO + "collapse": 250000, EXO + "arcturus": 5300000,
    # Elecian
    EXO + "challenge": 90, EXO + "disrespect": 560, EXO + "dispute": 780, EXO + "strife": 2190,
    EXO + "debate": 3480, EXO + "combat": 8390, EXO + "disagreement": 13800, EXO + "disaccord": 28400,
    EXO + "hostile": 54890, EXO + "assault": 78700, EXO + "contention": 74000, EXO + "bloodshed": 178900,
    EXO + "battle": 154080, EXO + "war": 5000000,
    # Quantra
    EXO + "pteris": 560, EXO + "irises": 790, EXO + "guardian": 980, EXO + "aster": 1000,
    EXO + "crystal-drone-healer": 3000, EXO + "urtica": 7000, EXO + "thymus": 16000,
    # Exogenesis tier 6/7 extensions of the vanilla trees ("Titan" host)
    EXO + "stella": 62500, EXO + "T-nemesis": 46500, EXO + "T-atlas": 78000, EXO + "T-prometheus": 80000,
    EXO + "twilight": 64600, EXO + "anvil": 78600, EXO + "toxicity": 83900, EXO + "virgo": 97000,
    EXO + "hex": 80000, EXO + "xenoct": 210000, EXO + "fornax": 180000, EXO + "nadir": 174000,
    EXO + "colossus": 287000,
    # Exogenesis core units
    EXO + "asgard": 900,
    # naval units (vanilla risso and retusa lines, Exogenesis tier 6/7 boats, the Quantra apex)
    "risso": 280, "minke": 600, "bryde": 910, "cyerce": 870, "navanax": 20000,
    EXO + "orca": 68200, EXO + "balaenoptera": 158200, EXO + "apotheosis": 6000000,
}

BOSS_HEALTH_MULTIPLIER = 1.5  # StatusEffects.boss.healthMultiplier @ v159.7

# Every naval unit of the groups, with its stand-in for maps without naval spawns. A boat spawned on dry
# ground dies at once (UnitComp.update kills units on tiles that are solid to them, and land is solid to
# boats), so there each one takes the place of the land unit of the same tier and role: attack boats
# (risso line) -> dagger line, support boats (retusa line) -> nova line. The lines are the species of
# Waves.generate @ v159.7. Exogenesis Old extends both (omura -> orca -> balaenoptera, reign -> anvil ->
# fornax). apotheosis, the Quantra naval apex, has no line; war is the apex closest in health and armour
# (5.0M HP / 90 vs 6.0M HP / 100), though it flies. A naval unit added to the groups needs an entry here.
cdtNavalSwap = {
    "risso": "dagger", "minke": "mace", "bryde": "fortress",
    "cyerce": "quasar", "navanax": "corvus",
    EXO + "orca": EXO + "anvil", EXO + "balaenoptera": EXO + "fornax",
    EXO + "apotheosis": EXO + "war",
}

# Shields added per wave by the groups the game's wave generator made for BIOME FFA
# (Waves.generate: 20 + 30 x difficulty); its second boss group grows four times as fast.
cShieldGrowth = 22.275732


class Group:
    def __init__(self, unit, first, last=None, every=1, amount=1, grow=None, cap=None,
                 shields=0.0, shield_growth=0.0, effect=None, at=None, note=""):
        self.unit = unit
        self.first = first          # human wave number of the first appearance
        self.last = last            # human wave number of the last appearance (None = endless)
        self.every = every          # spawn every N waves
        self.amount = amount        # units per spawn point at the first appearance
        self.grow = grow            # +1 unit every `grow` appearances (None = fixed amount)
        self.cap = cap              # max units per spawn point (game default 40)
        self.shields = shields
        self.shield_growth = shield_growth  # shield points added per wave after `first`
        self.effect = effect
        self.at = at                # spawn key (None = every spawn point)
        self.note = note

    def to_json(self, spawn_positions):
        g = {"type": self.unit}
        if self.first != 1:
            g["begin"] = self.first - 1
        if self.last is not None:
            g["end"] = self.last - 1
        if self.every != 1:
            g["spacing"] = self.every
        if self.cap is not None and self.cap != 40:
            g["max"] = self.cap
        if self.grow is not None:
            g["scaling"] = float(self.grow)
        if self.shields:
            g["shields"] = float(self.shields)
        if self.shield_growth:
            g["shieldScaling"] = float(self.shield_growth)
        if self.amount != 1:
            g["amount"] = self.amount
        if self.effect:
            g["effect"] = self.effect
        if self.at is not None:
            x, y = spawn_positions[self.at]
            g["spawn"] = pack_point(x, y)
        return g

    def spawned(self, wave):
        """Units per spawn point on a human wave number; mirrors SpawnGroup.getSpawned."""
        w = wave - 1
        begin = self.first - 1
        end = NEVER if self.last is None else self.last - 1
        if w < begin or w > end or (w - begin) % self.every != 0:
            return 0
        cap = 40 if self.cap is None else self.cap
        extra = 0 if self.grow is None else int(((w - begin) // self.every) / self.grow)
        return min(self.amount + extra, cap)

    def shield_at(self, wave):
        return max(self.shields + self.shield_growth * ((wave - 1) - (self.first - 1)), 0.0)


def pack_point(x, y):
    """arc.math.geom.Point2.pack - the packed tile position used by SpawnGroup.spawn."""
    return ((x & 0xFFFF) << 16) | (y & 0xFFFF)


def build_groups():
    """All spawn groups, in BIOME FFA's order. Only the shielded locus has a spawn key."""
    # Wave numbers are human (the file's begin + 1). BIOME FFA's "scaling: Infinity" (never grows) is left
    # out, which the game reads the same way.
    return [
        Group("crawler", 1, 18, grow=3.9540515, cap=13, shield_growth=cShieldGrowth),
        Group("dagger", 3, 50, grow=10),
        Group("nova", 5),
        Group("nova", 6, 24, grow=4.318818, cap=13, shield_growth=cShieldGrowth),
        Group("locus", 10, 70, grow=25),
        # BIOME FFA pins this one to its south-east spawn; east is the nearest direction on both maps
        Group("locus", 10, 70, grow=25, shields=50, at="desert"),
        Group("crawler", 14, amount=3, grow=2.5361075, cap=6, shield_growth=cShieldGrowth),
        Group("minke", 14, grow=43.47826),
        Group("horizon", 15, 60, every=3, grow=50),
        Group("fortress", 16, grow=499.99997),
        Group("fortress", 16, grow=499.99997),
        Group("quasar", 19, grow=50),
        Group("bryde", 20, grow=33.333336),
        Group(EXO + "heat", 20),
        Group(EXO + "drone-B", 21, grow=999.99994),
        Group("nova", 23, 33, every=4, amount=3, grow=2.21728, cap=6, shield_growth=cShieldGrowth),
        Group("risso", 23, grow=50),
        Group("flare", 24, 40, grow=3.9181943, cap=13, shield_growth=cShieldGrowth),
        Group("zenith", 24, 70, every=3, amount=3),
        Group("horizon", 25, 45, amount=3, grow=5.83123, cap=13, shield_growth=cShieldGrowth),
        Group("cyerce", 25, 101),
        Group("precept", 25, grow=5),
        Group("pulsar", 28),
        Group("atrax", 33, 50, amount=3, grow=5.0970526, cap=13, shield_growth=cShieldGrowth),
        Group("atrax", 36, 45, every=4, grow=2.036988, cap=6, shield_growth=cShieldGrowth),
        Group("quasar", 38, 60, amount=2, grow=7.9206233, cap=13,
              shields=155.93013, shield_growth=cShieldGrowth),
        Group("flare", 38, 54, grow=4.8549156, cap=13, shields=155.93013, shield_growth=cShieldGrowth),
        Group("flare", 39, 50, every=2, amount=3, grow=3.4462433, cap=6, shield_growth=cShieldGrowth),
        Group("conquer", 40, 41, effect="boss"),
        Group("tecta", 40, grow=100),
        Group(EXO + "b02-galileo", 40, grow=999.99994),
        Group("pulsar", 41, 62, amount=3, grow=5.7906, cap=13, shields=222.75732, shield_growth=cShieldGrowth),
        Group("conquer", 41),
        Group("horizon", 44, 52, every=3, grow=2.861656, cap=6, shield_growth=cShieldGrowth),
        Group("spiroct", 46, 73, amount=2, grow=13.65217, cap=13, shields=334.136, shield_growth=cShieldGrowth),
        Group("tecta", 46, grow=100),
        Group(EXO + "b01-orion", 50),
        Group(EXO + "b04-oort", 50, 51, effect="boss"),
        Group("crawler", 52, 64, every=2, grow=4.4125433, cap=13,
              shields=467.79037, shield_growth=cShieldGrowth),
        Group("flare", 53, 63, every=4, amount=3, grow=2.5531213, cap=6,
              shields=77.965065, shield_growth=cShieldGrowth),
        Group("scepter", 54, every=33, grow=33, cap=16, shield_growth=cShieldGrowth, effect="boss"),
        Group("horizon", 55, 77, amount=3, grow=6.1190214, cap=13,
              shields=534.61755, shield_growth=cShieldGrowth),
        Group("quasar", 59, 70, every=3, grow=2.551276, cap=6, shields=77.965065, shield_growth=cShieldGrowth),
        Group("quad", 60, grow=100),
        Group("pulsar", 61, 68, every=3, grow=3.0251129, cap=6, shields=111.37866, shield_growth=cShieldGrowth),
        Group("arkyid", 61, 89, grow=10.201302, cap=13, shields=668.272, shield_growth=cShieldGrowth),
        Group("quasar", 63, 85, amount=2, grow=14.627483, cap=13,
              shields=712.8234, shield_growth=cShieldGrowth),
        Group("crawler", 63, 74, every=2, amount=3, grow=2.477328, cap=6,
              shields=233.89519, shield_growth=cShieldGrowth),
        Group("atrax", 65, 84, amount=3, grow=5.1379867, cap=13, shields=757.3749, shield_growth=cShieldGrowth),
        Group("toxopid", 70),
        Group("navanax", 70, 1, effect="boss"),  # never spawns: ends before it begins, as in FFA
        Group("spiroct", 72, 82, every=2, grow=3.7324436, cap=6, shields=167.068, shield_growth=cShieldGrowth),
        Group("arkyid", 74, 99, every=2, grow=10.064946, cap=13, shields=957.8565, shield_growth=cShieldGrowth),
        Group("horizon", 76, 87, every=2, grow=2.3367858, cap=6,
              shields=267.30878, shield_growth=cShieldGrowth),
        Group("nova", 78, 92, grow=3.0233536, cap=13, shields=1046.9594, shield_growth=cShieldGrowth),
        Group("zenith", 78, 103, amount=2, grow=11.70797, cap=13,
              shields=1046.9594, shield_growth=cShieldGrowth),
        Group(EXO + "orca", 80),
        Group("atrax", 83, 93, every=4, grow=3.9277453, cap=6, shields=378.68744, shield_growth=cShieldGrowth),
        Group("quasar", 84, 95, every=2, grow=3.7063124, cap=6, shields=356.4117, shield_growth=cShieldGrowth),
        Group("quasar", 85, 111, amount=2, grow=9.971519, cap=13,
              shields=1202.8895, shield_growth=cShieldGrowth),
        Group("vela", 86, 113, grow=13.056084, cap=13, shields=1225.1653, shield_growth=cShieldGrowth),
        Group("arkyid", 88, 95, every=2, amount=0, grow=3.7771335, cap=6,
              shields=334.136, shield_growth=cShieldGrowth),
        Group("arkyid", 90, 122, grow=14.059486, cap=13, shields=1314.2682, shield_growth=cShieldGrowth),
        Group(EXO + "Fusion", 90, grow=100),
        Group("nova", 91, 99, every=2, amount=3, grow=2.0371065, cap=6,
              shields=523.4797, shield_growth=cShieldGrowth),
        Group("atrax", 93, 112, every=2, amount=3, grow=9.924236, cap=13,
              shields=1381.0953, shield_growth=cShieldGrowth),
        Group("dagger", 94, 114, every=2, grow=4.6671686, cap=13,
              shields=1403.3711, shield_growth=cShieldGrowth),
        Group("arkyid", 98, 109, every=4, amount=0, grow=2.3732305, cap=6,
              shields=478.92825, shield_growth=cShieldGrowth),
        Group("scepter", 100, 124, every=2, grow=14.904232, cap=13,
              shields=1537.0255, shield_growth=cShieldGrowth),
        Group(EXO + "T-prometheus", 100, 90, grow=100),  # never spawns: ends before it begins, as in FFA
        Group("zenith", 102, 111, every=3, grow=2.7371678, cap=6,
              shields=523.4797, shield_growth=cShieldGrowth),
        Group("antumbra", 104, 132, every=2, grow=13.021269, cap=13,
              shields=1626.1284, shield_growth=cShieldGrowth),
        Group("quasar", 110, 119, every=2, grow=2.9432948, cap=6,
              shields=601.44476, shield_growth=cShieldGrowth),
        Group("atrax", 111, 122, every=4, grow=2.498685, cap=6, shields=690.54767, shield_growth=cShieldGrowth),
        Group("vela", 112, 123, every=3, amount=0, grow=3.0705252, cap=6,
              shields=612.58264, shield_growth=cShieldGrowth),
        Group("vela", 112, 141, every=2, grow=12.828225, cap=13,
              shields=1804.3344, shield_growth=cShieldGrowth),
        Group(EXO + "molten", 112, effect="boss"),
        Group("dagger", 113, 122, every=4, amount=3, grow=3.2900357, cap=6,
              shields=701.68555, shield_growth=cShieldGrowth),
        Group("spiroct", 113, 139, amount=2, grow=14.764687, cap=13,
              shields=1826.61, shield_growth=cShieldGrowth),
        Group("vela", 114, 145, grow=16.57697, cap=13, shields=1848.8857, shield_growth=cShieldGrowth),
        Group("mace", 115, 134, amount=3, grow=6.216748, cap=13,
              shields=1871.1615, shield_growth=cShieldGrowth),
        Group("crawler", 116, 131, grow=3.550756, cap=13, shields=1893.4373, shield_growth=cShieldGrowth),
        Group(EXO + "colossus", 120, grow=100, effect="boss"),
        Group("arkyid", 121, 130, every=2, amount=0, grow=3.266715, cap=6,
              shields=657.1341, shield_growth=cShieldGrowth),
        Group("scepter", 123, 130, every=3, amount=0, grow=2.0180311, cap=6,
              shields=768.51276, shield_growth=cShieldGrowth),
        Group("arkyid", 123, 149, grow=10.219584, cap=13, shields=2049.3674, shield_growth=cShieldGrowth),
        Group(EXO + "xenoct", 123, grow=100),
        Group("scepter", 125, 150, every=2, grow=10.893033, cap=13,
              shields=2093.9187, shield_growth=cShieldGrowth),
        Group("vela", 130, every=16, grow=33, shields=500, shield_growth=4 * cShieldGrowth, effect="boss"),
        Group("crawler", 130, 139, every=2, amount=3, grow=3.1964254, cap=6,
              shields=946.7186, shield_growth=cShieldGrowth),
        Group("antumbra", 131, 140, every=3, amount=0, grow=3.3527763, cap=6,
              shields=813.0642, shield_growth=cShieldGrowth),
        Group("atrax", 132, amount=3, grow=7.3258805, cap=13, shields=2249.8489, shield_growth=cShieldGrowth),
        Group("mace", 133, 142, every=2, grow=2.890843, cap=6, shields=935.58075, shield_growth=cShieldGrowth),
        Group("vela", 133, every=2, grow=19.907948, cap=13, shields=2272.1248, shield_growth=cShieldGrowth),
        Group("fortress", 135, every=2, amount=2, grow=9.170129, cap=13,
              shields=2316.676, shield_growth=cShieldGrowth),
        Group("spiroct", 138, 145, every=3, grow=2.8064475, cap=6,
              shields=913.305, shield_growth=cShieldGrowth),
        Group("nova", 140, grow=4.944846, cap=13, shields=2428.0547, shield_growth=cShieldGrowth),
        Group("vela", 140, 148, every=3, amount=0, grow=2.4795914, cap=6,
              shields=902.1672, shield_growth=cShieldGrowth),
        Group("arkyid", 140, every=2, grow=14.949802, cap=13, shields=2428.0547, shield_growth=cShieldGrowth),
        Group(EXO + "b05-centauri", 140, effect="boss"),
        Group(EXO + "bloodshed", 140, grow=100),
        Group("vela", 142, grow=15.25532, cap=13, shields=2472.6062, shield_growth=cShieldGrowth),
        Group(EXO + "hex", 142),
        Group("vela", 144, 151, every=2, amount=0, grow=2.3142908, cap=6,
              shields=924.4429, shield_growth=cShieldGrowth),
        Group("arkyid", 145, every=16, grow=33, shields=500, shield_growth=4 * cShieldGrowth, effect="boss"),
        Group("vela", 146, every=2, grow=15.61611, cap=13, shields=2561.7092, shield_growth=cShieldGrowth),
        Group("arkyid", 148, 158, every=4, amount=0, grow=2.1589665, cap=6,
              shields=1024.6837, shield_growth=cShieldGrowth),
        Group("scepter", 149, 160, every=3, amount=0, grow=3.9351482, cap=6,
              shields=1046.9594, shield_growth=cShieldGrowth),
        Group("atrax", 150, 157, every=4, grow=3.0644674, cap=6,
              shields=1124.9244, shield_growth=cShieldGrowth),
        Group("arkyid", 150, grow=13.298361, cap=13, shields=2650.812, shield_growth=cShieldGrowth),
        Group(EXO + "b06-eros", 150),
        Group("nova", 151, 162, every=3, amount=3, grow=2.8240995, cap=6,
              shields=1214.0273, shield_growth=cShieldGrowth),
        Group("fortress", 155, 164, every=3, grow=2.6612978, cap=6,
              shields=1158.338, shield_growth=cShieldGrowth),
        Group(EXO + "asgard", 160),
        Group("vela", 162, 169, every=3, amount=0, grow=3.2351086, cap=6,
              shields=1136.0624, shield_growth=cShieldGrowth),
        Group("vela", 166, 174, every=3, amount=0, grow=3.7895713, cap=6,
              shields=1236.3031, shield_growth=cShieldGrowth),
        Group("arkyid", 167, 176, every=2, amount=0, grow=3.4801512, cap=6,
              shields=1214.0273, shield_growth=cShieldGrowth),
        Group("vela", 170, 179, every=3, amount=0, grow=2.9231658, cap=6,
              shields=1280.8546, shield_growth=cShieldGrowth),
        Group("arkyid", 174, 185, every=4, amount=0, grow=2.7223077, cap=6,
              shields=1325.406, shield_growth=cShieldGrowth),
        Group(EXO + "balaenoptera", 180),
        Group("antumbra", 186, every=33, grow=33, cap=16, shield_growth=cShieldGrowth, effect="boss"),
        Group(EXO + "T-atlas", 200, grow=100),
        Group(EXO + "twilight", 200),
        Group(EXO + "apotheosis", 250, effect="boss"),
        Group(EXO + "sagittarius", 300, effect="boss"),
    ]


def fnExpandGroups(arGroups, dtSpawns=None, arNavalSpawnKeys=(), dtSpawnAliases=None):
    """The groups as one map spawns them.

    On a map with naval spawns, each naval group comes up every naval spawn (one copy pinned to each,
    since a boat at a dry spawn dies at once); everywhere else its unit takes the stand-in from
    `cdtNavalSwap`. A group pinned to a spawn key the map does not have is resolved through
    `dtSpawnAliases` ({key used here: the map's own key}); `dtSpawns` = None skips that check."""
    dtAliases = dtSpawnAliases or {}
    arOut = []
    for sGroup in arGroups:
        if sGroup.unit in cdtNavalSwap:
            if arNavalSpawnKeys:
                for vKey in arNavalSpawnKeys:
                    sCopy = copy.copy(sGroup)
                    sCopy.at = vKey
                    arOut.append(sCopy)
                continue
            sGroup = copy.copy(sGroup)
            sGroup.unit = cdtNavalSwap[sGroup.unit]
        if sGroup.at is not None and dtSpawns is not None:
            vKey = dtAliases.get(sGroup.at, sGroup.at)
            if vKey not in dtSpawns:
                raise ValueError("A wave group is pinned to spawn '%s', which this map does not have; map it to "
                                 "one of %s with spawn aliases" % (sGroup.at, sorted(dtSpawns)))
            if vKey != sGroup.at:
                sGroup = copy.copy(sGroup)
                sGroup.at = vKey
        arOut.append(sGroup)
    return arOut


def fnBuildRules(dtSpawns, arNavalSpawnKeys=(), dtSpawnAliases=None):
    """Rules JSON object for a map's "rules" tag: the shared match rules plus the map's spawn groups."""
    dtRules = copy.deepcopy(sys_config.cdtMatchRules)
    arGroups = fnExpandGroups(build_groups(), dtSpawns, arNavalSpawnKeys, dtSpawnAliases)
    dtRules["spawns"] = [sGroup.to_json(dtSpawns) for sGroup in arGroups]
    return dtRules


def fnUnitsOnWave(vWave, arGroups, vSpawnCount):
    """(unit count, total health incl. boss multiplier and shields, {label: count}) for one wave of
    expanded groups on a map with `vSpawnCount` spawn points."""
    vUnits, vHp, dtCounts = 0, 0.0, {}
    for sGroup in arGroups:
        vSpawned = sGroup.spawned(vWave)
        if vSpawned == 0:
            continue
        vCount = vSpawned * (vSpawnCount if sGroup.at is None else 1)
        vBoss = sGroup.effect == "boss"
        vUnits += vCount
        vHp += vCount * (UNIT_HP.get(sGroup.unit, 0) * (BOSS_HEALTH_MULTIPLIER if vBoss else 1.0)
                         + sGroup.shield_at(vWave))
        vLabel = sGroup.unit.replace(EXO, "") + (" (boss)" if vBoss else "")
        dtCounts[vLabel] = dtCounts.get(vLabel, 0) + vCount
    return vUnits, vHp, dtCounts


def _fnToughness(vLabel):
    vName = vLabel.replace(" (boss)", "")
    return UNIT_HP.get(EXO + vName, UNIT_HP.get(vName, 0)) * (BOSS_HEALTH_MULTIPLIER if "(boss)" in vLabel else 1)


def fnWaveSummary(arWaves, arGroups, vSpawnCount):
    """Units, total health and the toughest units for selected waves."""
    arRows = []
    for vWave in arWaves:
        vUnits, vHp, dtCounts = fnUnitsOnWave(vWave, arGroups, vSpawnCount)
        arTop = sorted(dtCounts.items(), key=lambda kv: -_fnToughness(kv[0]))[:4]
        arRows.append({"wave": vWave, "units": vUnits, "total_hp": int(vHp),
                       "toughest": ", ".join("%dx %s" % (c, n) for n, c in arTop)})
    return arRows


def fnWaveCurve(vFirst, vLast, vWindow, arGroups, vSpawnCount):
    """Average units and health per wave over windows of waves."""
    arRows = []
    for vStart in range(vFirst, vLast + 1, vWindow):
        arData = [fnUnitsOnWave(w, arGroups, vSpawnCount)[:2] for w in range(vStart, vStart + vWindow)]
        arRows.append({"waves": "%d-%d" % (vStart, vStart + vWindow - 1),
                       "avg_units": round(sum(u for u, _ in arData) / vWindow, 1),
                       "min_units": min(u for u, _ in arData), "max_units": max(u for u, _ in arData),
                       "avg_total_hp": int(sum(h for _, h in arData) / vWindow)})
    return arRows


# Entry points generate_map.py has always used (Biomes Extended Remastered: five spawns, none on water).

def build_rules(spawn_positions):
    """Rules JSON object for the map's "rules" tag (Survival / PvE)."""
    return fnBuildRules(spawn_positions)


def wave_summary(waves_to_report):
    """Units, total health and the toughest units for selected waves."""
    return fnWaveSummary(waves_to_report, fnExpandGroups(build_groups()), 5)


def curve(first=1, last=160, window=10):
    """Average units and health per wave over windows of waves."""
    return fnWaveCurve(first, last, window, fnExpandGroups(build_groups()), 5)
