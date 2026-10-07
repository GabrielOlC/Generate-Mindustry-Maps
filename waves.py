"""Wave design for "Biomes Extended Remastered".

Each biome spawn sends the Exogenesis Old faction that matches its theme, while vanilla
Serpulo units come from every spawn. Groups are written in the JSON format that
mindustry.game.SpawnGroup reads (v8 build 159.7):

    type, begin, end, spacing, max, scaling, shields, shieldScaling, amount, effect, spawn

`begin`/`end` are 0-based wave indexes in the file; this module uses human wave numbers
(wave 1 = first wave) and converts them. `scaling` counts *appearances* of the group, not waves:
units per spawn point = min(amount + int(appearances_so_far / scaling), max).
A group without a `spawn` position spawns at all five spawn points.
"""

EXO = "exogenesisold-"
NEVER = 2147483647

# Health values used only for the summary tables (vanilla: UnitTypes.java @ v159.7,
# Exogenesis Old: content/units/*.json @ AureusStratus/ExoGenesis main).
UNIT_HP = {
    "dagger": 150, "mace": 550, "fortress": 900, "scepter": 9000, "reign": 24000,
    "nova": 120, "pulsar": 320, "quasar": 640, "vela": 8200, "corvus": 18000,
    "crawler": 150, "atrax": 600, "spiroct": 1000, "arkyid": 8000, "toxopid": 22000,
    "flare": 70, "horizon": 340, "zenith": 700, "antumbra": 7200, "eclipse": 22000,
    # Genesux (cold faction)
    EXO + "b01-orion": 360, EXO + "b01-majoris": 300, EXO + "b02-galileo": 890, EXO + "b02-gacrux": 890,
    EXO + "b03-kuiper": 2600, EXO + "b03-kentaurus": 2000, EXO + "b04-oort": 12000, EXO + "b04-vega": 12950,
    EXO + "b05-sirius": 45000, EXO + "b05-centauri": 38400, EXO + "b06-eros": 79800, EXO + "b06-altair": 82400,
    EXO + "b07-atlas": 190000, EXO + "b07-universalis": 174000, EXO + "sagittarius": 10000000,
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
}

BOSS_HEALTH_MULTIPLIER = 1.5  # StatusEffects.boss.healthMultiplier @ v159.7


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
    """All spawn groups. Spawn keys: frozen, semiarid, desert, forest, volcano."""
    g = Group
    E = EXO
    return [
        # ---- Vanilla Serpulo, every spawn point (5x the listed amount) -------------------
        g("dagger", 1, 30, grow=4, cap=2),
        g("flare", 2, 28, every=2, grow=4, cap=2),
        g("crawler", 4, 30, every=3, amount=2, grow=3, cap=4),
        g("nova", 6, 32, every=2, grow=5, cap=2),
        g("mace", 12, 60, every=2, grow=6, cap=2),
        g("horizon", 14, 56, every=3, grow=5, cap=2),
        g("atrax", 16, 62, every=3, grow=6, cap=2),
        g("pulsar", 20, 62, every=4, grow=5, cap=2),
        g("fortress", 26, every=3, grow=8, cap=2, shield_growth=6),
        g("zenith", 28, every=4, grow=8, cap=2, shield_growth=6),
        g("spiroct", 32, every=4, grow=8, cap=2, shield_growth=6),
        g("quasar", 34, every=5, grow=8, cap=2, shield_growth=6),
        g("scepter", 45, every=6, grow=8, cap=2, shield_growth=15),
        g("antumbra", 48, every=6, grow=8, cap=2, shield_growth=15),
        g("arkyid", 52, every=7, grow=8, cap=2, shield_growth=20),
        g("vela", 55, every=7, grow=8, cap=2, shield_growth=20),
        g("reign", 65, every=6, grow=5, cap=3, shield_growth=30),
        g("eclipse", 68, every=6, grow=5, cap=3, shield_growth=30),
        g("toxopid", 72, every=7, grow=5, cap=3, shield_growth=40),
        g("corvus", 76, every=7, grow=5, cap=3, shield_growth=40),
        # milestone guardians (boss status: x1.5 health, x1.3 damage)
        g("fortress", 25, 25, effect="boss", note="Milestone guardian"),
        g("scepter", 50, 50, effect="boss", note="Milestone guardian"),
        g("reign", 75, 75, effect="boss", shields=2000, note="Milestone guardian"),

        # ---- Genesux @ frozen north ---------------------------------------------------
        g(E + "b01-orion", 8, 44, amount=2, grow=3, cap=5, at="frozen"),
        g(E + "b01-majoris", 10, 44, every=2, amount=2, grow=3, cap=5, at="frozen"),
        g(E + "b02-galileo", 18, 70, every=2, grow=4, cap=5, at="frozen"),
        g(E + "b02-gacrux", 20, 70, every=2, grow=4, cap=4, at="frozen"),
        g(E + "b03-kuiper", 28, every=2, grow=5, cap=4, shield_growth=8, at="frozen"),
        g(E + "b03-kentaurus", 30, every=3, grow=5, cap=3, shield_growth=8, at="frozen"),
        g(E + "b04-oort", 40, every=3, grow=6, cap=3, shield_growth=15, at="frozen"),
        g(E + "b04-vega", 44, every=4, grow=6, cap=3, shield_growth=15, at="frozen"),
        g(E + "b05-sirius", 56, every=4, grow=6, cap=3, shield_growth=25, at="frozen"),
        g(E + "b05-centauri", 60, every=5, grow=5, cap=3, shield_growth=25, at="frozen"),
        g(E + "b06-eros", 72, every=5, grow=5, cap=3, shield_growth=40, at="frozen"),
        g(E + "b06-altair", 76, every=6, grow=5, cap=3, shield_growth=40, at="frozen"),
        g(E + "b07-atlas", 90, every=6, grow=5, cap=3, shield_growth=80, at="frozen"),
        g(E + "b07-universalis", 94, every=8, grow=5, cap=3, shield_growth=80, at="frozen"),
        g(E + "b06-eros", 90, 90, effect="boss", shields=5000, at="frozen", note="Herald"),
        g(E + "sagittarius", 100, every=30, effect="boss", shield_growth=3000, at="frozen",
          note="Apex boss: 10,000,000 HP, 144 armor"),

        # ---- Solran @ volcano south-west ------------------------------------------------
        g(E + "sol", 8, 44, amount=2, grow=3, cap=5, at="volcano"),
        g(E + "heat", 10, 48, every=2, grow=3, cap=5, at="volcano"),
        g(E + "corona", 18, 70, grow=4, cap=5, at="volcano"),
        g(E + "molten", 20, 70, every=2, grow=4, cap=4, at="volcano"),
        g(E + "photosphere", 28, every=2, grow=5, cap=4, shield_growth=8, at="volcano"),
        g(E + "magma", 30, every=3, grow=5, cap=3, shield_growth=8, at="volcano"),
        g(E + "radiative", 40, every=3, grow=6, cap=3, shield_growth=15, at="volcano"),
        g(E + "lava", 44, every=4, grow=6, cap=3, shield_growth=15, at="volcano"),
        g(E + "core", 56, every=4, grow=6, cap=3, shield_growth=25, at="volcano"),
        g(E + "eruption", 60, every=5, grow=5, cap=3, shield_growth=25, at="volcano"),
        g(E + "Fusion", 72, every=5, grow=5, cap=3, shield_growth=40, at="volcano"),
        g(E + "collapse", 90, every=6, grow=5, cap=3, shield_growth=80, at="volcano"),
        g(E + "Fusion", 90, 90, effect="boss", shields=5000, at="volcano", note="Herald"),
        g(E + "arcturus", 110, every=30, effect="boss", shield_growth=3000, at="volcano",
          note="Apex boss: 5,300,000 HP, 460 armor"),

        # ---- Elecian @ desert east ------------------------------------------------------
        g(E + "challenge", 8, 40, amount=3, grow=2, cap=10, at="desert"),
        g(E + "disrespect", 10, 50, grow=3, cap=5, at="desert"),
        g(E + "dispute", 12, 52, every=2, grow=3, cap=4, at="desert"),
        g(E + "strife", 20, 70, every=2, grow=4, cap=4, at="desert"),
        g(E + "debate", 24, 70, every=3, grow=4, cap=3, at="desert"),
        g(E + "combat", 30, every=3, grow=5, cap=3, shield_growth=8, at="desert"),
        g(E + "disagreement", 38, every=4, grow=6, cap=3, shield_growth=12, at="desert"),
        g(E + "disaccord", 50, every=5, grow=6, cap=2, shield_growth=20, at="desert"),
        g(E + "hostile", 56, every=4, grow=6, cap=3, shield_growth=25, at="desert"),
        g(E + "assault", 70, every=5, grow=5, cap=3, shield_growth=35, at="desert"),
        g(E + "contention", 74, every=6, grow=5, cap=3, shield_growth=35, at="desert"),
        g(E + "bloodshed", 90, every=6, grow=5, cap=3, shield_growth=80, at="desert"),
        g(E + "battle", 94, every=8, grow=5, cap=3, shield_growth=80, at="desert"),
        g(E + "assault", 90, 90, effect="boss", shields=5000, at="desert", note="Herald"),
        g(E + "war", 120, every=30, effect="boss", shield_growth=3000, at="desert",
          note="Apex boss: 5,000,000 HP, 90 armor, flying"),

        # ---- Quantra + Exogenesis titans @ forest west ----------------------------------
        g(E + "pteris", 8, 44, amount=2, grow=3, cap=5, at="forest"),
        g(E + "irises", 12, 52, grow=3, cap=5, at="forest"),
        g(E + "guardian", 14, 56, every=2, grow=3, cap=4, at="forest"),
        g(E + "aster", 20, 70, every=2, grow=4, cap=4, at="forest"),
        g(E + "crystal-drone-healer", 26, every=5, grow=8, cap=3, at="forest", note="Flying healer escort"),
        g(E + "urtica", 32, every=3, grow=5, cap=3, shield_growth=8, at="forest"),
        g(E + "thymus", 42, every=4, grow=6, cap=3, shield_growth=15, at="forest"),
        g(E + "anvil", 58, every=5, grow=5, cap=3, shield_growth=25, at="forest"),
        g(E + "toxicity", 64, every=5, grow=5, cap=3, shield_growth=30, at="forest"),
        g(E + "virgo", 76, every=6, grow=5, cap=3, shield_growth=40, at="forest"),
        g(E + "xenoct", 90, every=6, grow=5, cap=3, shield_growth=80, at="forest"),
        g(E + "fornax", 94, every=8, grow=5, cap=3, shield_growth=80, at="forest"),
        g(E + "virgo", 90, 90, effect="boss", shields=5000, at="forest", note="Herald"),
        g(E + "xenoct", 105, every=30, amount=2, effect="boss", shield_growth=1500, at="forest",
          note="Apex pair"),

        # ---- Titan host (vanilla lines + Exogenesis T6/T7) @ semi-arid north-east -------
        g("crawler", 10, 40, every=2, amount=3, grow=2, cap=8, at="semiarid", note="Dust swarm"),
        g("atrax", 20, 62, every=3, grow=3, cap=4, at="semiarid"),
        g("fortress", 30, every=3, grow=5, cap=3, shield_growth=8, at="semiarid"),
        g("quasar", 36, every=4, grow=5, cap=3, shield_growth=10, at="semiarid"),
        g(E + "stella", 50, every=5, grow=5, cap=3, shield_growth=15, at="semiarid"),
        g(E + "T-nemesis", 56, every=5, grow=5, cap=3, shield_growth=20, at="semiarid"),
        g(E + "T-atlas", 64, every=5, grow=5, cap=3, shield_growth=30, at="semiarid"),
        g(E + "T-prometheus", 70, every=6, grow=5, cap=3, shield_growth=35, at="semiarid"),
        g(E + "twilight", 72, every=6, grow=5, cap=3, shield_growth=35, at="semiarid"),
        g(E + "hex", 80, every=7, grow=5, cap=3, shield_growth=40, at="semiarid"),
        g(E + "nadir", 90, every=6, grow=5, cap=3, shield_growth=80, at="semiarid"),
        g(E + "colossus", 96, every=8, grow=8, cap=1, shield_growth=100, at="semiarid"),
        g(E + "T-prometheus", 90, 90, effect="boss", shields=5000, at="semiarid", note="Herald"),
        g(E + "colossus", 115, every=30, effect="boss", shield_growth=2000, at="semiarid",
          note="Apex carrier"),
    ]


def build_rules(spawn_positions):
    """Rules JSON object for the map's "rules" tag (Survival / PvE)."""
    return {
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
        "loadout": [
            {"item": "copper", "amount": 700},
            {"item": "lead", "amount": 300},
        ],
        "spawns": [grp.to_json(spawn_positions) for grp in build_groups()],
    }


def units_on_wave(wave, groups=None, spawn_count=5):
    """(unit count, total health incl. boss multiplier and shields, {label: count}) for one wave."""
    groups = groups or build_groups()
    units, hp, counts = 0, 0.0, {}
    for grp in groups:
        n = grp.spawned(wave)
        if n == 0:
            continue
        count = n * (spawn_count if grp.at is None else 1)
        boss = grp.effect == "boss"
        units += count
        hp += count * (UNIT_HP.get(grp.unit, 0) * (BOSS_HEALTH_MULTIPLIER if boss else 1.0) + grp.shield_at(wave))
        label = grp.unit.replace(EXO, "") + (" (boss)" if boss else "")
        counts[label] = counts.get(label, 0) + count
    return units, hp, counts


def wave_summary(waves_to_report):
    """Units, total health and the toughest units for selected waves."""
    groups = build_groups()
    rows = []
    for wave in waves_to_report:
        units, hp, counts = units_on_wave(wave, groups)

        def toughness(label):
            name = label.replace(" (boss)", "")
            return UNIT_HP.get(EXO + name, UNIT_HP.get(name, 0)) * (BOSS_HEALTH_MULTIPLIER if "(boss)" in label else 1)

        top = sorted(counts.items(), key=lambda kv: -toughness(kv[0]))[:4]
        rows.append({"wave": wave, "units": units, "total_hp": int(hp),
                     "toughest": ", ".join("%dx %s" % (c, n) for n, c in top)})
    return rows


def curve(first=1, last=160, window=10):
    """Average units and health per wave over windows of waves."""
    groups = build_groups()
    rows = []
    for a in range(first, last + 1, window):
        data = [units_on_wave(w, groups)[:2] for w in range(a, a + window)]
        rows.append({"waves": "%d-%d" % (a, a + window - 1),
                     "avg_units": round(sum(u for u, _ in data) / window, 1),
                     "min_units": min(u for u, _ in data), "max_units": max(u for u, _ in data),
                     "avg_total_hp": int(sum(h for _, h in data) / window)})
    return rows
