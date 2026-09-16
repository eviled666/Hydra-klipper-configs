# SexPistols recovery & dependency manifest

This backup repository is **not a self-contained recovery image**. Several
configuration entries are symlinks whose *targets* live outside the repo, and the
committed git objects preserve the link **targets, not their contents** (mode
`120000`). Restoring onto a bare machine therefore also requires re-installing the
dependencies listed below and re-applying any local patches.

> This manifest records what the read-only review evidence establishes. Where a
> revision could not be verified from the evidence it is marked **UNKNOWN**; do not
> treat UNKNOWN as "pristine upstream". The parent (deployment owner) can capture
> exact dereferenced content and local patches; this repo does **not** yet claim to
> contain them.

## Host / core software (from review evidence `info.json`)

| Item | Value |
|------|-------|
| Host | SexPistols |
| Klipper | `v0.13.0-629-g6349d4fb0-dirty` (note the `-dirty` suffix: do not assume pristine upstream) |
| Config path | `/home/pi/printer_data/config/printer.cfg` |
| Klippy env | `/home/pi/klippy-env` |

## Symlinked dependencies (do NOT follow these links for writing)

| Repo path (symlink) | Target | Upstream project | Known revision |
|---------------------|--------|------------------|----------------|
| `KAMP` | `/home/pi/Klipper-Adaptive-Meshing-Purging/Configuration` | Klipper-Adaptive-Meshing-Purging | `b0dad8e` (local KAMP_Settings content changes) |
| `mainsail.cfg` | `/home/pi/mainsail-config/client.cfg` | mainsail-config | tracked at **ff3869a** (source of the RESUME/PAUSE body reproduced in `user-overrides.cfg`) |
| `toolchanger/readonly-configs/toolchanger.cfg` | `/home/pi/klipper-toolchanger-easy/examples/easy-additions/toolchanger.cfg` | klipper-toolchanger-easy | `08dc049` |
| `toolchanger/readonly-configs/toolchanger-macros.cfg` | `.../easy-additions/toolchanger-macros.cfg` | klipper-toolchanger-easy | `08dc049` |
| `toolchanger/readonly-configs/toolchanger-include.cfg` | `.../easy-additions/user-configs/toolchanger-include.cfg` | klipper-toolchanger-easy | `08dc049` |
| `toolchanger/readonly-configs/calibrate-offsets.cfg` | `.../easy-additions/calibrate-offsets.cfg` | klipper-toolchanger-easy | `08dc049` |
| `toolchanger/readonly-configs/crash-detection.cfg` | `.../easy-additions/crash-detection.cfg` | klipper-toolchanger-easy (legacy wrappers) | UNKNOWN |
| `toolchanger/readonly-configs/homing.cfg` | `.../easy-additions/homing.cfg` | klipper-toolchanger-easy | `08dc049` |
| `toolchanger/readonly-configs/tool_detection.cfg` | `.../easy-additions/tool_detection.cfg` | klipper-toolchanger-easy | `08dc049` |

## Klipper python extras (installed into `klipper/extras`, evidence dated 2025-12-04)

These are an **installed checkout copy** (`toolchanger-source/` in the review
evidence), not verified pristine upstream. Matching another live copy proves nothing
about the upstream revision.

| Module | Role | Revision |
|--------|------|----------|
| `toolchanger.py` | core toolchanger | UNKNOWN |
| `tools_calibrate.py` | `TOOL_LOCATE_SENSOR`, `TOOL_CALIBRATE_TOOL_OFFSET`, `TOOL_CALIBRATE_SAVE_TOOL_OFFSET` | UNKNOWN |
| `tool_crash.py` | new leave-on crash detector (`[tool_crash]`, `START/STOP_TOOL_CRASH_DETECTION`) | `(C) 2025 @Contomo and @cekim` — revision UNKNOWN |
| `tool.py`, `tool_probe.py`, `tool_probe_endstop.py`, `rounded_path.py`, `multi_fan.py`, `manual_rail.py`, `bed_thermal_adjust.py` | supporting modules | UNKNOWN |

## How the fixes are layered (no upstream edits)

All fixes are expressed as **user-owned overrides** merged on top of the read-only
dependencies — nothing under the symlink targets is edited:

* `printer.cfg` — adds a single `[include user-overrides.cfg]` as the **last**
  include before the `SAVE_CONFIG` block, plus unchanged tool offsets moved from
  T0..T4 includes to the root so SAVE_CONFIG can replace them without include conflicts.
* `user-overrides.cfg` — new user file; wins the Klipper same-section-key merge for
  `PAUSE`/`RESUME`, the calibration macros, `TOOL_ALIGN_TEST`, the `[toolchanger]`
  `after_change_gcode`, the new `[input_shaper]`, and adds `SAFE_SYNC_MOTORS`.
* `macros.cfg` — root, user-owned; `PRINT_START`, `PRINT_END`/`_PRINT_END_PARK`,
  `APPLY_AND_SAVE_NEW_CALIBRATION_OFFSETS`, the retired `UNSAFE_*` + new
  `INCREASE_Z_CLEARANCE`, and the `TEST_SPEED` parameter fix.
* `homing.cfg` — root, user-owned; the superseded local `[homing_override]` body was
  removed (it was already overridden at runtime by the readonly toolchanger homing
  override and contained TAP-era calls). Effective homing behaviour is unchanged.

Klipper merges sections that share a name across included files, taking the **last**
value per option. `user-overrides.cfg` must stay the last include so its overrides
win. Duplicate `[gcode_macro NAME]` sections do **not** stack wrappers — they merge.

## Rollback

Baseline commit: `152d3217b502ee6e02fa679775a5d6ad18507e5d`.
Verified dereferenced backup on Pi:
`/home/hermes/printer-backups/before-safety-fixes-20260915-212447.tar.gz`.
Do not blindly extract over live symlinks; this archive contains their contents.

Stop printing and ensure heaters are off. From `/home/pi/printer_data/config`:

```bash
git --git-dir=.git --work-tree=. restore --source=152d321 --worktree -- printer.cfg macros.cfg homing.cfg toolchanger/tools/T0.cfg toolchanger/tools/T1.cfg toolchanger/tools/T2.cfg toolchanger/tools/T3.cfg toolchanger/tools/T4.cfg
```

Issue `RESTART` in Mainsail; require ready. This restores only runtime files changed
by this repair. `user-overrides.cfg` becomes unreferenced. External dependencies and
the backup ZIP remain untouched. Preserve any later calibration before rollback.

## Additional verified dependency revisions

Klipper `6349d4fb0`, Beacon `7c71e98`, motors-sync `0e59ed7`.
These identify checkouts, not proof that installed copies are pristine upstream.
Full Pi OS/firmware restoration and custom extra provenance remain outside this config backup.

## Safety changes and limits

PAUSE freezes tool identity; RESUME verifies it before a separate render handles
that verified tool's temperature and Mainsail recovery. Calibration changes are
stage-only until explicit SAVE_CONFIG/restart; the live transform is not partially
updated. PRINT_END shuts heat off first, then at most10mm Z-only lift with headroom,
without lateral parking or immediate gantry motor disable. Existing idle timeout remains.

Offline tests are not hardware certification. Follow TESTING.md. Crash detector,
electrical settings, dock coordinates, PID, pressure advance, and motion limits
were not guessed or disabled. Physical validation remains attended.
