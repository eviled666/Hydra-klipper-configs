# SexPistols: test the repaired configuration

Offline tests are not hardware certification. Follow this order with a clear bed, properly secured mounted tool, clear docks, and emergency stop within reach. Do not deliberately detach a tool during a print to test detection. Stop on unexpected travel, temperature, collision, or shutdown.

## 1. Configuration load (operator performs before handoff)

Deploy only after checking standby and all heater targets zero. Run RESTART, not homing or printing. Require Klipper ready, warnings empty, input_shaper loaded, and calibration offsets unchanged. Read back effective macros. If configuration loading fails, restore the previous files and RESTART; do not proceed.

## 2. No-motion checks immediately after restart, while still unhomed

Send commands one at a time in Mainsail:

- `PRINT_END`: heaters/fans off, report skipping lift; no motion.
- `RESUME`: error that printer is not paused; no motion/extrusion.
- `INCREASE_Z_CLEARANCE MM=0`: reject invalid increment.
- `INCREASE_Z_CLEARANCE MM=10`: reject unhomed Z.
- `APPLY_AND_SAVE_NEW_CALIBRATION_OFFSETS`: reject absent measurement.
- `CALIBRATE_ALL_OFFSETS`: reject unhomed axes.

These errors are intentional. Do not use the retired UNSAFE_LOWER_BED/UNSAFE_RAISE_BED commands; their old unhomed motions are disabled.

## 3. First attended motion

1. Confirm the normal mounted-tool/bed/dock prerequisites for this printer, then `G28`. Homing geometry was not changed.
2. `INCREASE_Z_CLEARANCE MM=5`: expect clearance to increase by about 5 mm, limited near the ceiling.
3. `PRINT_END`: expect heater targets zero, a Z-only upward lift of at most 10 mm, NO XY parking, NO descent, and motors remaining enabled until the existing idle timeout. The removal of lateral parking is intentional: no unverified clear corridor is assumed.
4. Do not test at maximum travel or use fabricated coordinates. Near-ceiling cases were checked offline; physical boundary verification belongs in a separate controlled session.
5. After these pass, perform familiar attended tool changes individually (T0 then each needed tool). Watch pickup/detection and check console for errors. New shaping uses existing configured parameters, not newly measured values.

## 4. Small first print and pause/resume

Use a small, familiar single-tool sliced file, not a large multi-tool job. Keep the first run attended.

- Startup: bed/nozzle preparation, the existing five-minute soak for bed <=90 C or chamber-target wait above90 C, THEN final QGL, Z reference/Beacon calibration and adaptive mesh.
- Confirm object definitions exist before meshing if adaptive bounds are expected.
- Confirm normal purge; max_extrude_cross_section remains5 for VORON_PURGE.
- Pause through Mainsail. Resume while hot: tool verification precedes unretract and return to print. Do not attempt a cold resume without following the displayed reheating instructions.
- At finish: targets zero; Z-only bounded lift; no lateral/downward park.

Do not first test with a full-temperature unattended multi-tool print. Real idle-timeout recovery and all-tool operation need separate attended acceptance checks.

## 5. Calibration (separate session, only if needed)

Existing calibration values were preserved. Do not recalibrate merely to test basic startup.

Use a fresh restart, clear bed, correct calibration switch placement, normal homing, and verified T0 reference. `CALIBRATE_ALL_OFFSETS` is a real heating/tool-changing/probing procedure, not a no-motion diagnostic. It heats each selected tool to150 C, captures T0 sensor location, then measures/stages each remaining tool's offsets to its own section. Review staged values before `SAVE_CONFIG`.

The historical command `APPLY_AND_SAVE_NEW_CALIBRATION_OFFSETS` is now deliberately STAGE-ONLY: it rejects sensor locations, stale/mismatched results, and consumed results. It does not mutate the live transform. `SAVE_CONFIG` persists and restarts, loading tool-object and motion state consistently. Do not expect same-tool reselection to apply new values.

Tool offsets now live in root printer.cfg so SAVE_CONFIG can replace them without included-value conflicts. Their numerical values were not altered by deployment. Never apply an absolute sensor-location result as a tool offset.

## 6. Optional maintenance helpers — not first-run tests

- `SAFE_SYNC_MOTORS` requires homed XY and T0 active/detected; synchronization causes physical motion/vibration. Not needed for first print acceptance.
- `TOOL_ALIGN_TEST` is a real docking/calibration operation. It checks proximity to the configured dock, then stages the current machine position as a candidate dock position. It DOES change in-memory dock parameters. Do not run casually or at an arbitrary nearby point; follow the established dock-alignment procedure and do not save unverified coordinates.
- `TEST_SPEED` is a motion stress test, not required for these safety fixes.

## Deferred validation

Fan voltage/startup/cooling, Nitehawk resistor identity, motor interpolation policy, safe Y rebound, dock corridors, rear Beacon sensing coverage and network trust require hardware/environment evidence. They were not guessed. Detector late-edge/UNSELECT_TOOL behavior remains an identified conditional risk; do not disable protection to hide it. Report unexpected shutdowns with console/log evidence.

## Offline tests

From repository root: create a local venv with Jinja2 if absent, then `cd tests && ../.venv/bin/python -m unittest test_safety_fixes -v`. Harness uses the operator's dereferenced review evidence, not a standalone firmware simulator; see tests/klipper_render.py. No rendered G-code is sent to hardware.

## Rollback

Pre-change commit: `152d3217b502ee6e02fa679775a5d6ad18507e5d`.
Dereferenced backup on Pi: `/home/hermes/printer-backups/before-safety-fixes-20260915-212447.tar.gz`.
Do not extract the entire dereferenced archive over managed symlinks. Restore only changed user files from the Git baseline, then RESTART. See RECOVERY.md. If you encounter a problem, stop and ask the operator to perform rollback rather than forcing unhomed movement.
