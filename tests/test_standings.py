"""Les scores seuls ne suffisent pas toujours à reconstituer les points."""

import pandas as pd
import unittest

from ift3700.report import standings_from_games


class StandingsTests(unittest.TestCase):
    def test_regulation_overtime_shootout_and_confirmed_point_forfeit(self):
        rows = [
            (2023020001, 3, 2, "REG"),  # victoire : 2 points
            (2023020002, 2, 3, "REG"),  # défaite : 0 point
            (2023020003, 2, 3, "OT"),   # défaite OT habituelle : 1 point
            (2023020004, 2, 3, "SO"),   # défaite SO : 1 point
            (2023021166, 1, 2, "OT"),   # point perdu, règle 84.2
        ]
        exposure = pd.DataFrame([dict(game_id=g, team_id=30, team="MIN", season=20232024,
                                     game_type=2, score=a, opponent_score=b, last_period_type=t)
                                 for g, a, b, t in rows])
        result = standings_from_games(exposure).iloc[0]
        self.assertEqual((result.games, result.wins, result.losses, result.ot_losses, result.points),
                         (5, 1, 2, 2, 4))
        self.assertEqual(result.ot_point_forfeits, 1)
        # Un autre but en filet désert ne doit pas être assimilé automatiquement
        # à cette annotation historique ; les pénalités différées sont distinctes.
        exposure.loc[4, "game_id"] = 2023021167
        self.assertEqual(standings_from_games(exposure).iloc[0].points, 5)

    def test_forfeit_annotation_cannot_apply_to_a_win(self):
        exposure = pd.DataFrame([dict(game_id=2023021166, team_id=30, team="MIN", season=20232024,
                                     game_type=2, score=2, opponent_score=1, last_period_type="OT")])
        with self.assertRaisesRegex(ValueError, "annotation"):
            standings_from_games(exposure)


if __name__ == "__main__":
    unittest.main()
