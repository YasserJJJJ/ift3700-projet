"""Exécuter le pipeline entier sur un corpus artificiel dans un dossier temporaire."""

import copy
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from fixtures import synthetic_game
from ift3700.acquisition import NHLClient, season_id
from ift3700.report import PROJECT, standings_from_games
from ift3700.run import main


class PipelineTests(unittest.TestCase):
    def test_eight_seasons_produce_all_figures_five_maps_and_blog(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "project"
            shutil.copytree(PROJECT, root, ignore=shutil.ignore_patterns("__pycache__", "outputs", "data", ".venv"))
            # Tester l'état sans capture indépendamment du blog de travail.
            # Seule la copie temporaire du test est modifiée.
            for capture in (root / "blog/public/figures").glob("widget.*"):
                if capture.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                    capture.unlink()
            client = NHLClient(root / "data/raw")
            for year in range(2016, 2024):
                identifiers = [int(f"{year}02{i:04d}") for i in [1, 2, 3]] + [int(f"{year}030111")]
                catalog = client.data_dir / "catalogs" / f"{season_id(year)}.json"
                catalog.parent.mkdir(parents=True, exist_ok=True)
                catalog.write_text(json.dumps({"season": season_id(year), "total": 4, "data": [{"id": g, "gameStateId": 7} for g in identifiers]}))
                labels = [("COL", 21, "BUF", 7), ("TBL", 14, "COL", 21), ("BUF", 7, "TBL", 14), ("COL", 21, "TBL", 14)]
                for identifier, (home_label, home_id, away_label, away_id) in zip(identifiers, labels):
                    game = synthetic_game(identifier)
                    original = game["plays"]
                    plays = []
                    for repetition in range(20):
                        for event in original:
                            value = copy.deepcopy(event)
                            value["eventId"] += 100 * repetition
                            owner = value.get("details", {}).get("eventOwnerTeamId")
                            if owner is not None:
                                value["details"]["eventOwnerTeamId"] = home_id if owner == 1 else away_id
                            plays.append(value)
                    game["plays"] = plays
                    game["homeTeam"].update(id=home_id, abbrev=home_label)
                    game["awayTeam"].update(id=away_id, abbrev=away_label)
                    path = client.game_path(identifier)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(game))
            # Les corpus artificiels restent dans le dossier temporaire, hors livrables.
            with patch("ift3700.run.PROJECT", root), patch("ift3700.report.PROJECT", root), \
                    redirect_stdout(io.StringIO()) as messages:
                status = main(["--data-dir", str(client.data_dir), "--regenerate-blog"])
            self.assertEqual(status, 0, messages.getvalue())
            self.assertEqual(len(list((root / "outputs/figures").glob("*.png"))), 5)
            self.assertEqual(len(list((root / "outputs/maps").glob("*.html"))), 5)
            article = (root / "blog/_posts/2026-10-08-milestone-1.md").read_text()
            self.assertNotIn("Brouillon : les résultats", article)
            self.assertEqual(article.count("{% include shotmap_"), 5)
            self.assertIn("Capture réelle", article)
            self.assertIn("COL", article)
            self.assertIn("BUF", article)
            self.assertIn("TBL", article)
            self.assertTrue((root / "outputs/standings_points.csv").exists())
            for fragment in (root / "blog/_includes").glob("shotmap_*.html"):
                self.assertIn("Plotly.newPlot", fragment.read_text())
            self.assertTrue((root / "outputs/article_avant_regeneration.md").exists())
            # Sans --regenerate-blog, un texte rédigé à la main n'est jamais écrasé.
            post = root / "blog/_posts/2026-10-08-milestone-1.md"
            post.write_text(article + "\nTexte rédigé à la main.\n")
            with patch("ift3700.run.PROJECT", root), patch("ift3700.report.PROJECT", root), \
                    redirect_stdout(io.StringIO()) as messages:
                status = main(["--data-dir", str(client.data_dir)])
            self.assertEqual(status, 0, messages.getvalue())
            self.assertIn("Texte rédigé à la main.", post.read_text())
            # Article existant + nouvelle capture JPEG : elle est convertie en widget.png,
            # le fichier que l'article référence, et le texte reste intact.
            from PIL import Image
            jpeg = Path(folder) / "nouvelle_capture.jpg"
            Image.new("RGB", (40, 30), "red").save(jpeg, format="JPEG")
            with patch("ift3700.run.PROJECT", root), patch("ift3700.report.PROJECT", root), \
                    redirect_stdout(io.StringIO()) as messages:
                status = main(["--data-dir", str(client.data_dir), "--widget-screenshot", str(jpeg)])
            self.assertEqual(status, 0, messages.getvalue())
            with Image.open(root / "blog/public/figures/widget.png") as converted:
                self.assertEqual((converted.format, converted.size), ("PNG", (40, 30)))
            self.assertFalse((root / "blog/public/figures/widget.jpg").exists())
            self.assertIn("Texte rédigé à la main.", post.read_text())


if __name__ == "__main__":
    unittest.main()
