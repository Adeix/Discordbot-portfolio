import unittest

from src.level_curve import (
    build_curve,
    max_level_for_prestige,
    required_xp,
    scale_curve,
)


class LevelCurveTests(unittest.TestCase):
    def test_curve_is_strictly_increasing(self):
        curve = build_curve(50)
        values = [curve[str(level)] for level in range(1, 51)]

        self.assertEqual(values, sorted(set(values)))

    def test_prestige_increases_level_cap(self):
        self.assertEqual(max_level_for_prestige(0), 50)
        self.assertEqual(max_level_for_prestige(1), 70)
        self.assertEqual(max_level_for_prestige(5), 130)

    def test_prestige_increases_required_xp(self):
        curve = build_curve(50)

        self.assertLess(
            required_xp(curve, 50, prestige=0),
            required_xp(curve, 50, prestige=1),
        )

    def test_voice_curve_can_be_scaled(self):
        curve = build_curve(10)
        voice_curve = scale_curve(curve, 1.5)

        self.assertEqual(voice_curve["0"], 0)
        self.assertGreater(voice_curve["10"], curve["10"])
