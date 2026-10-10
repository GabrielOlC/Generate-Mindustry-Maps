# 📏 Naming Conventions & Patterns: Project Updates

This file holds the additions to the Coding-Conventions-Patterns standards (`READme.md`) made for this project. It extends them and changes nothing there. Each section follows the shape of its neighbours in `READme.md`, so it can be merged there unchanged.

**Note: New code follows these rules. Existing code keeps its names until it is rewritten for another reason.**

* * *

## Python Specifics

**Python keeps the universal and default tokens unchanged. Only the casing of the descriptive part is decided here: PascalCase, as in every other language, so one CTRL-F finds a name in Python, VBA, SQL or M alike.**

### 🔹Components & Constructs

* `fn` → **Functions:** `def` that returns a value. **e.g.:** `fnWaveCurve`
* `cl` → **Class:** Class definitions. **e.g.:** `clGroup`
* `_` → **Auxiliary Elements:** Module-private helpers; Python already marks them with a leading `_`. **e.g.:** `_fnPackPoint`
* `vs` → **Procedures:** `def` that returns nothing, as VBA's Sub. **e.g.:** `vsRenderPreview`
* `wf_` / `cm_` / `sys_` → **Modules:** The layer token from `Architecture_Principles.md` (controller, service, core) in front of the snake_case file name. A folder of interchangeable plugins keeps plain names. **e.g.:** `wf_generate.py`, `cm_pipeline.py`, `sys_config.py`, `layouts/biomes_confluence.py`

### 🔹Variables

* `v` → **Variable(Standard):** int, float, str, bool. **e.g.:** `vTotalHP`
* `s` → **Set (Objects):** Instances of a class. Python has no `Set` keyword, and its `set` type is an `ar`, not an `s`. **e.g.:** `sGroup`
* `c` → **Constant:** Module-level constant. Alone for a basic value, stacked on the type token for a collection, as in `ctbID`. **e.g.:** `cShieldGrowth`, `cdtNavalSwap`
* `ar` → **Array:** list, tuple or set. **e.g.:** `arWaves`
* `dt` → **Dictionary:** dict. **e.g.:** `dtCounts`
* Attributes on `self` and on a class take the same tokens. **e.g.:** `self.arFloor`, `cKey`

### 🔹Kept from Python

* File and module names stay snake_case, because they are import names. **e.g.:** `waves.py`
* `self`, `__init__` and the other dunder names, and keyword arguments of an existing API, are unchanged.
