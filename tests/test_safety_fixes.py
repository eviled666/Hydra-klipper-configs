"""Offline regression tests for the confirmed SexPistols Klipper safety fixes.

These tests render the EFFECTIVE (merged) macro bodies with Klipper's single-brace
Jinja delimiters and mocked status objects, then assert on the emitted command
SEQUENCE. Rendered G-code is never executed on a printer. See klipper_render.py.

Mapping of assertions to the astra-xhigh-review findings:
  1.1  PRINT_END clearance / no descent .......... test_print_end_*
  1.2  PRINT_END null-tool render failure ........ test_print_end_null_tool_*
  1.4  UNSAFE_* retired / safe replacement ....... test_unsafe_*, test_increase_z_*
  1.3  RESUME restores Mainsail body + verify .... test_resume_*
  2.1  first-tool heater resolution .............. test_heat_and_wait_active
  2.2  CALIBRATE_MOVE_OVER_PROBE absolute/homed .. test_calibrate_move_*
  2.3  offset ownership / provenance ............. test_calibrate_all_*, test_apply_and_save_*
  2.5  input shaper type+damping ................. test_after_change_shaper
  4.3  TOOL_ALIGN_TEST dock tolerance ............ test_tool_align_*
  4.3  TEST_SPEED SMALLPATTERNSIZE ............... test_test_speed_smallpattern
  5    SAFE_SYNC_MOTORS precondition ............. test_safe_sync_motors_*
"""

import os
import re
import unittest

import klipper_render as k
from klipper_render import status as S, Coord, MacroError, commands as C

REVIEW = "/home/clawstache/printer-backups/sexpistols-review/config"

CFG = k.effective_config()


def zval(line):
    m = re.search(r"\bZ(-?\d+(?:\.\d+)?)", line)
    return float(m.group(1)) if m else None


def tool_status(**extra):
    s = S(params_park_x=13.3, params_park_y=1.0, params_safe_y=100.0,
          params_park_z=247.0)
    s.update(extra)
    return s


def base_printer(homed="xyz", tool="tool T0", cz=100.0, extruder="extruder",
                 can_extrude=True, off=(0.0, 0.0, 0.0)):
    pr = S(
        toolhead=S(homed_axes=homed, extruder=extruder,
                   axis_maximum=Coord([300, 300, 280, 0]),
                   position=Coord([100, 100, cz, 0])),
        toolchanger=S(tool=tool, tool_number=0, detected_tool_number=0,
                      has_detection=True, tool_numbers=Coord([0, 1, 2, 3, 4])),
        gcode_move=S(homing_origin=Coord([off[0], off[1], off[2], 0]),
                     gcode_position=Coord([100, 100, cz, 0])),
    )
    if extruder:
        pr[extruder] = S(can_extrude=can_extrude)
    if tool:
        pr[tool] = tool_status()
    return pr


# --------------------------------------------------------------------------- #
# 1.2 PRINT_END - unconditional shutdown independent of tool rendering
# --------------------------------------------------------------------------- #
class PrintEndShutdown(unittest.TestCase):
    def test_old_body_fails_on_null_tool(self):
        """Regression: the ORIGINAL PRINT_END raised at render on a null tool."""
        old = k.parse_cfg(os.path.join(REVIEW, "macros.cfg"))
        body = old["gcode_macro PRINT_END"]["gcode"]
        pr = base_printer(tool=None)
        # configfile.config[...] used by the old body
        pr["configfile"] = S(config={"stepper_x": {"position_max": "300"},
                                      "stepper_y": {"position_max": "300"},
                                      "stepper_z": {"position_max": "280"}})
        pr["tool_probe_endstop"] = S()
        with self.assertRaises(Exception):
            k.render_body(body, pr)

    def test_new_body_null_tool_still_shuts_down(self):
        """Fixed: outer PRINT_END always emits TURN_OFF_HEATERS on a null tool."""
        out = C(k.render_macro(CFG, "PRINT_END", base_printer(tool=None,
                                                              homed="",
                                                              extruder="")))
        self.assertTrue(any("TURN_OFF_HEATERS" in l for l in out))
        self.assertTrue(any(l.startswith("M107") for l in out))
        self.assertTrue(any("_PRINT_END_PARK" in l for l in out))

    def test_new_body_cold_does_not_retract(self):
        out = C(k.render_macro(CFG, "PRINT_END",
                               base_printer(extruder="extruder", can_extrude=False)))
        self.assertFalse(any(l.startswith("G1 E-") for l in out))
        self.assertTrue(any("TURN_OFF_HEATERS" in l for l in out))

    def test_shutdown_is_first_and_cannot_retract_or_drop_gantry(self):
        out = C(k.render_macro(CFG, "PRINT_END", base_printer()))
        self.assertEqual(out[0], "TURN_OFF_HEATERS")
        self.assertFalse(any(l.startswith(("G1 E", "M18", "M84")) for l in out))


# --------------------------------------------------------------------------- #
# 1.1 PRINT_END park - clearance, no descent, no overtravel
# --------------------------------------------------------------------------- #
class PrintEndPark(unittest.TestCase):
    def park(self, cz, tool="tool T0", homed="xyz", off=(0.0, 0.0, 0.0)):
        return C(k.render_macro(CFG, "_PRINT_END_PARK",
                                base_printer(tool=tool, homed=homed, cz=cz, off=off)))

    def z_moves(self, out):
        return [l for l in out if l.startswith("G0 Z")]

    def test_no_descent_from_various_heights(self):
        for cz in (0, 259.0, 275.0, 278.0, 280.0):
            out = self.park(cz)
            for zm in self.z_moves(out):
                self.assertIn("G91", out)
                self.assertGreater(zval(zm), 0)
                self.assertLessEqual(cz + zval(zm), 279.5)

    def test_z259_no_intermediate_overshoot_then_descent(self):
        out = self.park(259)
        self.assertEqual([zval(z) for z in self.z_moves(out)], [10.0])

    def test_no_unverified_lateral_moves_even_at_ceiling(self):
        for z in (10, 200, 278, 280):
            out = self.park(z)
            self.assertFalse(any(l.startswith(("G0 X", "G0 Y")) for l in out))

    def test_offset_does_not_overtravel_machine_ceiling(self):
        for off in (-5, 0, 5):
            out = self.park(279, off=(0, 0, off))
            for zm in self.z_moves(out):
                self.assertLessEqual(279 + zval(zm), 279.5)

    def test_unhomed_skips_park(self):
        out = self.park(200.0, homed="")
        self.assertFalse(any(l.startswith("G0 ") for l in out))
        self.assertTrue(any("not homed" in l for l in out))

    def test_null_tool_lifts_but_no_lateral(self):
        out = self.park(200.0, tool=None)
        self.assertTrue(any(l.startswith("G0 Z") for l in out))
        self.assertFalse(any(l.startswith("G0 X") for l in out))


# --------------------------------------------------------------------------- #
# 1.4 UNSAFE_* retired; INCREASE_Z_CLEARANCE safe replacement
# --------------------------------------------------------------------------- #
class UnsafeMacros(unittest.TestCase):
    def test_unsafe_lower_bed_errors(self):
        with self.assertRaises(MacroError):
            k.render_macro(CFG, "UNSAFE_LOWER_BED", base_printer())

    def test_unsafe_raise_bed_errors(self):
        with self.assertRaises(MacroError):
            k.render_macro(CFG, "UNSAFE_RAISE_BED", base_printer())

    def test_increase_z_requires_homed(self):
        with self.assertRaises(MacroError):
            k.render_macro(CFG, "INCREASE_Z_CLEARANCE",
                           base_printer(homed=""), params={"MM": "10"})

    def test_increase_z_rejects_nonpositive(self):
        with self.assertRaises(MacroError):
            k.render_macro(CFG, "INCREASE_Z_CLEARANCE",
                           base_printer(), params={"MM": "0"})

    def test_increase_z_rejects_over_cap(self):
        with self.assertRaises(MacroError):
            k.render_macro(CFG, "INCREASE_Z_CLEARANCE",
                           base_printer(), params={"MM": "51"})

    def test_increase_z_upward_only_and_clamped(self):
        out = C(k.render_macro(CFG, "INCREASE_Z_CLEARANCE",
                               base_printer(cz=100.0), params={"MM": "10"}))
        zt = zval([l for l in out if l.startswith("G0 Z")][0])
        self.assertEqual(zt, 110.0)
        # near ceiling: clamp to max - offset
        out2 = C(k.render_macro(CFG, "INCREASE_Z_CLEARANCE",
                                base_printer(cz=279.0), params={"MM": "10"}))
        zt2 = zval([l for l in out2 if l.startswith("G0 Z")][0])
        self.assertLessEqual(zt2, 280.0)
        self.assertGreaterEqual(zt2, 279.0)


# --------------------------------------------------------------------------- #
# 1.3 RESUME - Mainsail body restored + tool verification gating
# --------------------------------------------------------------------------- #
class ResumeMacro(unittest.TestCase):
    def state(self, hot=True, paused=True, expected=0, active=0):
        pr = S(pause_resume=S(is_paused=paused), idle_timeout=S(state="Ready"),
               toolhead=S(extruder="extruder"), toolchanger=S(tool_number=active),
               configfile=S(settings=S(pause_resume=S(recover_velocity=50))))
        pr["extruder"] = S(can_extrude=hot, target=210)
        pr["gcode_macro RESUME"] = S(expected_tool=expected, idle_state=False,
             last_extruder_temp={"restore":False,"temp":0}, restore_idle_timeout=0)
        return pr

    def test_resume_verifies_recorded_identity_before_second_render(self):
        out = C(k.render_macro(CFG,"RESUME",self.state(expected=4),rawparams=""))
        self.assertEqual(out[:3], ["INITIALIZE_TOOLCHANGER","VERIFY_TOOL_DETECTED T=4","_RESUME_VERIFIED"])
        self.assertFalse(any(l.startswith(("M109","_CLIENT_EXTRUDE","RESUME_BASE")) for l in out))

    def test_verified_hot_resume_unretracts_then_resumes(self):
        out=C(k.render_macro(CFG,"_RESUME_VERIFIED",self.state()))
        self.assertLess(out.index("_CLIENT_EXTRUDE"),next(i for i,l in enumerate(out) if l.startswith("RESUME_BASE")))

    def test_cold_resume_aborts_without_position_resume(self):
        out=C(k.render_macro(CFG,"_RESUME_VERIFIED",self.state(hot=False)))
        self.assertFalse(any(l.startswith("RESUME_BASE") for l in out))

    def test_wrong_active_tool_is_refused(self):
        with self.assertRaises(MacroError):
            k.render_macro(CFG,"_RESUME_VERIFIED",self.state(expected=0,active=4))

    def test_unpaused_or_unrecorded_resume_is_refused(self):
        for pr in [self.state(paused=False),self.state(expected=-1)]:
            with self.assertRaises(MacroError): k.render_macro(CFG,"RESUME",pr,rawparams="")

    def test_duplicate_pause_does_not_overwrite_record(self):
        out=C(k.render_macro(CFG,"PAUSE",self.state(paused=True),rawparams=""))
        self.assertEqual(out,[])

    def test_pause_captures_tool_before_pausing(self):
        out=C(k.render_macro(CFG,"PAUSE",self.state(paused=False,active=4),rawparams=""))
        self.assertIn("VARIABLE=expected_tool VALUE=4",out[0])

    def test_resume_preserves_mainsail_client_hooks(self):
        body=CFG["gcode_macro _RESUME_VERIFIED"]["gcode"]
        for key in ["_CLIENT_EXTRUDE","recover_velocity","runout_sensor","restore_idle_timeout"]:
            self.assertIn(key,body)


# --------------------------------------------------------------------------- #
# 2.1 / 2.2 / 2.3 Calibration ownership, heater, mode
# --------------------------------------------------------------------------- #
class Calibration(unittest.TestCase):
    def test_heat_and_wait_active(self):
        pr = S(toolhead=S(extruder="extruder4"))
        out = C(k.render_macro(CFG, "_HEAT_AND_WAIT_ACTIVE", pr,
                               params={"TEMP": "150"}))
        self.assertTrue(any("TEMPERATURE_WAIT SENSOR='extruder4'" in l for l in out))
        self.assertTrue(any(l.startswith("M104 S150") for l in out))

    def test_calibrate_move_over_probe_absolute_and_homed(self):
        pr = base_printer()
        pr["gcode_macro _CALIBRATION_SWITCH"] = S(x=54.531, y=0.743, z=10)
        out = C(k.render_macro(CFG, "CALIBRATE_MOVE_OVER_PROBE", pr))
        self.assertIn("G90", out)
        self.assertTrue(any(l.startswith("SAVE_GCODE_STATE") for l in out))
        self.assertTrue(any(l.startswith("RESTORE_GCODE_STATE") for l in out))

    def test_calibrate_move_over_probe_requires_homed(self):
        pr = base_printer(homed="")
        pr["gcode_macro _CALIBRATION_SWITCH"] = S(x=1, y=1, z=10)
        with self.assertRaises(MacroError):
            k.render_macro(CFG, "CALIBRATE_MOVE_OVER_PROBE", pr)

    def test_calibrate_all_measures_then_stages_each_tool(self):
        out = C(k.render_macro(CFG, "CALIBRATE_ALL_OFFSETS", base_printer()))
        seq = [l for l in out if l.startswith(("TOOL_CALIBRATE_TOOL_OFFSET",
                                               "_STAGE_ACTIVE_TOOL_OFFSET"))]
        # every measurement is immediately followed by a stage (correct ownership)
        self.assertTrue(seq)
        for i, l in enumerate(seq):
            if l.startswith("TOOL_CALIBRATE_TOOL_OFFSET"):
                self.assertEqual(seq[i + 1], "_STAGE_ACTIVE_TOOL_OFFSET")
        # heat/wait comes AFTER SELECT_TOOL (fix 2.1), never before the first select
        heat_idx = [i for i, l in enumerate(out) if l.startswith("_HEAT_AND_WAIT_ACTIVE")]
        sel_idx = [i for i, l in enumerate(out) if l.startswith("SELECT_TOOL")]
        self.assertLess(sel_idx[0], heat_idx[0])

    def test_calibrate_all_requires_homed(self):
        with self.assertRaises(MacroError):
            k.render_macro(CFG, "CALIBRATE_ALL_OFFSETS", base_printer(homed=""))

    def test_stage_delegates_to_provenance_guard(self):
        out = C(k.render_macro(CFG, "_STAGE_ACTIVE_TOOL_OFFSET", S()))
        self.assertEqual(out, ["APPLY_AND_SAVE_NEW_CALIBRATION_OFFSETS"])

    def test_measurement_invalidates_previous_result_before_native_call(self):
        for macro, native in [("TOOL_LOCATE_SENSOR", "_BASE_TOOL_LOCATE_SENSOR"),
                              ("TOOL_CALIBRATE_TOOL_OFFSET", "_BASE_TOOL_CALIBRATE_TOOL_OFFSET")]:
            out = C(k.render_macro(CFG, macro, S(), rawparams=""))
            self.assertIn("VARIABLE=valid VALUE=False", out[0])
            self.assertTrue(out[1].startswith(native))


class ApplyAndSave(unittest.TestCase):
    def _pr(self, kind="offset", rec_tool="tool T0", active="tool T0",
            rec=(1.0, 2.0, 3.0), live=(1.0, 2.0, 3.0), valid=True):
        return S(
            toolchanger=S(tool=active),
            tools_calibrate=S(last_result=Coord(list(live))),
            **{"gcode_macro _CALIB_RESULT": S(valid=valid, kind=kind, tool=rec_tool,
                                              x=rec[0], y=rec[1], z=rec[2])},
        )

    def test_valid_offset_applies_and_stages(self):
        out = C(k.render_macro(CFG, "APPLY_AND_SAVE_NEW_CALIBRATION_OFFSETS", self._pr()))
        self.assertFalse(any(l.startswith("SET_GCODE_OFFSET") for l in out))
        self.assertTrue(any("VARIABLE=valid VALUE=False" in l for l in out))
        saves = [l for l in out if l.startswith("TOOL_CALIBRATE_SAVE_TOOL_OFFSET")]
        self.assertEqual(len(saves), 3)
        for l in saves:
            self.assertIn('SECTION="tool T0"', l)

    def test_sensor_result_refused(self):
        with self.assertRaises(MacroError):
            k.render_macro(CFG, "APPLY_AND_SAVE_NEW_CALIBRATION_OFFSETS",
                           self._pr(kind="sensor"))

    def test_wrong_tool_refused(self):
        with self.assertRaises(MacroError):
            k.render_macro(CFG, "APPLY_AND_SAVE_NEW_CALIBRATION_OFFSETS",
                           self._pr(rec_tool="tool T4", active="tool T0"))

    def test_stale_result_refused(self):
        with self.assertRaises(MacroError):
            k.render_macro(CFG, "APPLY_AND_SAVE_NEW_CALIBRATION_OFFSETS",
                           self._pr(rec=(1.0, 2.0, 3.0), live=(9.0, 9.0, 9.0)))

    def test_no_result_refused(self):
        with self.assertRaises(MacroError):
            k.render_macro(CFG, "APPLY_AND_SAVE_NEW_CALIBRATION_OFFSETS",
                           self._pr(valid=False))


# --------------------------------------------------------------------------- #
# 2.5 Input shaper - per-tool type + damping applied
# --------------------------------------------------------------------------- #
class InputShaper(unittest.TestCase):
    def test_after_change_shaper(self):
        tool = S(tool_number=2, params_input_shaper_type_x="mzv",
                 params_input_shaper_freq_x=62.4, params_input_shaper_damping_ratio_x=0.01,
                 params_input_shaper_type_y="mzv", params_input_shaper_freq_y=88.6,
                 params_input_shaper_damping_ratio_y=0.01)
        pr = S(**{"gcode_macro T2": S()})
        out = C(k.render_option(CFG, "toolchanger", "after_change_gcode", pr, tool=tool))
        shaper = [l for l in out if l.startswith("SET_INPUT_SHAPER")][0]
        for token in ("SHAPER_TYPE_X=mzv", "SHAPER_FREQ_X=62.4", "DAMPING_RATIO_X=0.01",
                      "SHAPER_TYPE_Y=mzv", "SHAPER_FREQ_Y=88.6", "DAMPING_RATIO_Y=0.01"):
            self.assertIn(token, shaper)

    def test_input_shaper_section_present(self):
        self.assertIn("input_shaper", CFG)
        self.assertEqual(CFG["input_shaper"]["shaper_type_x"], "mzv")


# --------------------------------------------------------------------------- #
# 4.3 TOOL_ALIGN_TEST dock tolerance + TEST_SPEED SMALLPATTERNSIZE
# --------------------------------------------------------------------------- #
class AlignAndSpeed(unittest.TestCase):
    def _align_pr(self, pos):
        pr = base_printer()
        pr["gcode_move"] = S(gcode_position=Coord(list(pos) + [0]))
        pr["toolhead"]["position"] = Coord(list(pos) + [0])
        return pr

    def test_positive_dock_y_is_accepted(self):
        # Dock is at (13.3, 1.0, 247). A near-dock test with POSITIVE Y must NOT
        # be rejected (old code aborted on any Y>0).
        out = C(k.render_macro(CFG, "TOOL_ALIGN_TEST", self._align_pr((13.3, 1.0, 247.0))))
        self.assertTrue(any(l.startswith("TEST_TOOL_DOCKING") for l in out))
        self.assertFalse(any("aborted" in l for l in out))

    def test_far_position_is_rejected(self):
        out = C(k.render_macro(CFG, "TOOL_ALIGN_TEST", self._align_pr((150.0, 150.0, 100.0))))
        self.assertTrue(any("aborted" in l for l in out))
        self.assertFalse(any(l.startswith("TEST_TOOL_DOCKING") for l in out))

    def test_align_requires_tool_and_homed(self):
        pr = base_printer(homed="")
        pr["gcode_move"] = S(gcode_position=Coord([13.3, 1.0, 247.0, 0]))
        out = C(k.render_macro(CFG, "TOOL_ALIGN_TEST", pr))
        self.assertTrue(any("aborted" in l for l in out))

    def _speed_pr(self):
        return S(
            toolhead=S(axis_minimum=Coord([0, 0, 0, 0]),
                       axis_maximum=Coord([300, 300, 280, 0])),
            configfile=S(settings=S(
                printer=S(max_velocity=300, max_accel=5000, max_accel_to_decel=2500),
                quad_gantry_level=S())),
            quad_gantry_level=S(applied=True),
        )

    def test_test_speed_smallpattern_reads_param(self):
        # SMALLPATTERNSIZE=70 -> small box spans center +/- 35 (x_center=150).
        out = C(k.render_macro(CFG, "TEST_SPEED", self._speed_pr(),
                               params={"SMALLPATTERNSIZE": "70"}))
        xs = set()
        for l in out:
            m = re.search(r"\bX(\d+(?:\.\d+)?)", l)
            if m:
                xs.add(float(m.group(1)))
        self.assertIn(115.0, xs, "expected center-35 with size 70")
        self.assertIn(185.0, xs, "expected center+35 with size 70")

    def test_test_speed_default_smallpattern(self):
        out = C(k.render_macro(CFG, "TEST_SPEED", self._speed_pr(), params={}))
        xs = set()
        for l in out:
            m = re.search(r"\bX(\d+(?:\.\d+)?)", l)
            if m:
                xs.add(float(m.group(1)))
        self.assertIn(140.0, xs)  # center-10 with default size 20
        self.assertIn(160.0, xs)


# --------------------------------------------------------------------------- #
# 5 SAFE_SYNC_MOTORS precondition wrapper
# --------------------------------------------------------------------------- #
class SafeSync(unittest.TestCase):
    def _pr(self, homed="xy", tool="tool T0", detected=0):
        return S(toolhead=S(homed_axes=homed),
                 toolchanger=S(tool=tool, has_detection=True,
                               detected_tool_number=detected))

    def test_sync_ok_with_t0_detected(self):
        out = C(k.render_macro(CFG, "SAFE_SYNC_MOTORS", self._pr()))
        self.assertTrue(any(l.startswith("VERIFY_TOOL_DETECTED") for l in out))
        self.assertTrue(any(l.strip() == "SYNC_MOTORS" for l in out))

    def test_sync_requires_homed(self):
        with self.assertRaises(MacroError):
            k.render_macro(CFG, "SAFE_SYNC_MOTORS", self._pr(homed=""))

    def test_sync_requires_t0_active(self):
        with self.assertRaises(MacroError):
            k.render_macro(CFG, "SAFE_SYNC_MOTORS", self._pr(tool="tool T3"))

    def test_sync_requires_t0_detected(self):
        with self.assertRaises(MacroError):
            k.render_macro(CFG, "SAFE_SYNC_MOTORS", self._pr(detected=3))


# --------------------------------------------------------------------------- #
# Whole-config sanity: every effective macro body compiles; PRINT_START renders
# --------------------------------------------------------------------------- #
class ConfigSanity(unittest.TestCase):
    def test_all_effective_macros_compile(self):
        env = k.make_env()
        failures = []
        for sec, opts in CFG.items():
            for opt in ("gcode", "after_change_gcode", "before_change_gcode"):
                if opt in opts:
                    try:
                        env.from_string(opts[opt])
                    except Exception as e:  # noqa: BLE001
                        failures.append("%s/%s: %s" % (sec, opt, e))
        self.assertEqual(failures, [], "template compile failures: %s" % failures)

    def test_print_start_renders_both_bed_branches(self):
        pr = S(toolhead=S(axis_maximum=Coord([300, 300, 280, 0])))
        for bt in ("120", "60"):
            out = C(k.render_macro(CFG, "PRINT_START", pr,
                                   params={"BED_TEMP": bt, "TOOL": "0"}))
            self.assertTrue(any("VORON_PURGE" in l for l in out))
            self.assertTrue(any(l.startswith("START_TOOL_CRASH_DETECTION") for l in out))
            # leveling references must come AFTER the soak commands
            i_soak = max([i for i, l in enumerate(out)
                          if l.startswith("M190") or l.startswith("G4 P300000")
                          or "TEMPERATURE_WAIT" in l])
            i_qgl = [i for i, l in enumerate(out) if l.startswith("QUAD_GANTRY_LEVEL")][0]
            self.assertLess(i_soak, i_qgl, "QGL must run after the soak (bed=%s)" % bt)

    def test_print_start_has_no_retired_commands(self):
        body = CFG["gcode_macro PRINT_START"]["gcode"]
        # rendered output must not emit the undefined/bogus commands
        pr = S(toolhead=S(axis_maximum=Coord([300, 300, 280, 0])))
        out = C(k.render_macro(CFG, "PRINT_START", pr, params={"BED_TEMP": "60", "TOOL": "0"}))
        self.assertFalse(any(l.strip() == "M191 S35" for l in out))
        self.assertFalse(any(l.strip() == "G4 S500" for l in out))


if __name__ == "__main__":
    unittest.main(verbosity=2)
