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
python generate_map.py   # ~30-60 s; writes .msav, preview PNG, enemy-routes PNG, report JSON
python check_map.py      # re-decodes the map and runs the 5 barrier tests; must print "All checks passed."
python audit_names.py    # needs internet; checks every block/unit/item name against the game + mod
```
After that, look at the preview and routes PNGs. Update the numbers in `README.md` from the
`... - report.json` if resources or waves changed, and copy the two PNGs into `docs/`.

## Files

| File | Role |
|---|---|
| `generate_map.py` | Terrain pipeline (`MapBuilder`), statistics, preview rendering, `main()` writes everything |
| `waves.py` | All spawn groups (`build_groups`) and the rules JSON (`build_rules`: timer, loadout, unit cap) |
| `msav.py` | Save-format-13 writer plus a validator that mirrors the game's reader |
| `check_map.py` | Barrier tests on a generated map |
| `audit_names.py` | Content-name audit against GitHub sources (game tag configurable with `--tag`) |

## Pipeline order (`main()` in generate_map.py), which matters

noise → polar grid → biomes → floors → volcano/forest/frozen/semi-arid/desert features (liquids,
special floors) → keep-clear zones → natural walls → structural walls (mesa arc, dune wall, volcano
cone, separator ridges, central rim, map border) → outpost pads → spawns + core plaza → ore patches
→ decorations → connectivity (carves a path only if a spawn cannot reach the core).

`self.prot` tile codes: 0 = free, 1 = liquid/bank feature (no random walls or ores),
2 = forced open (passes, bridges, fords, pads; no walls or ores), 3 = structural wall.
`CB` is the biome by sector, used for features and statistics. `BI` is the dithered biome, used for
floors.

## Invariants (don't break these)

- **Barriers must stay sealed.** Each biome's enemy side reaches the core side only through its
  named choke points. `check_map.py` proves this. Its tests use **hard-coded start/goal
  coordinates and marker names**, so update them if you move spawns, outposts or features.
- **Structural barriers use vanilla blocks only**, so the layout still holds if the mod is missing.
  See `structural()`.
- **Mod content must carry the `exogenesisold-` prefix in the file.** Blocks get it via
  `file_block_name()` / `MOD_BLOCKS`; units via `EXO` in `waves.py`. The game does no prefixing,
  and unknown names silently become air/stone (blocks) or dagger (units).
- The map tags must contain **`"genfilters": "[]"`**. Otherwise the game scatters default ores on load.
- The first 34 entries of the block table copy the game's runtime ids (`msav.RUNTIME_BLOCK_PREFIX`).
  Don't reorder them.
- The core is the only building. Its data layout (`msav.core_chunk`) is version-specific.
- Rules JSON must stay under 65,535 bytes (Java `writeUTF`). It is about 10 KB now.
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

Then run `python audit_names.py --tag <new tag>`.

The game itself was never run during development. All validation mirrors the game's reader. Ask
the owner to open the map in the in-game editor after format-level changes.
