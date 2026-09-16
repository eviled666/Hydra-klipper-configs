# TESTING — verifying the SexPistols safety fixes

These fixes were implemented and regression-tested **offline only** (Jinja render +
mocked status; rendered G-code is never executed — see `tests/`). Offline rendering
**cannot prove hardware behaviour**. A fresh Klipper load and the attended checks
below are the deployment owner's responsibility.

**Global prerequisites & stop conditions**

* Physical **E-stop within reach**; be ready to hit it.
* **Clear bed**, no print in progress, correct tool physically secured in its dock.
* If any step behaves unexpectedly (unexpected motion direction, a descending Z move,
  a heater staying on, a crash-detector shutdown), **STOP**, power down if needed, and
  roll back per `RECOVERY.md`.
* **Never** run the retired `UNSAFE_LOWER_BED` / `UNSAFE_RAISE_BED` (they now error by
  design) and never force unhomed motion to "recover".

Run the checks in order. Do not proceed to a later phase until the earlier one passes.

---

## Phase 0 — Offline regression tests (no printer)

```
cd tests
../.venv/bin/python -m unittest test_safety_fixes -v
```

Expected: **41 tests OK**. (If the venv is absent: `uv venv .venv && uv pip install
--python .venv/bin/python jinja2`.)

## Phase 1 — Config load / restart (no heat, no motion)

1. Deploy the config and **RESTART** (or `FIRMWARE_RESTART`).
2. Expected: Klipper reaches **ready** with no config errors. In particular confirm
   the new/overridden objects loaded:
   * `[input_shaper]` present; `SET_INPUT_SHAPER` is now a known command.
   * `RESUME`, `CALIBRATE_ALL_OFFSETS`, `TOOL_ALIGN_TEST`, `SAFE_SYNC_MOTORS`,
     `INCREASE_Z_CLEARANCE`, `APPLY_AND_SAVE_NEW_CALIBRATION_OFFSETS` are registered.
3. Stop condition: any "Option ... is not valid", "Unable to parse", or duplicate
   command-rename error → do not proceed; roll back.

## Phase 2 — No-heat, no-motion command checks

Run each and read the response only (these must not move the toolhead or heat):

* `UNSAFE_LOWER_BED` and `UNSAFE_RAISE_BED` → **expected: an error** telling you to use
  `INCREASE_Z_CLEARANCE` / `G28`. No motion.
* `APPLY_AND_SAVE_NEW_CALIBRATION_OFFSETS` before any calibration → **expected: error**
  ("No recorded calibration result").
* `INCREASE_Z_CLEARANCE MM=10` while **unhomed** → **expected: error** ("requires a
  homed Z"). No motion.
* `INCREASE_Z_CLEARANCE MM=0` and `MM=51` → **expected: error** (bounds).
* `CALIBRATE_ALL_OFFSETS` while **unhomed** → **expected: error** ("home all axes
  first"). No motion.
* `SAFE_SYNC_MOTORS` while unhomed / with a non-T0 tool active → **expected: error**.

## Phase 3 — Controlled, attended motion (homed, bed clear, hand on E-stop)

1. `G28` — confirm normal homing (behaviour is unchanged; the readonly toolchanger
   homing override is still authoritative). Watch that homing rebound/coordinates are
   as before.
2. `INCREASE_Z_CLEARANCE MM=10` — Z should rise ~10 mm (upward only), clamped near the
   top of travel; no descent.
3. **PRINT_END trajectory** (the key fix). With the toolhead parked mid-bed at a few Z
   heights, run `PRINT_END` and watch Z:
   * From a **low** Z (e.g. Z50): a single upward lift toward the top, then lateral
     travel to the dock X / safe Y. **No descending Z at any point.**
   * From a **high** Z (e.g. Z259, Z278, Z280): the lift target never goes **below**
     the current Z and never above the ceiling; then lateral travel. **No descent.**
   * From an **unhomed** state: `PRINT_END` turns heaters off and **skips** the park
     with an info message (no motion).
   * With **no tool selected** (`UNSELECT_TOOL` first): `PRINT_END` still turns heaters
     off, lifts, and **skips the lateral park** — it must **not** raise an error.
   Stop condition: any downward Z move, or a diagonal that lowers toward the bed/an
   object.
4. `TOOL_ALIGN_TEST` near a real dock (positive dock Y): **expected: accepted** and it
   proceeds to `TEST_TOOL_DOCKING`. Far from the dock (>30 mm): **expected: aborted**.
   Dock coordinates are not modified by this test.

## Phase 4 — Thermal / calibration (attended)

1. `SAFE_SYNC_MOTORS` with **T0 mounted/detected** and homed → proceeds
   (`VERIFY_TOOL_DETECTED` then `SYNC_MOTORS`). With T0 not detected → aborts.
2. **Per-tool offset calibration** (`CALIBRATE_ALL_OFFSETS`):
   * Confirm the **first tool (T0)** heater actually heats and the wait is on **T0's**
     extruder — not the previously-active tool (fix 2.1). Watch the console: the
     `TEMPERATURE_WAIT SENSOR=` must name the active tool's extruder.
   * Confirm each tool's result is **staged to its own section** (fix 2.3): after the
     run, inspect the pending `SAVE_CONFIG` diff — each `[tool Tn] gcode_*_offset`
     should hold **that tool's** measured value. A T4 measurement must **not** land on
     `[tool T0]`.
   * `SAVE_CONFIG` is an **explicit** step you run yourself when the offsets look
     correct; the macros never auto-restart.
3. **Single-tool apply** (`APPLY_AND_SAVE_NEW_CALIBRATION_OFFSETS`): run
   `TOOL_CALIBRATE_TOOL_OFFSET` on the **active** tool, then apply. Verify:
   * A **sensor-location** result (`TOOL_LOCATE_SENSOR` only) is **refused**.
   * A result whose tool ≠ the active tool is **refused**.
   * A valid, fresh, matching result applies live (`SET_GCODE_OFFSET`) and stages to
     the correct `[tool Tn]` section for `SAVE_CONFIG`.
4. **Input shaping**: after a toolchange, confirm the shaper is set with the tool's
   **type + frequency + damping** (e.g. `SET_INPUT_SHAPER SHAPER_TYPE_X=mzv
   SHAPER_FREQ_X=62.4 DAMPING_RATIO_X=0.01 ...`). These are the **existing configured**
   values (mzv / 62.4 / 88.6 / 0.01); you must **validate real resonance measurements**
   before trusting them for print quality.

## Phase 5 — Print-level (attended first print)

1. `PRINT_START` with realistic params. Confirm the intended sequence:
   * `M191`/`G4 S500` are gone; bed heats; nozzle preheats to 150.
   * The **soak happens BEFORE** `QUAD_GANTRY_LEVEL` / `G28 Z` / `BEACON_AUTO_CALIBRATE`
     (leveling references are established at temperature — fix 2.4).
   * KAMP purge (`VORON_PURGE`) still runs; `max_extrude_cross_section` unchanged.
   * `START_TOOL_CRASH_DETECTION` enables the new detector.
2. **PAUSE / RESUME** mid-print: PAUSE retracts and parks; `RESUME` must
   **reheat/unretract** (full Mainsail recovery restored) **and** verify the tool
   before resuming. If the tool is not detected, `RESUME` must **abort before**
   restoring position (no `RESUME_BASE`).
3. Finish with `PRINT_END` and confirm the safe park (Phase 3.3) at the real print
   height.

## Deferred / still-unproven (see review §5 and RECOVERY.md)

The following were **not** changed (not confirmed faults) and remain validation work,
not proven failures — do not "fix" them without hardware data:

* Crash-detector `UNSELECT_TOOL` / late-edge lifecycle timing (review 3): the new
  detector is intentionally left enabled; the legacy inert wrappers were only cleaned
  up. Watch for any nuisance shutdown around unselect/homing during Phase 5 and report.
* Controller fan cooling values, extruder sense-resistor (0.11 vs 0.100),
  interpolation policy, homing Y-rebound / travel geometry, toolchange corridor, rear
  QGL coverage, Moonraker `trusted_clients` scope. All are hardware/environment
  dependent and left documented, not guessed.
