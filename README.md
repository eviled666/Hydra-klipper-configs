# Hydra-klipper-configs

## Verified safety fixes (branch `fix/verified-printer-safety`)

Confirmed Klipper software fixes from the completed reviews are layered as
**user-owned overrides** on top of the read-only symlinked dependencies:

* `user-overrides.cfg` — included **last** from `printer.cfg`; carries the restored
  Mainsail `RESUME` + tool verification, provenance-tracked tool-offset calibration,
  the `[input_shaper]` section + per-tool callback, `TOOL_ALIGN_TEST` dock tolerance,
  and `SAFE_SYNC_MOTORS`.
* `macros.cfg` — robust `PRINT_END`/`_PRINT_END_PARK`, the retired `UNSAFE_*` macros +
  the safe `INCREASE_Z_CLEARANCE`, the reordered `PRINT_START`, and the `TEST_SPEED`
  parameter fix.
* `homing.cfg` — removed the superseded local homing override (behaviour unchanged).

See **`TESTING.md`** for the ordered no-heat → attended-motion → thermal → print
verification checks, and **`RECOVERY.md`** for the dependency manifest, symlink notes
and rollback instructions.

Offline regression tests live in `tests/` (Jinja render of the merged config;
rendered G-code is never executed):

```
uv venv .venv && uv pip install --python .venv/bin/python jinja2   # first time only
cd tests && ../.venv/bin/python -m unittest test_safety_fixes -v
```
