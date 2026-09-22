"""Offline backup regressions; never sends G-code or claims physical clearance."""
import pathlib
import unittest
import klipper_render as k
from klipper_render import status as S, Coord, commands

ROOT = pathlib.Path(k.FIX)
CFG = k.effective_config()

class PickupBackup(unittest.TestCase):
    def test_original_pickup_is_inherited_without_local_override(self):
        local = k.parse_cfg(str(ROOT / "user-overrides.cfg"))
        self.assertNotIn("pickup_gcode", local["toolchanger"])
        body = CFG["toolchanger"]["pickup_gcode"]
        self.assertIn("Y={tool.params_safe_y} F={fast} D=20", body)
        self.assertIn("Z={restore_position.Z} F={fast} D=150", body)
        self.assertNotIn("_AUTO_FRONT_BRUSH", body)

    def test_no_automatic_brush_caller_in_effective_callbacks(self):
        for section, opts in CFG.items():
            for key, body in opts.items():
                if key.endswith("_gcode"):
                    self.assertNotIn("_AUTO_FRONT_BRUSH", body, (section, key))
        self.assertIn("gcode_macro BRUSH_CLEAN", CFG)

    def test_include_order(self):
        text = (ROOT / "printer.cfg").read_text()
        self.assertLess(text.index("[include front-brush.cfg]"), text.index("[include user-overrides.cfg]"))

    def bed(self, **params):
        return commands(k.render_macro(CFG, "M190", S(configfile=S(settings=S(
            heater_bed=S(min_temp=0, max_temp=120)))), params=params, deadband=3.0))

    def test_m190_alias_and_default_band(self):
        self.assertEqual(CFG["gcode_macro M190"]["rename_existing"], "M190.1")
        self.assertIn("TEMPERATURE_WAIT SENSOR=heater_bed MINIMUM=57.0 MAXIMUM=63.0", self.bed(S="60"))

    def test_m190_zero_does_not_wait(self):
        self.assertEqual(self.bed(S="0"), ["M140 S0.0"])

    def test_m190_invalid_values_rejected(self):
        for params in ({"S":"121"}, {"S":"-1"}, {"D":"0"}, {"D":"11"}):
            with self.assertRaises(k.MacroError): self.bed(**params)

    def start(self, **params):
        return commands(k.render_macro(CFG, "PRINT_START", S(toolhead=S(
            axis_maximum=Coord([300,300,280,0]))), params=params))

    def test_material_soak_policy(self):
        for material, expected in [("ABS",True),("ASA",True),("PLA",False),("TPU",False),("TPE",False),("PETG",False)]:
            out = self.start(MATERIAL=material, BED_TEMP="100")
            self.assertEqual(any("TEMPERATURE_WAIT SENSOR=\"temperature_sensor chamber\"" in line for line in out), expected)
            self.assertNotIn("G4 P300000", out)

    def test_explicit_soak_override(self):
        self.assertTrue(any("temperature_sensor chamber" in line for line in self.start(MATERIAL="PLA",HEATSOAK="1")))
        self.assertFalse(any("temperature_sensor chamber" in line for line in self.start(MATERIAL="ABS",HEATSOAK="0")))

    def test_invalid_soak_mode_rejected(self):
        with self.assertRaises(k.MacroError): self.start(HEATSOAK="bogus")

if __name__ == "__main__":
    unittest.main()
