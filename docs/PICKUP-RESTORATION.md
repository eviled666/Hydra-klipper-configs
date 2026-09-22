# SexPistols pickup restoration — 2026-09-22

**USER-VERIFIED:** the owner confirmed that the pickup problem is fixed and requested this repository update. This is the owner's physical confirmation, not a claim that an agent tested every tool or clearance condition.

## Fix and retained behavior

The former pickup override changed the trajectory to full stops and sequential returns. Removing that override restored the original toolchanger rounded exit: safe Y with `D=20`, restored Z with `D=150`, optional X with `D=1000`, and final Y/flush with `D=0`. A speed adjustment alone did not fix the trajectory regression.

- `user-overrides.cfg` does not override `pickup_gcode`. The managed toolchanger dependency supplies the original body; do not edit its symlink target.
- Automatic brushing has no caller in the normal pickup. `front-brush.cfg` retains manual `BRUSH_CLEAN` and the unused automatic helper. Its `enabled=True` variable does not mean automatic pickup brushing is active. Do not re-enable it without separately validating the complete path.
- `M190` waits within ±3°C by default; `D` changes the half-width. `M190.1` preserves the native command. Heater PID and safety limits are unchanged.
- `PRINT_END` shuts heaters off first, performs the bounded Z-only lift, then `M400` before `M84`. This intentionally supersedes the earlier keep-motors-enabled behavior. Motor-release/gantry-drift safety is not established by offline tests.
- Material-aware startup soak remains: ABS/ASA soak, PLA/TPU/TPE/PETG skip, unknown material falls back to bed temperature above 90°C. `HEATSOAK=0/1` overrides the policy. There is no unconditional five-minute soak for lower-temperature jobs.

## Evidence boundaries

The overnight audit initially found the original pickup only on disk while the printer still ran the former override. That is historical. The authorized activation at **13:04 EDT** followed print completion; captured read-back showed ready, standby, no configuration warnings, and pickup matching the original after whitespace/comment normalization. The owner subsequently confirmed the physical fix.

This publication uses the read-only captured configuration, cross-checked against that post-activation runtime evidence. A new SCP refresh encountered an approval gate, so no fresh remote snapshot is claimed. The publication itself issued no printer writes, restarts, motion, heating or SAVE_CONFIG.

Pending Beacon/default mesh results are normal per-print calibration, not a defect or repeated save/discard approval gate. Do not SAVE_CONFIG solely to clear that flag; intentional persistent tool-offset changes are separate.

## Verification and remaining limits

- Offline regression suite: **59 tests passed**, including restored pickup inheritance/no automatic callback, M190 validation, soak policy, and shutdown→park→M400→M84 ordering.
- Captured installed parser with the published user files overlaid on the private dependency snapshot: **146 effective sections, 68 templates compiled**, and **no normalized option differences** from captured post-activation configuration.
- Existing pause/resume, staging/provenance, shaping, travel-limit and calibration regression coverage is retained.
- No claim of full firmware simulation, backup restore, all-tool commissioning, or brush swept-volume certification. The test harness requires private dereferenced dependency evidence; this repository is not a standalone recovery image.
- Other audit findings remain unresolved: cancellation can leave the custom printing flag set, automatic-brush geometry checks are incomplete, conditional out-of-range adaptive-mesh bounds and extra-Z restoration behavior need separate work.

Raw runtime JSON, host inventories, private paths, credentials and historical archives are deliberately excluded from this public report. Detailed linked operating notes remain in the owner's Obsidian vault.
