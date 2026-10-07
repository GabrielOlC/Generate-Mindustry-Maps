# Biomes Extended Remastered

An 800×800 PvE survival map for **Mindustry v8 Build 159.7**, designed for **4–8 players** and the
**Exogenesis Old** mod (`exogenesisold` 1.9.1). One player core sits in the centre. Five biomes surround
it, and each one sends out the Exogenesis faction that matches its theme. The same biome also holds the
resources that faction's tech tree needs, so beating a front means expanding into its land.

| | |
|---|---|
| Map file | `maps\Biomes Extended Remastered.msav` (save format 13) |
| Size | 800 × 800 tiles (640,000) |
| Mode | Survival / PvE, endless waves |
| Player core | Core: Foundation at the centre (tiles 399–402 × 399–402) |
| Enemy spawns | 5 spawn points, one per biome, all near the map edge |
| Session length | Wave 100 at ~4 h 15 min, wave 120 at ~5 h 05 min (players can call waves early) |
| Required mod | Exogenesis Old 1.9.1 (needs game build 158 or newer) |

![Map preview](docs/preview.png)

*Preview: red circles are enemy spawns with their 37.5-tile drop zones, cyan rings are outpost pads,
yellow dots are named choke points, and orange marks the core. North is up.*

---

## 1. Install and play

1. Turn on **Exogenesis Old** under *Mods* and restart the game.
2. From the main menu open **Editor → Import Map** and pick
   `maps\Biomes Extended Remastered.msav` in this project's folder.
   (Or copy the file into the game's `maps` folder.)
3. Choose **Play → Custom Game → Biomes Extended Remastered → Survival**, or host it for friends.

The wave list, loadout and rules are stored in the map file. You can change them in the editor
under *Map Info → Rules / Waves*.

**Built-in rules:** 7 minutes to set up before wave 1, then one wave every 150 s. Players may call
waves early. The waves never end. Spawn points are visible. Each unit type has a cap of 24, plus 16
from the Foundation core (more with bigger cores). The starting loadout is 700 copper and 300 lead.

---

## 2. Layout

| Direction | Biome | Spawn (x, y) | Enemy faction |
|---|---|---|---|
| North | Frozen / cryofluid | (420, 778) | **Genesux**, the cold faction |
| North-east | Semi-arid steppe | (730, 730) | **Titan host**: vanilla lines plus Exogenesis tier 6/7 |
| East | Desert | (778, 352) | **Elecian** |
| West | Forest | (22, 450) | **Quantra** plus Exogenesis titans |
| South-west | Volcano | (68, 68) | **Solran**, the molten faction |
| Centre | Crossroads Basin | core at (400, 400) | — |

Vanilla Serpulo units (dagger up to corvus) come out of **every** spawn.

The map is built from three rings:

- **Crossroads Basin (radius ~60):** a calm stone-and-grass bowl around the core. It holds only the
  starter resources.
- **Crossroads Rim:** a stone ring 9–13 tiles thick. The only ways through are **five 16-tile gates**,
  one facing each biome.
- **Ring Road (just outside the rim, to r ≈ 92):** an open band that connects all five gates.
  Separator ridges between the biomes start just beyond it.

Each biome is then cut in two by a natural barrier. The **core side** is safe to expand into. The
**enemy side** holds the spawn and the richest deposits. The barrier can only be crossed at named
choke points (section 5).

---

## 3. Biomes and resource distribution

Tile counts come from the generator report (`... - report.json`, seed 1597).

Ores come as **many small patches** spread across each biome: 429 patches in total, each 3–5.5 tiles
in radius, holding 10–84 ore tiles (median 36). Any two patches are at least 8 tiles apart, and two
patches of the same ore are at least 26 tiles apart, so every resource is scattered over its biome
instead of sitting in one big field. Rarer ores sit farther from the core.

| Biome | Area (tiles) | Patches | Ores (tiles) | Liquids and special floors (tiles) |
|---|---|---|---|---|
| **Crossroads Basin** (centre) | 10,801 | 19 | copper 343 · lead 213 · scrap 72 · coal 39 | darksand (sand) 1,843 |
| **Forest** (W) | 110,963 | 68 | lead 834 · coal 779 · copper 662 · titanium 287 · scrap 151 | **water 7,967** (Great River, Mirror Lake, fords) · spore moss 6,322 · sand/darksand 1,308 |
| **Volcano** (SW) | 148,025 | 88 | thorium 787 · **tungsten 467** · **beryllium 459** · coal 453 · titanium 344 · lead 293 · copper 215 · scrap 196 | **lava (molten slag) 4,353** · **pyromagma 983** (Exo, pumps pyroplasma) · hotrock/magmarock (heat) 18,045 |
| **Frozen** (N) | 112,525 | 89 | **titanium 1,105** · **siradamite 522** (Exo) · **stellar steel 381** (Exo) · lead 380 · thorium 366 · copper 238 · scrap 85 | **pooled cryofluid 9,055** · **glowing vein 1,821** (Exo, pumps cold plasma) · **siratla crystal 403** (Exo, drills astrolite; 11 patches) |
| **Semi-arid** (NE) | 89,200 | 89 | titanium 658 · **dytrix 498** (Exo) · copper 481 · lead 352 · coal 322 · scrap 307 · **urbium 299** (Exo) · thorium 260 | shale (oil bonus) 6,222 · darksand 6,667 · oasis water 373 |
| **Desert** (E) | 168,486 | 76 | **scrap 1,063** · **urbium 488** (Exo) · lead 419 · titanium 357 · copper 291 · coal 138 · thorium 135 | **tar (oil) 2,205** · shale (oil bonus) 13,842 · sand/darksand 120,431 |

### What each biome is for

- **Crossroads Basin.** Copper, lead, scrap, a little coal and darksand patches, which is enough for
  graphite and silicon. There is no titanium, water or oil here, so you have to expand.
- **Forest (W).** Water for pumps, the richest coal and lead, and spore moss for cultivators and spore
  presses (**Spore Hollow**, north-west). Quantra's gamma-green (Irradiation Kiln) needs this water.
- **Volcano (SW).** Thorium, plus the two Erekir ores that Exogenesis' **Solran** tech uses:
  beryllium + sand → *volcanite* at the Ignition Forge, and tungsten for the Primal Forge and Hadel
  Furnace. Molten slag feeds slag separators and Exogenesis' Core Drill. Pyromagma creeks run toward
  the core side. Magmarock and hotrock power thermal generators.
- **Frozen (N).** The richest titanium. Cryofluid lakes can be pumped directly, which skips the
  cryofluid mixers. The **Siratla Glacier** (r > ~305) holds the core **Genesux** materials:
  siradamite and stellar steel ores, siratla crystal (astrolite) and glowing veins (cold plasma).
- **Semi-arid (NE).** All-round titanium, copper and coal. Exogenesis **dytrix** and **urbium** are in
  the outer steppe, and the **Last Oasis** gives water on the far side. Genesux late-game forges
  need both ores, so the frozen and semi-arid fronts feed each other.
- **Desert (E).** Oil from tar pits and shale for plastanium, which Quantra and Elecian
  alloys need. The **Derelict Wreck Field** (south-east) is a rich scrap ruin, and urbium sits deep
  in the dunes.

### Outposts (core-zone pads)

Ten 7×7 `core-zone` pads let players **build a new core directly on them**: Shard, Foundation or
Nucleus. A forward core cuts hauling time and gives a respawn point. The first pad in each biome is
on the safe core side. The second sits on the frontier, which in four biomes means past the choke
points on the enemy side.

| Biome | First pad (core side) | Second pad (frontier) |
|---|---|---|
| Frozen | Rimeward Outpost (361, 568) | Siratla Outpost (213, 699): enemy side, on the glacier |
| Semi-arid | Steppe Outpost (495, 526) | Oasis Outpost (655, 647): enemy side, beyond the mesas |
| Desert | Dunewatch Outpost (556, 337) | Wreckage Outpost (688, 262): enemy side, east of the dune wall |
| Forest | Riverbank Outpost (232, 436) | Sporewood Outpost (112, 520): enemy side, west bank |
| Volcano | Ember Outpost (309, 253) | Ashfall Outpost (358, 103): core side, in the Ash Fields facing the South Basalt Bridge |

---

## 4. Terrain transitions

Biome borders follow a noise-warped angle (±6°), so they wander instead of running as straight
spokes. Floors dither across a 9–23-tile blend band. Five **separator ridges** sit on the borders.
Each is 13–19 tiles thick, which also stops legged units: Mindustry only lets legs walk over rock
bands thinner than about 5 tiles.

| Border | Ridge (extent) | What the transition looks like |
|---|---|---|
| Basin → every biome | Crossroads Rim (r ≈ 60) | Stone and grass give way to each biome's ground along the Ring Road. Basin floor bleeds out through the gates. |
| Desert ↔ Semi-arid (22°) | **Salt Escarpment**, Ring Road to the map edge | Salt flats on both sides of a sand-and-dacite escarpment. |
| Semi-arid ↔ Frozen (68°) | **Rime Bluffs**, r 92–300 | Beyond r 300 it opens into a **tundra steppe**: dirt dotted with snow and ice-snow. |
| Frozen ↔ Forest (135°) | **Taiga Wall**, r 92–345 | A **boreal taiga** band: snow pines on snow and pines on grass. The open NW taiga corner lies beyond r 345. |
| Forest ↔ Volcano (205°) | **Ashwood Ridge**, Ring Road to the map edge | **Burnt forest**: char floors and dead white trees fading into basalt. |
| Volcano ↔ Desert (285°) | **Obsidian Wall**, Ring Road to the map edge | **Ash dunes**: darksand mixed into basalt and sand. |

Signature terrain inside the biomes:

- **Volcano.** A volcanic cone about 40 tiles in radius at (230, 185), around a molten-slag crater. Two **lava
  rivers** run to the west edge and the south edge, which walls off the south-west corner. Smaller
  lava pools and two pyromagma creeks are scattered through the rest of the biome.
- **Forest.** The **Great River** meanders from the Taiga Wall to the Ashwood Ridge through
  **Mirror Lake** (148, 360). Its banks are darksand and mud, and pine groves form natural cover.
  **Spore Hollow** is a purple spore-moss grove in the north-west.
- **Frozen.** A ring of **pooled-cryofluid lakes** at r ≈ 268 separates the inner tundra from
  the **Siratla Glacier**. Ice cliffs and snow pines are scattered around.
- **Semi-arid.** A **mesa arc** (r 212–268) of dirt and dacite plateaus, crossed by two canyons.
  The rest is dry steppe with shale and salt pans.
- **Desert.** A meandering **dune wall** (x ≈ 570–630) splits the sea of sand. Tar pits sit at the
  Tar Narrows and Black Lake. There is a salt pan in the south-east and the derelict wreck field.

---

## 5. Choke points

Coordinates are tile (x, y) as shown in the editor, with the origin at the bottom-left. Every
barrier was tested by closing its crossings and checking that the far side becomes unreachable on
foot (`check_map.py`; all five tests pass).

### Outer crossings (enemy side → core side)

| Biome | Choke point | Position | Width | Barrier it crosses |
|---|---|---|---|---|
| Frozen | **Frost Bridge East** / **Frost Bridge West** | (414, 668) / (291, 645) | 12 | ice causeways through the cryofluid lake ring |
| Semi-arid | **Red Canyon** / **Dust Canyon** | (570, 570) / (520, 608) | 14 / 9 (winding) | the mesa arc |
| Desert | **Tar Narrows** / **Salt Pass** / **Southern Breach** | (615, 398) / (577, 205) / (613, 62) | 15 / 13 / 11 | the dune wall; the Narrows run between two tar-pit fields |
| Forest | **North Ford** / **South Ford** | (174, 500) / (168, 408) | 17 | shallow water across the Great River |
| Volcano | **West Basalt Bridge** / **South Basalt Bridge** | (103, 143) / (233, 91) | 14 | cooled-basalt crossings over the lava rivers |

### Inner gates (Crossroads Rim, 16 tiles wide each)

East Gate (466, 400) · North-east Gate (447, 447) · North Gate (398, 466) · West Gate (334, 402) ·
South-west Gate (365, 344).

### Ridge passes (core side ↔ core side, so defenders can shift between fronts)

Salt Gap (551, 467) desert ↔ semi-arid · Rime Pass (453, 567) semi-arid ↔ frozen ·
Taiga Pass (292, 504) frozen ↔ forest · Cinder Pass (234, 329) forest ↔ volcano ·
Obsidian Gate (437, 255) and Far Obsidian Gate (473, 119) volcano Ash Fields ↔ desert.

Enemies can use these passes too. On the enemy side, armies can only mix in two places: the tundra
(north ↔ north-east) and the NW taiga corner (forest west bank ↔ glacier).

### Measured enemy routes

Mindustry's flow field moves in four directions, so several routes often cost the same. The table
lists every choke point that lies on a route within 2% of the shortest one.

| Spawn | Shortest ground path | Likely choke points |
|---|---|---|
| North (Frozen) | 439 tiles | Frost Bridge East → North Gate |
| North-east (Semi-arid) | 691 tiles | Red Canyon or Dust Canyon → North-east Gate, North Gate (via Rime Pass) or East Gate (via Salt Gap). This army can split three ways. |
| East (Desert) | 567 tiles | Tar Narrows → East Gate |
| West (Forest) | 455 tiles | South Ford → West Gate |
| South-west (Volcano) | 661 tiles | West or South Basalt Bridge → South-west Gate, or Cinder Pass → West Gate |

![Enemy routes](docs/enemy-routes.png)

*Each colour shows one spawn's set of near-shortest ground routes: cyan north, orange north-east,
yellow east, green west, red south-west. Black is rock, blue is deep water or cryofluid, brown is
lava, and white dots are choke points.*

Flying units ignore all of this. They enter from the map edge in the direction of their spawn.

---

## 6. Waves

There are 96 spawn groups. Faction groups are pinned to their own spawn point. Vanilla groups spawn
at all five, so their counts are multiplied by 5.

| Phase | Waves (time) | What arrives |
|---|---|---|
| Landfall | 1–12 (0:07–0:35) | Vanilla tier 1: dagger, flare, crawler, nova |
| Factions emerge | 8–30 | Faction tier 1–2 from each biome: b01/b02 Genesux, sol/heat/corona/molten, challenge/disrespect/dispute/strife, pteris/irises/guardian/aster, plus the north-east dust swarm |
| Escalation | 28–56 (~1:15–2:25) | Tier 3–4: b03/b04, photosphere/magma/radiative/lava, combat/disagreement/disaccord, urtica/thymus, vanilla fortress → vela |
| Siege | 56–89 (~2:25–3:50) | Tier 5–6: b05/b06, core/eruption/Fusion, hostile/assault/contention, anvil/toxicity/virgo, stella/T-nemesis/T-atlas/T-prometheus/twilight/hex, vanilla reign/eclipse/toxopid/corvus |
| Apocalypse | 90+ (~3:50 →) | Tier 7: b07-atlas/universalis, collapse, bloodshed/battle, xenoct/fornax, nadir/colossus, plus apex bosses |

**Milestone guardians (boss status: ×1.5 health, ×1.3 damage).** At wave 25, a boss fortress comes
from each spawn. At wave 50 it's a boss scepter, and at wave 75 a boss reign with 2,000 shields.
At wave 90 each faction sends a **Herald**: b06-eros, Fusion, assault, virgo and T-prometheus,
each with boss status and 5,000 shields.

**Apex bosses.** Each one has boss status and repeats every 30 waves. Its shields grow every wave
after its first appearance.

| Boss | First wave | From | Base stats | Shield growth |
|---|---|---|---|---|
| sagittarius | 100 (~4:15) | North | 10,000,000 HP, 144 armour | +3,000 per wave |
| xenoct ×2 | 105 | West | 210,000 HP each | +1,500 per wave |
| arcturus | 110 (~4:40) | South-west | 5,300,000 HP, 460 armour | +3,000 per wave |
| colossus | 115 | North-east | 287,000 HP, flying carrier | +2,000 per wave |
| war | 120 (~5:05) | East | 5,000,000 HP, 90 armour, flying | +3,000 per wave |

**Difficulty curve.** Averages per 10 waves, with total health including shields and the boss
multiplier:

| Waves | 1–10 | 11–20 | 21–30 | 31–40 | 41–50 | 51–60 | 61–70 | 71–80 | 81–90 | 91–100 | 101–110 | 111–120 | 121–130 | 141–150 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Units per wave | 19 | 59 | 88 | 84 | 68 | 56 | 45 | 37 | 37 | 42 | 46 | 53 | 49 | 56 |
| Total HP per wave | 3.5k | 20k | 44k | 69k | 117k | 195k | 301k | 499k | 727k | 2.39M | 2.02M | 2.22M | 2.85M | 2.76M |

Early waves are many weak units. Later waves are fewer but much tougher, and shields keep growing,
so endless play eventually overwhelms any defence.

**Without the mod.** Exogenesis unit names fall back to **dagger** in the game's wave loader. If the
waves look like endless daggers, Exogenesis Old is not enabled.

---

## 7. Exogenesis Old dependency

The map uses these Exogenesis Old terrain blocks: `pyromagma`, `siratla-stone`,
`siratla-stone-wall`, `siratla-stone-boulder`, `siratla-crystal`, `glowingvein`, and the ores
`ore-dytrix`, `ore-siradamite`, `ore-stellar-steel` and `ore-urbium`. In the game they appear with
the `exogenesisold-` prefix.

Every structural barrier (rim, ridges, cone, mesas, dune wall, lakes, rivers) uses **vanilla
blocks only**, so the choke points still work if the map is opened without the mod. In that case
mod floors become stone, and mod ores and boulders disappear.

---

## 8. Regenerating or changing the map

Everything runs on the Python standard library (3.8+), so there is nothing to install.

```bash
python generate_map.py                                  # default seed 1597, writes to the maps folder
python generate_map.py --seed 42 --out "D:\some\folder"  # a different variation
python check_map.py                                     # checks maps\Biomes Extended Remastered.msav
```

One run takes about 30–60 s and writes four files: the `.msav`, a preview PNG, an enemy-routes PNG
and a JSON report with every measured number used in this document.

| File | What to change there |
|---|---|
| `generate_map.py` | Spawns, gates, ridges and passes, feature positions (`SPAWNS`, `GATES`, `RIDGES`, `FORDS`, ...), ore patches per biome (`ORE_SPECS`: count, distance range, radius range) and their spacing (`DEPOSIT_GAP`, `SAME_ORE_GAP`), outposts (`OUTPOSTS`), map author/name |
| `waves.py` | Every spawn group, wave timer, loadout, unit cap |
| `msav.py` | The save-format writer and validator (no need to touch) |
| `check_map.py` | Re-reads a map and runs the barrier tests |
| `audit_names.py` | Checks every block/unit/item name against the game and mod sources on GitHub (needs internet) |
| `CLAUDE.md` | Maintenance notes: pipeline, invariants, what to re-check when the game updates |

### Technical notes

- The file follows `SaveVersion` for **save format 13**: zlib-compressed `MSAV` header followed by
  the meta, patches, content, map, entities, markers and custom regions. Each region carries an int
  length. `check_map.py` re-reads every region with the same length checks the game uses.
- The map tags include `"genfilters": "[]"`. Without it, the game applies its default ore and
  decoration filters when the map loads, and would scatter random ores over the designed layout.
- The core is written as a team-1 (Sharded) `core-foundation` building with the exact building
  data layout of v159.7 (`Building.writeBase` version 3 plus `CoreBuild` revision 1).
- The first 34 entries of the block table copy the game's runtime block ids. That way, an unknown
  floor (for example when the mod is missing) falls back to stone instead of a random block.
- Mod blocks are stored under their in-game names (`exogenesisold-pyromagma`, ...), because the game
  does not add the mod prefix by itself.
- Name audit: all 102 block names, all 82 wave unit types (62 from Exogenesis Old), the `boss`
  effect and the loadout items were checked against v159.7's `Blocks`, `UnitTypes`,
  `StatusEffects` and `Items` and against the mod's `content/` folder. All five pinned spawn
  positions sit on spawn tiles.
- **Not tested in the game itself.** No game client was run during generation. Validation mirrors
  the game's own reader, but please open the map once in the editor to confirm it loads.

### Sources

- Mindustry source code at release **v159.7**: `SaveIO`, `SaveVersion`, `Save13`,
  `SaveFileReader`, `MapIO`, `Maps`, `BuildingComp`, `CoreBlock`, `Rules`, `SpawnGroup`,
  `WaveSpawner`, `Pathfinder`, `Blocks`, `UnitTypes` and `Items`.
  <https://github.com/Anuken/Mindustry/tree/v159.7>
- Release list (v8 Build 159.7, 19 Jul 2026): <https://github.com/Anuken/Mindustry/releases/tag/v159.7>
- Arc library (JSON/UBJSON) at commit `208a754044`, the version pinned by v159.7:
  <https://github.com/Anuken/Arc>
- Exogenesis Old by AureusStratus. From `mod.json`: name `exogenesisold`, version 1.9.1,
  minGameVersion 158. Unit and terrain definitions are in `content/`.
  <https://github.com/AureusStratus/ExoGenesis>
