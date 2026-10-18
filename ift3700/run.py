"""Après acquisition : créer le dataframe, les figures, les cartes et le blog."""

import argparse
import json
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

from .acquisition import AcquisitionError
from .analysis import make_simple_figures
from .report import PROJECT, standings_from_games, write_blog
from .shotmaps import export_maps
from .tidy import build_dataset, quality_report
from .standings import verify_points
from .preview import make_preview


def main(argv=None):
    parser = argparse.ArgumentParser(description="Calculer les livrables réels du jalon 1.")
    parser.add_argument("--data-dir", help="Sinon NHL_DATA_DIR, puis data/raw.")
    parser.add_argument("--widget-screenshot", help="Capture réelle du notebook à intégrer au blog.")
    parser.add_argument("--regenerate-blog", action="store_true",
                        help="Réécrire l'article à partir du modèle automatique. Sans cette option, "
                             "un article existant (rédigé à la main) n'est jamais modifié.")
    args = parser.parse_args(argv)
    output = PROJECT / "outputs"
    post_path = PROJECT / "blog/_posts/2026-10-08-milestone-1.md"
    try:
        print("Lecture et validation de toutes les saisons 2016-17 à 2023-24…", flush=True)
        frame, exposure = build_dataset(args.data_dir)
        output.mkdir(exist_ok=True)
        frame.to_csv(output / "shots.csv", index=False)
        exposure.to_csv(output / "team_games.csv", index=False)
        (output / "data_quality.json").write_text(json.dumps(quality_report(frame), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{len(frame)} événements retenus, {exposure['game_id'].nunique()} matchs.", flush=True)
        simple = make_simple_figures(frame, output / "figures")
        for image in (output / "figures").glob("*.png"):
            target = PROJECT / "blog/public/figures" / image.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(image, target)
        maps = export_maps(frame, exposure, output / "maps", include_dir=PROJECT / "blog/_includes")
        reports = {"simple": simple["reports"], "maps": {str(rates["year"]): rates["report"] for rates in maps}}
        (output / "analysis_exclusions.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
        standings_from_games(exposure).to_csv(output / "standings_points.csv", index=False)
        standings_check = verify_points(exposure, args.data_dir)
        (output / "standings_verification.json").write_text(json.dumps(standings_check, ensure_ascii=False, indent=2), encoding="utf-8")
        if post_path.exists() and not args.regenerate_blog:
            # L'article est rédigé à la main : seules les figures et les cartes sont mises à jour.
            if args.widget_screenshot is not None:
                screenshot = Path(args.widget_screenshot)
                if screenshot.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                    raise ValueError("La capture du widget doit être PNG ou JPEG.")
                # L'article référence toujours widget.png : une capture JPEG est
                # réellement convertie en PNG (pas un simple renommage).
                from PIL import Image
                with Image.open(screenshot) as image:
                    image.save(PROJECT / "blog/public/figures/widget.png", format="PNG")
            post = post_path
            print(f"Article conservé tel quel (rédigé à la main) : {post}")
            print("Pour le réécrire automatiquement : --regenerate-blog (une copie est d'abord sauvegardée).")
        else:
            if post_path.exists():
                backup = output / "article_avant_regeneration.md"
                shutil.copy2(post_path, backup)
                print(f"Copie de l'ancien article : {backup}")
            post = write_blog(frame, exposure, simple, maps, screenshot=args.widget_screenshot)
        preview = make_preview(PROJECT / "blog")
        print(f"Figures et cartes générées ; article : {post}")
        print(f"Aperçu HTML local : {preview}")
        if not list((PROJECT / "blog/public/figures").glob("widget.*")):
            print("La capture du widget reste à ajouter : relancer avec --widget-screenshot chemin/capture.png.")
        print("Relire les observations et renseigner les membres avant la vérification finale et la remise.")
        return 0
    except (AcquisitionError, ValueError, OSError) as error:
        print(f"Pipeline interrompu : {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
