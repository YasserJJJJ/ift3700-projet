"""Commande : python -m ift3700.acquire --start-season 2016 --end-season 2023."""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor

from .acquisition import AcquisitionError, NHLClient, RequestLimiter


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Acquisition play-by-play, IFT3700.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--game", type=int, help="Télécharger un seul match.")
    scope.add_argument("--season", type=int, help="Année de début, par exemple 2017 pour 2017-18.")
    scope.add_argument("--start-season", type=int, help="Première année de début incluse.")
    parser.add_argument("--end-season", type=int, help="Dernière année de début incluse.")
    parser.add_argument("--game-types", nargs="+", choices=["regular", "playoffs"], default=["regular", "playoffs"])
    parser.add_argument("--data-dir", help="Sinon NHL_DATA_DIR, puis data/raw.")
    parser.add_argument("--offline", action="store_true", help="Utiliser uniquement le cache existant.")
    parser.add_argument("--force", action="store_true", help="Remplacer les caches par de nouvelles réponses validées.")
    parser.add_argument("--limit", type=int, help="Essai limité ; ne constitue pas l'acquisition complète.")
    parser.add_argument("--workers", type=int, default=4, help="Nombre de saisons traitées en parallèle, de 1 à 8.")
    parser.add_argument("--game-workers", type=int, default=4, help="Téléchargements par saison, de 1 à 8 ; délai HTTP partagé.")
    parser.add_argument("--request-interval", type=float, default=0.25, help="Délai global minimal entre départs HTTP (secondes).")
    args = parser.parse_args(argv)
    if args.start_season is not None and (args.end_season is None or args.end_season < args.start_season):
        parser.error("--start-season exige --end-season, supérieur ou égal au début.")
    if args.end_season is not None and args.start_season is None:
        parser.error("--end-season s'utilise avec --start-season.")
    if args.limit is not None and (args.limit <= 0 or args.game is not None):
        parser.error("--limit doit être positif et s'utilise avec une saison.")
    if args.force and args.offline:
        parser.error("--force et --offline ne peuvent pas être combinés.")
    if not 1 <= args.workers <= 8 or not 1 <= args.game_workers <= 8 or args.request_interval < 0.1:
        parser.error("Les nombres de workers doivent être entre 1 et 8 ; --request-interval doit être au moins 0.1.")
    client = NHLClient(args.data_dir, offline=args.offline)
    try:
        if args.game is not None:
            game = client.get_game(args.game, force=args.force)
            print(f"Match {game['id']} : {len(game['plays'])} événements. Fichier : {client.game_path(args.game)}")
            return 0
        years = [args.season] if args.season is not None else range(args.start_season, args.end_season + 1)
        kinds = tuple({"regular": 2, "playoffs": 3}[name] for name in dict.fromkeys(args.game_types))
        limiter = RequestLimiter(args.request_interval)
        def download(year):
            try:
                season_client = NHLClient(args.data_dir, offline=args.offline, limiter=limiter)
                report = season_client.download_season(year, game_types=kinds, force=args.force,
                                                       limit=args.limit, workers=args.game_workers)
                print(f"Saison {report['season']} : {len(report['downloaded'])} téléchargés, "
                      f"{len(report['cached'])} en cache, {len(report['failed'])} échecs, "
                      f"complet={report['complete']}.")
                return bool(report["failed"])
            except (AcquisitionError, ValueError) as error:
                print(f"Saison {year} : {error}", file=sys.stderr)
                return True
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(download, years))
        return 1 if any(results) else 0
    except (AcquisitionError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
