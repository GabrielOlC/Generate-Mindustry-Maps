# Handoff notes for an AI assistant (or developer) maintaining this map generator

Read `README.md` first for the map designs (biomes, resources, choke points, waves),
`docs/Biomes_Confluence.md` for the naval map and `docs/Biomes_Warfront.md` for the PvP map. This file
covers how the code works and what must not break.

## What this is

A stdlib-only Python framework that writes Mindustry maps straight to the game's binary `.msav`
format. There is no game engine involved. It has three map types (layouts) that share everything else:
- `biomes-extended`: **"Biomes Extended Remastered"**, the original map (PvE, no naval routes).
- `biomes-confluence`: **"Biomes Confluence"**, PvE: five biome lanes around a harbour core. Boats sail
  two rivers, Greenwater (water) and Rimeflow (cryofluid), to the lagoon beside the core.
- `biomes-warfront`: **"Biomes Warfront"**, PvP for 5: one walled base per biome sector, waves from the
  Rift in the middle (RTS AI), defender bots for empty slots (a world processor), every floor resource
  in every base (one home biome each, 3x3 pockets elsewhere).

Targets and owner preferences:
- Target game: **Mindustry v8 Build 159.7** (save format **13**).
- Target mod: **Exogenesis Old** (`exogenesisold` 1.9.1, https://github.com/AureusStratus/ExoGenesis).
- Owner preferences: **don't install anything**. Keep it standard library only and keep `requirements.txt`.
  Generated maps go to the `maps` folder next to the scripts. That is the default `--out`
  (`sys_config.cDefaultOut`, built from the script's own location). Keep every default path relative to
  the project folder; no machine-specific paths.
- **Naming in new code** follows the owner's notation (the Coding-Conventions-Patterns skill) with the
  Python rules in `docs/Coding_Conventions_Updates.md`. That means token + PascalCase (`cdtNavalSwap`,
  `fnBuild`, `vsSeal`), and module files carry their layer token (`wf_`, `cm_`, `sys_`). Existing names
  change only when that code is rewritten anyway. New rules go into that file, never into the skill's
  own files.
- `generate_map.py`, `check_map.py` and `audit_names.py` are the original scripts and keep working.
  `generate_map.py` only binds its shared constants to `sys_config`/`cm_render`. Its terrain code
  (`MapBuilder`) is the original layout. Don't rewrite it: the `biomes-extended` adapter runs it step by
  step.

## Workflow after any change

```
python wf_generate.py                        # asks for the map type, then the difficulty (Enter = hardest)
python wf_generate.py --map biomes-confluence --ore-rolls 5            # no --difficulty = the hardest
python wf_generate.py --map biomes-extended --difficulty normal --ore-rolls 5
python wf_generate.py --map biomes-warfront --ore-rolls 5
python audit_names.py "maps\<map name>.msav" # needs internet; every block/unit/item/filter/patch name
                                             # (and, on the PvP map, the world processor's code)
```
- **What a run does:** each run takes ~1-2 min (+20-50 s per extra ore roll). It writes the .msav, a
  preview PNG, an enemy-routes PNG and a report JSON, then runs the map's checks. It must end with "All
  checks passed." (the exit code is 0 only then). The original map's checks are `check_map.main`; every
  other map type uses `cm_checks.fnCheckMap`. `python generate_map.py` + `python check_map.py` still
  produce and check the original map. Both paths write the same file (verified: decoded map, both PNGs
  and the report are identical).
- **After that:** look at the preview and routes PNGs. Update the numbers in `README.md` /
  `docs/Biomes_Confluence.md` / `docs/Biomes_Warfront.md` from the `... - report.json` if resources or
  waves changed, and copy the PNGs into `docs/` (the PvP map writes `... - routes.png` instead of
  `... - enemy routes.png`). The documented ore numbers are averages of 5 simulated rolls, so regenerate with
  `--ore-rolls 5` before copying them (roll 1, and so the preview, is the same with any roll count).

## Files

| File | Layer | Role |
|---|---|---|
| `wf_generate.py` | controller | Lists the map types found in `layouts/` and the difficulty levels, asks for both (or `--map`, `--difficulty`; no difficulty = the hardest), routes them to the pipeline |
| `sys_config.py` | core | Common configuration layer: mod prefix and blocks, liquid/deep/lava floors, floor heat, data patches, floor-to-wall palette, preview colours, match rules, **difficulty levels** (`cdtDifficulties`, `fnMapName`), pad/plaza floor conventions, **PvP** teams, rules, wave team and defender bots (`cdtPvpTeams`, `cdtPvpRules`, `cdtPvpWaveTeamRules`, `cdtBotRules`, `cBotKeep`) |
| `cm_layout.py` | service | The layout contract (`clLayout`, `clLayoutResult`, incl. the PvP fields `sMatch`, `arTeamCores`, `arNavalLinks`, `dtResourceRules`) and `fnFindLayouts` (plugin discovery) |
| `cm_pipeline.py` | service | Shared pipeline for any layout: ore rolls, statistics, ground and naval routes, rules, `.msav` + re-decode, PNGs, report, checks. PvP: one core per team, the bots' world processor, base-to-base distances |
| `cm_bot.py` | service | The defender bots' world-processor program (`fnBuildProgram`) and a static check that mirrors the game's logic parser (`fnCheckProgram`) |
| `cm_terrain.py` | service | Size-independent terrain toolkit (`clGrid`): noise, discs, polylines/rivers, BFS, the naval flow field port, `fnAllDeep`, `vsSealDeepWalls` |
| `cm_render.py` | service | PNG writer, preview and routes images |
| `cm_checks.py` | service | Shared verification of a written map (see Invariants) |
| `layouts/biomes_extended.py` | plugin | Adapter running `generate_map.MapBuilder` unchanged; its check is `check_map.main` |
| `layouts/biomes_confluence.py` | plugin | The naval map (`clConfluenceTerrain`) |
| `layouts/biomes_warfront.py` | plugin | The PvP map (`clWarfrontTerrain`) |
| `ores.py` | shared | In-game ore filters (`build_filters`, `check_filters`, `to_json`) and a port of the game's Simplex noise + OreFilter/NoiseFilter to simulate rolls (`roll`, `measure`) |
| `waves.py` | shared | All spawn groups (`build_groups`). `fnExpandGroups` fits them to a map (naval swap or naval pins), `fnBuildRules` builds the rules JSON, plus the wave statistics |
| `msav.py` | shared | Save-format-13 writer (incl. embedded data patches and world processors, `fnLogicChunk`) plus a validator that mirrors the game's reader (it decodes processor code too) |
| `generate_map.py`, `check_map.py` | original | The original map's terrain (`MapBuilder`) and its own entry point / barrier tests |
| `audit_names.py` | tool | Content-name audit against GitHub sources (game tag configurable with `--tag`) |

## Adding a map type

1. Create `layouts/<name>.py` with a subclass of `cm_layout.clLayout`, setting `cKey`, `cName`,
   `cSummary`, `cDefaultSeed` and `cOrder`. Its `fnBuild(vSeed)` returns a `clLayoutResult` (fields
   documented in `cm_layout.py`). Nothing else changes: the controller finds it, and the pipeline,
   ores, waves, rules and checks come for free.
2. Paint outpost pads and the core plaza with `sys_config.cPadFloor`/`cPadRingFloor` and
   `cPlazaFloor`/`cPlazaBorderFloor` (the ore filters keep exactly these clear). Write only `spawn` marks
   as overlays. Use `cm_terrain.clGrid` for geometry.
3. Use the shared wave groups' spawn keys (only `desert` is pinned today), or map them with
   `dtSpawnAliases`. Spawns on water go in `arNavalSpawnKeys`; every naval group is then pinned to each of
   them.
4. Give `arBarrierTests` for every choke point that must seal something. If the map has water barriers,
   call `clGrid.vsSealDeepWalls` after the last wall is placed.
5. A PvP map sets `sMatch="pvp"` and gives `arTeamCores` (one per player slot of
   `sys_config.cdtPvpTeams`, each with a clear square of `sys_config.cBotKeep` for a bot fortress),
   optionally `arNavalLinks` (boat raids that must arrive) and `dtResourceRules` (which biome is home to
   which floor resource). The pipeline then adds the PvP rules, the cores and the bots' world processor;
   the checks test all of it.

## Terrain order, which matters

- **biomes-extended** (`main()` in generate_map.py and the adapter): noise → polar grid → biomes →
  floors → volcano/forest/frozen/semi-arid/desert features → keep-clear zones → natural walls →
  structural walls (mesa arc, dune wall, volcano cone, separator ridges, central rim, map border) →
  outpost pads → spawns + core plaza → decorations → connectivity (carves a path only if a spawn cannot
  reach the core).
- **biomes-confluence**: noise → polar grid → floors → rivers → lagoon + inlet + harbour pools → fords →
  volcano/frozen/semi-arid/desert/forest features → keep-clear → natural walls → ridges → Harbour Wall
  → biome barriers → crater → map border → pads → spawns + plaza → decorations → connectivity (cuts
  natural walls only, never structural walls or liquids) → **seal** (`vsSealDeepWalls`, last).
- **biomes-warfront**: noise → polar grid → roads (spawn → Rift gate, kept clear) → floors (palettes with
  no foreign resource floor) → rivers → lagoon + harbours → Rift fords → volcano/frozen/desert/forest
  features (liquids outside the bases, off the ridges and roads) → keep-clear → natural walls (none inside
  ramparts) → ridges with flank passes → ramparts with gates and sluices → map border → pads → resource
  gardens → spawns + plazas + fortress squares → decorations → connectivity → **seal** (last).
- The pipeline then simulates the in-game ore filters on the finished terrain for the preview and the
  report (never written to the map).

`prot` tile codes (both layouts):
- 0 = free;
- 1 = liquid/bank feature (no random walls);
- 2 = forced open (passes, bridges, fords, pads; no walls);
- 3 = structural wall.

They do not affect the in-game ore filters, which may put ore anywhere on open ground except the
floors in `ores.CLEAR_FLOORS`. `CB` is the biome by (warped) sector, used for features and statistics.

## Invariants (don't break these)

**Barriers**
- **Barriers must stay sealed.** Each biome's enemy side reaches the core side only through its
  named choke points.
  - `check_map.py` proves this for the original map.
  - `cm_checks` proves it for the naval map with whole-map tests: with a lane's passes closed its
    spawn cannot reach the core, and with its gate closed the land behind the passes cannot.
  - Both use **hard-coded coordinates and marker names**, so update them if you move spawns or features.
- **The game's ground rule is `allDeep`, not "deep":**
  - `Pathfinder.costGround` blocks a tile only if it is solid or allDeep (the tile and all 8 neighbours
    have deep floors). A deep tile at a bank merely costs 6000.
  - `cm_checks` tests barriers under that rule. So a river or lava band crossing a wall line must carry
    its liquid under the adjacent walls (`vsSealDeepWalls`), and liquid barriers need 3+ deep tiles of
    width.
  - Without the seal step all four river crossings of the naval map leak (tested).
  - The original map also passes the strict rule (checked once, for information).
- **Structural barriers use vanilla blocks only**, so the layout still holds if the mod is missing.
  See `structural()` / `fnStructural()`.

**Naval**
- **Naval rules** (Pathfinder, WaveSpawner, UnitComp @ v159.7):
  - A boat on a non-liquid floor dies at once, and spawn tiles do not filter by unit type.
  - So naval groups must only ever be pinned to naval spawns (`waves.fnExpandGroups`; `cm_checks`
    fails otherwise). Maps without naval spawns get the land stand-ins from `waves.cdtNavalSwap`.
  - **Every naval unit used in the groups needs an entry in `cdtNavalSwap`**, or it would spawn
    everywhere and die.
- **Harbour spawns**: every tile within 2.5 of a naval spawn must be liquid (boats survive) and not deep
  (ground units spawned there don't drown). `cm_checks` tests this.
- **Boats reach the core**:
  - The naval flow field (`costNaval`) never blocks. Land costs 7000/tile and boats only step on water,
    so they stop at the water closest to the core.
  - `cm_checks` ports the field and requires the resting tile within 12 tiles of the core.
  - It is 9.5 tiles on Biomes Confluence, where the inlet touches the plaza. The shortest-ranged boat,
    risso, fires from about 19 tiles (GroundAI: `range / 1.3 + 16`).

**Map content**
- **Mod content must carry the `exogenesisold-` prefix in the file.** Blocks get it via
  `sys_config.fnFileBlockName()` / `carModBlocks` (also inside the filter JSON); units via `EXO` in
  `waves.py`. The game does no prefixing, and unknown names silently become air/stone (blocks) or dagger
  (units).
- **Ores are rolled by the game, not baked.** The `genfilters` tag holds the explicit filter list
  from `ores.build_filters`; `World.FilterContext` gives every filter a new random seed on each map
  load. Never write ore overlays into the map (only `spawn`), or they would repeat every game, and never
  leave `genfilters` empty: an empty tag makes the game scatter its own default ores and boulders.
  Siratla crystal (a floor) is rolled the same way by NoiseFilters.
- **Filter order and targets must survive a missing mod** (`ores.check_filters`, run by the pipeline
  and the checks):
  - Without the mod every mod name in the JSON reads as `air`. A mod-ore filter then erases ore, so all
    mod filters come before the first vanilla ore filter.
  - A vanilla filter must never target a mod floor (its target would become "everywhere").
  - NoiseFilters must set `block` to `air` (the default is stone-wall) and always have a floor target,
    or they would repaint lava, water and walls and break the barriers.
- **Thermal generators on lava** come from the embedded data patches in `sys_config.carDataPatches`:
  - `thermal-generator.placeableLiquid = true`. The block is already `floating`, but
    `Build.contactsShallows` kept it on the banks of the molten slag.
  - Heat for Exogenesis' `pyromagma`, which defines none, so `ThermalGenerator.canPlaceOn` (heat > 0)
    rejected the creeks.
  - Any new lava-looking floor needs heat too: add it to `carLavaFloors`, and the checks will test
    every 2×2 spot on it.
  - Keep patches on mod content in their own asset with a dotted path, so a missing mod only produces
    a warning.

**Difficulty**
- **The levels are the game's own** (`Difficulty.java` @ v159.7: enemy health, enemy spawn and wave
  time multipliers), ordered easiest to hardest in `sys_config.cdtDifficulties`.
  - The game applies them only in the campaign (`CampaignRules.apply`, `WaveSpawner`, `Logic`), so the
    map carries them itself.
  - Health: `"teams": {"2": {"unitHealthMultiplier": h}}` in the rules (crux, the wave team;
    `ShieldComp` divides damage by it).
  - Timer: `waveSpacing` and `initialWaveSpacing` × the wave time multiplier.
  - Units: `waves.fnApplyDifficulty` gives each group amount and cap × the multiplier and growth that
    many times faster, with the campaign's rounding (bosses rounded down, never below 1). Over waves
    1–310 that stays within 4% of the campaign rule.
- **Normal must stay the identity:** normal output is the waves as designed. The framework at
  `--difficulty normal` writes the same file as `generate_map.py` (verified: decoded map, PNGs and report).
- **No difficulty means the hardest:** `sys_config.cDefaultDifficulty` is the last level in
  `cdtDifficulties`, so a harder level added at the end becomes the default.
- **Each level has its own map name and files:** "Name (Level)" (`fnMapName`); Normal keeps the plain
  name. A non-normal map's description ends with the game-style difficulty line (`fnDifficultyNote`).
  The terrain never depends on the difficulty.

**PvP (biomes-warfront)**
- **No team is AI in PvP** (`Team.isAI()` is false when `rules.pvp`), so units of every team get
  `CommandAI` and stand still unless commanded. The base-builder AI is off in PvP (`Logic`: `buildAi &&
  !pvp`), and `setrule` cannot switch `rtsAi`, `buildAi` or `cheat`. Hence:
  - **Waves** come from a sixth team, neoplastic (`sys_config.cPvpWaveTeam` = 6), with `rtsAi` on
    (`cdtPvpWaveTeamRules`). The RTS AI runs in PvP and sends each idle squad at an easy target among all
    players' cores, drills, generators, factories and batteries. `rtsMinWeight` 0 = attack at once.
    `airUseSpawns` is on, so flyers rise from the Rift spawns too (`WaveSpawner.eachFlyerSpawn` otherwise
    puts them on the map edge in the spawn's direction, which here is behind the bases).
  - **Defender bots** are a world processor (privileged, team 6: derelict buildings never update). It
    waits `cdtBotRules["joinWindow"]` s, then for every team with a core and no player: `setrule`
    multipliers, `setblock` turrets + wall ring, `setprop` ammo, `spawn` guards; it reloads them every
    `refresh` s and gives a team back its normal multipliers when a player joins it.
- **The map's rules must say `pvp: true` and `attackMode: true`** (`cdtPvpRules`). Map rules override the
  gamemode's, and without attack mode `Logic.checkGameState` ends the game when team 1 (sharded) loses its
  core, instead of when one team is left.
- **The processor program must parse**: only statements, enum values and field counts that
  `cm_bot.fnCheckProgram` knows (v159.7 `LStatements` field order), at most 1000 instructions
  (`LExecutor.maxInstructions`) and 500 labels; the checks and the name audit run it. Logic has no arrays,
  so the five teams are unrolled; the code fetches unit counts before spawning (team data counts new units
  only on the next update, so a fetch right after a spawn would loop to the unit cap).
- **Fortress squares stay clear**: no solid wall and no liquid within `cBotKeep` (Chebyshev) of any core
  centre, or `setblock` would put turrets on water. The bot pattern (`cdtBotRules`) must fit inside it.
- **One home per resource**: every group of `sys_config.cdtResourceFloors` has one home biome
  (`cdtHomes` in the layout). Biome palettes never paint a foreign resource floor (e.g. no darksand banks
  or sand-water outside the forest/desert), and each base garden holds one 3x3 pocket of every foreign
  group. The checks count usable tiles per base (no solid wall on them): foreign 1..9, home 300+.
- Ridge tests are per pair of sectors (the test region is those two sectors, outside the Rift): closing one
  pass cannot cut two sectors apart while the ring of other passes is open.
- Naval links on the PvP map need only reach the other river base's harbour (`cHarbourReach` 40 tiles):
  the fortress square keeps water at least 24 tiles from a core.

**File format**
- The first 34 entries of the block table copy the game's runtime ids (`msav.RUNTIME_BLOCK_PREFIX`).
  Don't reorder them.
- The cores are the only buildings, plus one world processor on a PvP map. Their data layouts
  (`msav.core_chunk`, `msav.fnLogicChunk`) are version-specific.
- Rules JSON and the genfilters JSON must each stay under 65,535 bytes (Java `writeUTF`). They are
  about 12.5-15.3 KB (by map and difficulty) and 4.5 KB now.

**Accuracy notes**
- The preview/report ore numbers come from `ores.py`'s port of `arc.util.noise.Simplex` and the filter
  rules. It follows the game's arithmetic step by step (doubles, int32 hashing, the final float cast and
  comparison), so a simulated roll stands for a possible in-game roll; only the random seeds differ.
  The fast path in `ores.hits` was checked against the plain `noise2d` port. The port itself was
  never compared against a running game.
- Ground pathing uses 4-way steps, so many routes tie. Armies can split across gates and both river
  banks. This is expected, not a bug. Legged units may wade deep water at cost 6000/tile (they hover
  and don't drown), as on the original map; the passes stay far cheaper.

## If the game version changes

Compare these files at the new tag against v159.7:
- `core/src/mindustry/io/SaveVersion.java` and the newest `io/versions/SaveNN.java` (region order,
  map/tile encoding). Bump `msav.SAVE_VERSION` only if a new format is the latest writer.
- `entities/comp/BuildingComp.java` (`writeBase`) and `world/blocks/storage/CoreBlock.java`
  (`CoreBuild.version/write`), which define the core chunk.
- `content/Blocks.java` (order of the first blocks, environment block names, `isLiquid`/`drownTime` of
  the liquid floors), `game/Rules.java` (field names; `planet` "sun" is the rules dialog's "<Any>", see
  `ui/dialogs/CustomRulesDialog.java`) and `game/SpawnGroup.java` (wave JSON keys).
- Ore filters: `maps/filters/GenerateFilter.java` (noise call, `randomize`), `OreFilter.java` and
  `NoiseFilter.java` (fields and conditions), `core/World.java` (`FilterContext.applyFilters`),
  `io/JsonIO.java` (filter class tags, unknown blocks → `air`) and Arc's `util/noise/Simplex.java` at
  the `archash` in the game's `gradle.properties`.
- Data patch: `io/SaveVersion.java` (`readDataPatches`), `mod/data/DataAssetType.java` (patch ordinal),
  `mod/data/PatchAsset.java`, `mod/DataPatcher.java` (patch syntax), `world/Build.java`
  (`contactsShallows`, `placeableLiquid`), `world/blocks/power/ThermalGenerator.java` (`canPlaceOn`)
  and the heat values in `content/Blocks.java` (`cdtFloorHeat`). If the mod updates, check whether
  `content/blocks/environment/pyromagma.json` gained its own heat.
- Difficulty: `game/Difficulty.java` (multipliers), `game/CampaignRules.java` (what the campaign sets),
  `core/Logic.java` (wave timer), `ai/WaveSpawner.java` (spawn multiplier rounding),
  `entities/comp/ShieldComp.java` and `game/Rules.java` (`unitHealth`, `TeamRules` JSON).
- Naval and ground pathing: `ai/Pathfinder.java` (`costGround`, `costNaval`, `packTile`'s `allDeep`,
  `Flowfield.passable`), `ai/WaveSpawner.java` (where groups spawn), `entities/comp/UnitComp.java` and
  `WaterMoveComp.java` (boats on land), `entities/EntityCollisions.java` (`waterSolid`) and
  `ai/types/GroundAI.java` (when a unit targets the core).

- PvP and bots: `game/Team.java` (`isAI`), `core/Logic.java` (`checkGameState`, team AI update),
  `core/NetServer.java` (`assigner`), `game/Gamemode.java` (`pvp`), `io/MapIO.java` (teams with cores),
  `ai/RtsAI.java`, `ai/WaveSpawner.java` (`eachFlyerSpawn`, `airUseSpawns`), `game/Rules.java` (`TeamRule`), `world/blocks/logic/LogicBlock.java` (`LogicBuild.write/read`,
  `compress`, limits), `logic/LParser.java`, `logic/LStatements.java` (field order), `logic/LogicRule.java`,
  `logic/FetchType.java`, `logic/LExecutor.java` (`SetRuleI`, `SetBlockI`, `SpawnUnitI`, `FetchI`,
  `maxInstructions`), `entities/comp/BuildingComp.java` (`setProp`) and
  `world/blocks/defense/turrets/ItemTurret.java` (`acceptStack`, `handleStack`).

Then run `python audit_names.py --tag <new tag>`. It also checks that the filter fields and the patched
Block field still exist and that the game still re-rolls filter seeds on load.

The game itself was never run during development. All validation mirrors the game's reader and source.
Ask the owner to open the maps in the in-game editor after format-level changes, to watch one naval
wave on Biomes Confluence, and to host Biomes Warfront as PvP with fewer than 5 players once (empty slots
must turn into fortresses after the join window, and waves must leave the Rift).
