import unittest

from bot.services.level_curve import (
    build_curve,
    max_level_for_prestige,
    required_xp,
    scale_curve,
)


class LevelCurveTests(unittest.TestCase):
    def setUp(self):
        self.curve = build_curve()

    def test_curve_is_monotonic_and_has_expected_limits(self):
        values = [self.curve[str(level)] for level in range(1, 131)]

        self.assertEqual(self.curve["0"], 0)
        self.assertEqual(values, sorted(values))
        self.assertEqual(max_level_for_prestige(0), 50)
        self.assertEqual(max_level_for_prestige(4), 130)
        self.assertLess(required_xp(self.curve, 50, 0), 60_000)

    def test_prestige_multiplier_is_applied_to_same_curve(self):
        base_xp = required_xp(self.curve, 50, 0)

        self.assertEqual(required_xp(self.curve, 50, 1), round(base_xp * 1.25))

    def test_levels_above_curve_do_not_have_a_threshold(self):
        self.assertEqual(required_xp(self.curve, 131, 4), 0)

    def test_voice_curve_is_scaled_without_changing_level_keys(self):
        voice_curve = scale_curve(self.curve, 1.5)

        self.assertEqual(set(voice_curve), set(self.curve))
        self.assertEqual(voice_curve["50"], round(self.curve["50"] * 1.5))


if __name__ == "__main__":
    unittest.main()