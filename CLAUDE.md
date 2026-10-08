# Handoff notes for an AI assistant (or developer) maintaining this map generator

Read `README.md` first for the map's design: biomes, resources, choke points and waves. This file
covers how the code works and what must not break.

## What this is

A stdlib-only Python generator that writes the Mindustry PvE map **"Biomes Extended Remastered"**
(800×800) straight to the game's binary `.msav` format. There is no game engine involved.
- Target game: **Mindustry v8 Build 159.7** (save format **13**).
- Target mod: **Exogenesis Old** (`exogenesisold` 1.9.1, https://github.com/AureusStratus/ExoGenesis).
- Owner preferences: **don't install anything**. Keep it standard library only and keep `requirements.txt`.
  Generated maps go to the `maps` folder next to the scripts. That is the default `--out`
  (`DEFAULT_OUT` in `generate_map.py`, built from the script's own location). Keep every default
  path relative to the project folder; no machine-specific paths.

## Workflow after any change

```
python generate_map.py   # ~1-2 min; writes .msav, preview PNG, enemy-routes PNG, report JSON
python check_map.py      # re-decodes the map, checks ore filters + data patch, runs the 5 barrier tests;
                         # must print "All checks passed."
python audit_names.py    # needs internet; checks every block/unit/item/filter/patch name against game + mod
```
After that, look at the preview and routes PNGs. Update the numbers in `README.md` from the
`... - report.json` if resources or waves changed, and copy the two PNGs into `docs/`. The README's ore
numbers are averages of 5 simulated rolls: regenerate with `python generate_map.py --ore-rolls 5` before
copying them (roll 1, and so the preview, is the same with any roll count).

## Files

| File | Role |
|---|---|
| `generate_map.py` | Terrain pipeline (`MapBuilder`), data patches, statistics, preview rendering, `main()` writes everything |
| `ores.py` | In-game ore filters (`build_filters`, `check_filters`, `to_json`) and a port of the game's Simplex noise + OreFilter/NoiseFilter to simulate rolls (`roll`, `measure`) |
| `waves.py` | All spawn groups (`build_groups`) and the rules JSON (`build_rules`: timer, loadout, unit cap) |
| `msav.py` | Save-format-13 writer (incl. embedded data patches) plus a validator that mirrors the game's reader |
| `check_map.py` | Barrier tests, ore-filter rules and data-patch check on a generated map |
| `audit_names.py` | Content-name audit against GitHub sources (game tag configurable with `--tag`) |

## Pipeline order (`main()` in generate_map.py), which matters

noise → polar grid → biomes → floors → volcano/forest/frozen/semi-arid/desert features (liquids,
special floors) → keep-clear zones → natural walls → structural walls (mesa arc, dune wall, volcano
cone, separator ridges, central rim, map border) → outpost pads → spawns + core plaza → decorations
→ connectivity (carves a path only if a spawn cannot reach the core) → ore roll preview (simulates the
in-game filters on the finished terrain for the preview PNG and the report; never written to the map).

`self.prot` tile codes: 0 = free, 1 = liquid/bank feature (no random walls),
2 = forced open (passes, bridges, fords, pads; no walls), 3 = structural wall. They do not affect the
in-game ore filters, which may put ore anywhere on open ground except the floors in `ores.CLEAR_FLOORS`.
`CB` is the biome by sector, used for features and statistics. `BI` is the dithered biome, used for
floors.

## Invariants (don't break these)

- **Barriers must stay sealed.** Each biome's enemy side reaches the core side only through its
  named choke points. `check_map.py` proves this. Its tests use **hard-coded start/goal
  coordinates and marker names**, so update them if you move spawns, outposts or features.
- **Structural barriers use vanilla blocks only**, so the layout still holds if the mod is missing.
  See `structural()`.
- **Mod content must carry the `exogenesisold-` prefix in the file.** Blocks get it via
  `file_block_name()` / `MOD_BLOCKS` (also inside the filter JSON); units via `EXO` in `waves.py`.
  The game does no prefixing, and unknown names silently become air/stone (blocks) or dagger (units).
- **Ores are rolled by the game, not baked.** The `genfilters` tag holds the explicit filter list
  from `ores.build_filters`; `World.FilterContext` gives every filter a new random seed on each map
  load. Never write ore overlays into the map (only `spawn`), or they would repeat every game, and never
  leave `genfilters` empty: an empty tag makes the game scatter its own default ores and boulders.
  Siratla crystal (a floor) is rolled the same way by NoiseFilters.
- **Filter order and targets must survive a missing mod** (`ores.check_filters`, run by the generator
  and `check_map.py`). Without the mod every mod name in the JSON reads as `air`: a mod-ore filter then
  erases ore, so all mod filters come before the first vanilla ore filter, and a vanilla filter must
  never target a mod floor (its target would become "everywhere"). NoiseFilters must set `block` to
  `air` (the default is stone-wall) and always have a floor target, or they would repaint lava, water
  and walls and break the barriers.
- **Thermal generators on lava** come from the embedded data patch `DATA_PATCHES`
  (`thermal-generator.placeableLiquid = true`; the block is already `floating`, but
  `Build.contactsShallows` kept it on the banks). Lava stays a barrier because the pathfinder's
  `allDeep` flag only looks at floors, so buildings on lava never open a ground route.
- The first 34 entries of the block table copy the game's runtime ids (`msav.RUNTIME_BLOCK_PREFIX`).
  Don't reorder them.
- The core is the only building. Its data layout (`msav.core_chunk`) is version-specific.
- Rules JSON and the genfilters JSON must each stay under 65,535 bytes (Java `writeUTF`). They are
  about 10 KB and 4.5 KB now.
- The preview/report ore numbers come from `ores.py`'s port of `arc.util.noise.Simplex` and the filter
  rules. It follows the game's arithmetic step by step (doubles, int32 hashing, the final float cast and
  comparison), so a simulated roll stands for a possible in-game roll; only the random seeds differ.
  The fast path in `ores.hits` was checked against the plain `noise2d` port. The port itself was
  never compared against a running game.
- Ground pathing uses 4-way steps, so many routes tie. The north-east and south-west armies can
  split across gates. This is expected, not a bug.

## If the game version changes

Compare these files at the new tag against v159.7:
- `core/src/mindustry/io/SaveVersion.java` and the newest `io/versions/SaveNN.java` (region order,
  map/tile encoding). Bump `msav.SAVE_VERSION` only if a new format is the latest writer.
- `entities/comp/BuildingComp.java` (`writeBase`) and `world/blocks/storage/CoreBlock.java`
  (`CoreBuild.version/write`), which define the core chunk.
- `content/Blocks.java` (order of the first blocks, environment block names), `game/Rules.java`
  (field names) and `game/SpawnGroup.java` (wave JSON keys).
- Ore filters: `maps/filters/GenerateFilter.java` (noise call, `randomize`), `OreFilter.java` and
  `NoiseFilter.java` (fields and conditions), `core/World.java` (`FilterContext.applyFilters`),
  `io/JsonIO.java` (filter class tags, unknown blocks → `air`) and Arc's `util/noise/Simplex.java` at
  the `archash` in the game's `gradle.properties`.
- Data patch: `io/SaveVersion.java` (`readDataPatches`), `mod/data/DataAssetType.java` (patch ordinal),
  `mod/data/PatchAsset.java`, `mod/DataPatcher.java` (patch syntax), `world/Build.java`
  (`contactsShallows`, `placeableLiquid`) and `world/blocks/power/ThermalGenerator.java` (`canPlaceOn`).

Then run `python audit_names.py --tag <new tag>`. It also checks that the filter fields and the patched
Block field still exist and that the game still re-rolls filter seeds on load.

The game itself was never run during development. All validation mirrors the game's reader. Ask
the owner to open the map in the in-game editor after format-level changes.
