"""Vérifier des invariants sportifs, des dénominateurs et la gestion des absences."""

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from fixtures import synthetic_game
from ift3700.acquisition import AcquisitionError
from ift3700.analysis import distance_table, shot_types, wilson_interval
from ift3700.explorer import build_explorer, draw_event
from ift3700.shotmaps import make_map_figure, map_rates, physical_to_pixel
from ift3700.tidy import game_to_frame


class HockeyTests(unittest.TestCase):
    def test_only_saved_shots_and_goals_unique_key(self):
        frame = game_to_frame(synthetic_game())
        self.assertEqual(frame["event_id"].tolist(), [2, 3, 4, 5])
        self.assertEqual(frame["is_goal"].sum(), 1)
        self.assertFalse(frame.duplicated(["game_id", "event_id"]).any())

    def test_missing_not_zero_or_false_and_names(self):
        frame = game_to_frame(synthetic_game()).set_index("event_id")
        self.assertEqual(frame.loc[2, "shooter_name"], "Test Shooter")
        self.assertEqual(frame.loc[2, "goalie_name"], "Test Goalie")
        self.assertTrue(pd.isna(frame.loc[5, "x"]))
        self.assertTrue(pd.isna(frame.loc[5, "empty_net"]))
        self.assertTrue(pd.isna(frame.loc[5, "distance_ft"]))
        self.assertEqual(frame.loc[2, "strength"], "EV")
        self.assertEqual(frame.loc[2, "strength_detail"], "5c5")
        self.assertEqual(frame.loc[3, "strength"], "PP")
        self.assertEqual(frame.loc[3, "strength_detail"], "5c4")
        self.assertTrue(pd.isna(frame.loc[5, "strength"]))
        self.assertTrue(pd.isna(frame.loc[5, "strength_detail"]))

    def test_rotation_and_attacking_goal_distance(self):
        frame = game_to_frame(synthetic_game()).set_index("event_id")
        self.assertEqual(frame.loc[4, "x_normalized"], 79)
        self.assertEqual(frame.loc[4, "y_normalized"], 5)
        self.assertAlmostEqual(frame.loc[4, "distance_ft"], np.hypot(10, 5))
        self.assertEqual(frame.loc[2, "distance_ft"], 10)
        game = synthetic_game()
        game["plays"][1]["details"].update(eventOwnerTeamId=2, xCoord=-79, yCoord=-5)
        away = game_to_frame(game).set_index("event_id")
        self.assertEqual(away.loc[2, "x_normalized"], 79)
        self.assertEqual(away.loc[2, "y_normalized"], 5)

    def test_unknown_orientation_remains_unknown(self):
        game = synthetic_game()
        for event in game["plays"]:
            event.pop("homeTeamDefendingSide", None)
        frame = game_to_frame(game)
        self.assertTrue(frame["distance_ft"].isna().all())

    def test_empty_net_not_confused_with_shorthanded(self):
        game = synthetic_game()
        game["plays"][2]["situationCode"] = "0651"
        goal = game_to_frame(game).set_index("event_id").loc[3]
        self.assertTrue(goal.empty_net)
        self.assertTrue(pd.isna(goal.strength))
        self.assertEqual(goal.strength_detail, "5c6")

    def test_shot_strength_from_away_perspective(self):
        game = synthetic_game()
        game["plays"][1]["details"]["eventOwnerTeamId"] = 2
        game["plays"][1]["situationCode"] = "1541"
        shot = game_to_frame(game).set_index("event_id").loc[2]
        self.assertEqual(shot.strength, "PP")
        self.assertEqual(shot.strength_detail, "5c4")

    def test_event_side_takes_priority_when_period_metadata_changes(self):
        game = synthetic_game()
        game["plays"][1]["homeTeamDefendingSide"] = "right"
        game["plays"][1]["details"]["xCoord"] = -79
        game["plays"][1]["details"]["zoneCode"] = "O"
        game["plays"][2]["details"]["zoneCode"] = "O"
        frame = game_to_frame(game).set_index("event_id")
        self.assertEqual(frame.loc[2, "x_normalized"], 79)
        self.assertEqual(frame.loc[2, "direction_source"], "api_event_side_conflict")
        self.assertEqual(frame.loc[3, "x_normalized"], 89)

    def test_period_median_does_not_override_conflicting_zone_votes(self):
        game = synthetic_game()
        for event in game["plays"]:
            event.pop("homeTeamDefendingSide", None)
        shots = [copy.deepcopy(game["plays"][1]) for _ in range(3)]
        for index, (event, x) in enumerate(zip(shots, [79, 87, -79])):
            event.update(eventId=index + 20)
            event["details"].update(xCoord=x, zoneCode="O")
        game["plays"] = shots
        frame = game_to_frame(game)
        self.assertTrue(frame["distance_ft"].isna().all())
        self.assertEqual(frame["x"].tolist(), [79, 87, -79])

    def test_event_conflicting_with_zone_majority_stays_unknown(self):
        game = synthetic_game()
        shots = [copy.deepcopy(game["plays"][1]) for _ in range(10)]
        for index, event in enumerate(shots):
            event.pop("homeTeamDefendingSide", None)
            event.update(eventId=index + 20)
            event["details"].update(xCoord=79 if index < 9 else -79, zoneCode="O")
        game["plays"] = shots
        frame = game_to_frame(game)
        self.assertTrue(frame.iloc[:9]["distance_ft"].notna().all())
        self.assertTrue(pd.isna(frame.iloc[9]["distance_ft"]))
        self.assertEqual(frame.iloc[9]["direction_source"], "unknown_zone_conflict")

    def test_zone_codes_override_api_side_inverted_for_whole_period(self):
        # Cas réel des matchs 2019020249 et 2019020256 : l'API annonce le mauvais
        # côté pour toute la période, et toutes les zones O le contredisent.
        game = synthetic_game()
        shots = [copy.deepcopy(game["plays"][1]) for _ in range(6)]
        for index, event in enumerate(shots):
            event.update(eventId=index + 20, homeTeamDefendingSide="right")
            event["details"].update(xCoord=70 + index, yCoord=5, zoneCode="O")
        game["plays"] = shots
        frame = game_to_frame(game)
        self.assertTrue(frame["x_normalized"].gt(0).all())
        self.assertTrue(frame["direction_source"].eq("zone_code_overrides_api_side").all())
        self.assertAlmostEqual(frame.iloc[0]["distance_ft"], np.hypot(19, 5))

    def test_isolated_api_side_contradicting_zone_becomes_unknown(self):
        game = synthetic_game()
        game["plays"][1]["homeTeamDefendingSide"] = "right"
        game["plays"][1]["details"]["zoneCode"] = "O"
        frame = game_to_frame(game).set_index("event_id")
        self.assertEqual(frame.loc[2, "x"], 79)
        self.assertTrue(pd.isna(frame.loc[2, "x_normalized"]))
        self.assertTrue(pd.isna(frame.loc[2, "distance_ft"]))
        self.assertEqual(frame.loc[2, "direction_source"], "unknown_api_side_zone_conflict")
        self.assertEqual(frame.loc[3, "x_normalized"], 89)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "data/raw/20192020/regular/2019020256.json").exists(),
                         "Cache réel absent")
    def test_real_buffalo_goal_2019020256_event_73(self):
        path = Path(__file__).resolve().parents[1] / "data/raw/20192020/regular/2019020256.json"
        frame = game_to_frame(json.loads(path.read_text(encoding="utf-8"))).set_index("event_id")
        goal = frame.loc[73]
        self.assertEqual((goal["x"], goal["y"]), (-69, 16))
        self.assertEqual((goal["x_normalized"], goal["y_normalized"]), (69, -16))
        self.assertAlmostEqual(goal["distance_ft"], np.hypot(20, 16))
        self.assertEqual(goal["direction_source"], "zone_code_overrides_api_side")

    def test_duplicate_event_fails(self):
        game = synthetic_game()
        game["plays"].append(copy.deepcopy(game["plays"][1]))
        with self.assertRaises(AcquisitionError):
            game_to_frame(game)

    def test_counts_conversion_and_local_exclusions(self):
        frame = game_to_frame(synthetic_game(2019020001))
        types, report = shot_types(frame, 2019)
        self.assertEqual(types.loc["wrist", "shots"], 2)
        self.assertEqual(types.loc["wrist", "goals"], 1)
        self.assertEqual(types.loc["wrist", "goal_pct"], 50)
        self.assertEqual(report["excluded_missing_shot_type"], 1)
        distance, report = distance_table(frame, 2019)
        self.assertEqual(distance["shots"].sum(), 3)
        self.assertEqual(distance["goals"].sum(), 1)
        self.assertEqual(report["excluded_missing_required_fields"], 1)

    def test_map_denominator_includes_games_without_retained_shots(self):
        frame = game_to_frame(synthetic_game())
        exposure = pd.DataFrame([
            {"game_id": game, "season": 20172018, "game_type": 2, "team_id": team, "team": label}
            for game in [2017020001, 2017020002] for team, label in [(1, "AAA"), (2, "BBB")]
        ])
        maps = map_rates(frame, exposure, 2017)
        self.assertEqual(maps["report"]["league_team_hours"], 4)
        self.assertAlmostEqual(maps["league_rate"].sum(), 3 / 4)
        self.assertAlmostEqual(maps["teams"]["AAA"]["rate"].sum(), 3 / 2)
        self.assertAlmostEqual(maps["teams"]["AAA"]["excess"].sum(), 3 / 4)
        self.assertAlmostEqual(maps["teams"]["BBB"]["excess"].sum(), -3 / 4)
        # L'excès moyen, pondéré par les heures-équipe, doit être exactement nul.
        weighted = sum(team["excess"] * team["games"] for team in maps["teams"].values())
        np.testing.assert_allclose(weighted, 0)
        figure = make_map_figure(maps)
        self.assertEqual(len(figure.data), 2)
        self.assertEqual(len(figure.layout.updatemenus[0].buttons), 2)
        self.assertEqual(figure.layout.updatemenus[0].buttons[1].args[0]["visible"], [False, True])

    def test_pixel_conversion_corners_and_center(self):
        x, y = physical_to_pixel(np.array([-100, 0, 100]), np.array([42.5, 0, -42.5]), 1101, 469)
        np.testing.assert_allclose(x, [0, 550, 1100])
        np.testing.assert_allclose(y, [0, 234, 468])

    def test_confidence_interval_handles_zero_and_extremes(self):
        lower, upper = wilson_interval([0, 0, 10], [0, 10, 10])
        self.assertTrue(np.isnan(lower[0]))
        self.assertTrue(np.isnan(upper[0]))
        self.assertAlmostEqual(lower[1], 0)
        self.assertAlmostEqual(upper[2], 100)

    def test_explorer_can_select_every_event_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "20162017/regular/2016020001.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(synthetic_game(2016020001)))
            catalog = root / "catalogs/20162017.json"
            catalog.parent.mkdir()
            catalog.write_text(json.dumps({"season": 20162017, "total": 1, "data": [{"id": 2016020001, "gameStateId": 7}]}))
            with redirect_stdout(io.StringIO()):
                widget = build_explorer(root)
                slider = widget.children[3]
                self.assertEqual(slider.max, 6)
                slider.value = 6
            self.assertEqual(slider.value, 6)
            widget.close()
        figure = draw_event(synthetic_game(), 4)
        self.assertTrue(any("ne contient pas" in text.get_text() for text in figure.axes[0].texts))
        plt.close(figure)


if __name__ == "__main__":
    unittest.main()
