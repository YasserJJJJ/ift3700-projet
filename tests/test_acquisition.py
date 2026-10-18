"""Tests avec réponses artificielles, jamais présentées comme données de la LNH."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from ift3700.acquisition import AcquisitionError, NHLClient, game_info, season_id
from ift3700.acquire import main


def artificial_game(identifier=2017020001):
    """Réponse minimale artificielle pour tester le stockage, sans analyse sportive."""
    year, kind = game_info(identifier)
    return {"id": identifier, "season": season_id(year), "gameType": kind,
            "gameState": "OFF", "plays": [{"eventId": 1, "typeDescKey": "faceoff"}]}


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.client = NHLClient(self.folder.name, delay=0, retries=0)

    def test_id_and_season(self):
        self.assertEqual(season_id(2017), 20172018)
        self.assertEqual(game_info(2017030416), (2017, 3))
        for identifier in [2017, 2017010001, "abcdefghij"]:
            with self.assertRaises(ValueError):
                game_info(identifier)

    def test_second_call_and_new_client_use_cache_without_network(self):
        with patch.object(self.client, "_get_json", return_value=artificial_game()) as request:
            first = self.client.get_game(2017020001)
            self.assertEqual(first, self.client.get_game(2017020001))
            request.assert_called_once()
        offline = NHLClient(self.folder.name, offline=True)
        self.assertEqual(first, offline.get_game(2017020001))
        self.assertEqual(offline.request_count, 0)
        self.assertEqual(offline.cache_hits, 1)

    def test_environment_and_explicit_directory(self):
        with patch.dict(os.environ, {"NHL_DATA_DIR": self.folder.name}):
            self.assertEqual(NHLClient().data_dir, Path(self.folder.name))
            self.assertEqual(NHLClient("custom").data_dir, Path("custom"))

    def test_bad_remote_payload_is_not_saved(self):
        for key, value in [("id", 2017020002), ("season", 20162017),
                           ("gameType", 3), ("gameState", "FUT"), ("plays", [])]:
            bad = artificial_game()
            bad[key] = value
            with patch.object(self.client, "_get_json", return_value=bad):
                with self.assertRaises(AcquisitionError):
                    self.client.get_game(2017020001)
            self.assertFalse(self.client.game_path(2017020001).exists())

    def test_corrupt_cache_not_silently_overwritten(self):
        path = self.client.game_path(2017020001)
        path.parent.mkdir(parents=True)
        path.write_text("{truncated", encoding="utf-8")
        with patch.object(self.client, "_get_json", return_value=artificial_game()) as request:
            with self.assertRaises(AcquisitionError):
                self.client.get_game(2017020001)
            request.assert_not_called()
            self.client.get_game(2017020001, force=True)
        self.assertEqual(json.loads(path.read_text())["id"], 2017020001)
        self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_offline_missing_game_and_catalog(self):
        client = NHLClient(self.folder.name, offline=True)
        with self.assertRaises(AcquisitionError):
            client.get_game(2017020001)
        with self.assertRaises(AcquisitionError):
            client.list_games(2017)
        self.assertEqual(client.request_count, 0)

    def test_real_transport_decodes_json_and_counts_requests(self):
        with patch("ift3700.acquisition.urlopen", return_value=io.BytesIO(json.dumps(artificial_game()).encode())):
            self.client.get_game(2017020001)
        self.assertEqual(self.client.request_count, 1)

    def test_403_not_retried_or_saved(self):
        self.client.retries = 3
        error = HTTPError("https://example.invalid", 403, "Forbidden", {}, None)
        with patch("ift3700.acquisition.urlopen", side_effect=error) as request:
            with self.assertRaisesRegex(AcquisitionError, "HTTP 403"):
                self.client.get_game(2017020001)
            self.assertEqual(request.call_count, 1)
        self.assertFalse(self.client.game_path(2017020001).exists())

    def test_429_retry_then_success(self):
        self.client.retries = 1
        error = HTTPError("https://example.invalid", 429, "Slow down", {"Retry-After": "2"}, None)
        payload = io.BytesIO(json.dumps(artificial_game()).encode())
        with patch("ift3700.acquisition.urlopen", side_effect=[error, payload]), \
                patch("ift3700.acquisition.time.sleep") as pause:
            self.client.get_game(2017020001)
        pause.assert_any_call(2.0)
        self.assertEqual(self.client.request_count, 2)

    def test_catalog_pagination_filters_preseason_preserves_playoff_ids(self):
        pages = [
            {"total": 4, "data": [{"id": 2017010001, "gameStateId": 7}, {"id": 2017020001, "gameStateId": 7}]},
            {"total": 4, "data": [{"id": 2017030111, "gameStateId": 7}, {"id": 2017030416, "gameStateId": 7}]},
        ]
        with patch.object(self.client, "_get_json", side_effect=pages) as request:
            self.assertEqual(self.client.list_games(2017), [2017020001, 2017030111, 2017030416])
            second_query = parse_qs(urlsplit(request.call_args_list[1].args[0]).query)
            self.assertEqual(second_query["start"], ["2"])
            self.assertEqual(second_query["cayenneExp"], ["season=20172018"])
        with patch.object(self.client, "_get_json") as request:
            self.assertEqual(self.client.list_games(2017, game_types=(3,)), [2017030111, 2017030416])
            request.assert_not_called()

    def test_incomplete_repeated_and_wrong_season_catalogs_not_cached(self):
        cases = [
            [{"total": 2, "data": [{"id": 2017020001, "gameStateId": 7}]}, {"total": 2, "data": []}],
            [{"total": 2, "data": [{"id": 2017020001, "gameStateId": 7}]}, {"total": 2, "data": [{"id": 2017020001, "gameStateId": 7}]}],
            [{"total": 1, "data": [{"id": 2018020001, "gameStateId": 7}]}],
            [{"total": 0, "data": []}],
        ]
        for pages in cases:
            with self.subTest(pages=pages), patch.object(self.client, "_get_json", side_effect=pages):
                with self.assertRaises(AcquisitionError):
                    self.client.list_games(2017)
            self.assertFalse((self.client.data_dir / "catalogs/20172018.json").exists())

    def test_unplayed_playoff_games_are_not_download_targets(self):
        page = {"total": 3, "data": [
            {"id": 2017020001, "gameStateId": 7},
            {"id": 2017030416, "gameStateId": 7},
            {"id": 2017030417, "gameStateId": 1},
        ]}
        with patch.object(self.client, "_get_json", return_value=page):
            self.assertEqual(self.client.list_games(2017), [2017020001, 2017030416])
        with patch.object(self.client, "_get_json", side_effect=[artificial_game(), artificial_game(2017030416)]), \
                redirect_stdout(io.StringIO()):
            report = self.client.download_season(2017)
        self.assertTrue(report["complete"])
        self.assertEqual(report["unplayed_catalog_ids"], [2017030417])

    def test_catalog_without_game_state_cannot_claim_completeness(self):
        with patch.object(self.client, "_get_json", return_value={"total": 1, "data": [{"id": 2017020001}]}):
            with self.assertRaisesRegex(AcquisitionError, "État"):
                self.client.list_games(2017)

    def test_failed_season_resume_only_fetches_missing_match(self):
        identifiers = [2017020001, 2017030416]
        with patch.object(self.client, "list_games", return_value=identifiers), \
                patch.object(self.client, "_get_json", side_effect=[artificial_game(), AcquisitionError("HTTP 503")]), \
                redirect_stdout(io.StringIO()):
            report = self.client.download_season(2017)
        self.assertFalse(report["complete"])
        self.assertIn("2017030416", report["failed"])
        with patch.object(self.client, "list_games", return_value=identifiers), \
                patch.object(self.client, "_get_json", return_value=artificial_game(2017030416)) as request, \
                redirect_stdout(io.StringIO()):
            report = self.client.download_season(2017)
        self.assertTrue(report["complete"])
        self.assertEqual(report["cached"], [2017020001])
        self.assertEqual(report["downloaded"], [2017030416])
        self.assertEqual(request.call_count, 1)

    def test_limited_run_is_not_complete(self):
        with patch.object(self.client, "list_games", return_value=[2017020001, 2017030416]), \
                patch.object(self.client, "_get_json", return_value=artificial_game()), \
                redirect_stdout(io.StringIO()):
            report = self.client.download_season(2017, limit=1)
        self.assertFalse(report["complete"])
        self.assertEqual(report["expected"], 2)
        self.assertEqual(report["selected"], 1)

    def test_cli_returns_failure_on_missing_offline_data(self):
        with redirect_stdout(io.StringIO()), patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(main(["--game", "2017020001", "--offline", "--data-dir", self.folder.name]), 1)


if __name__ == "__main__":
    unittest.main()
