## 1. Acquisition des données

Nous utilisons l'API play-by-play actuelle de la LNH. Pour chaque saison, nous lisons
le catalogue paginé des matchs, puis nous retenons les identifiants réguliers (`02`)
et des séries (`03`). Les identifiants des séries ne sont pas une simple suite
d'entiers. Le catalogue évite aussi de supposer un nombre fixe de matchs par saison.
Les matchs réellement terminés sont identifiés par `gameStateId=7` dans le
catalogue ; les rencontres de séries prévues mais devenues inutiles ne sont pas
des données manquantes et leurs identifiants non joués sont rapportés séparément.

La classe `NHLClient` vérifie les réponses avant de sauvegarder un fichier JSON
par match. Un appel suivant lit directement ce fichier. Les fichiers sont écrits
par remplacement atomique ; après une interruption, relancer l'acquisition permet
de reprendre à partir du cache. Les erreurs temporaires sont retentées et les
autres erreurs restent consignées dans les rapports d'acquisition.

Exemple, depuis la racine du projet :

```python
from ift3700 import NHLClient

client = NHLClient(data_dir="data/raw")
game = client.get_game(2017020001)
requests_before = client.request_count
same_game = client.get_game(2017020001)
assert client.request_count == requests_before
assert same_game == game

for year in range(2016, 2024):
    report = client.download_season(year)
    if not report["complete"]:
        raise RuntimeError(report["failed"])
```

Le chemin peut aussi être choisi par `NHL_DATA_DIR`. Les années 2016 à 2023
désignent les saisons **2016-17 à 2023-24**, inclusivement. Les données brutes
restent hors de Git, comme l'indique `.gitignore`.

Code complet du module d'acquisition :

```python
"""Télécharger les données brutes de la LNH, puis réutiliser le cache local.

La tâche 1 ne nécessite que la bibliothèque standard de Python.
Les URL et les sources sont documentées dans docs/sources.md.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from threading import Lock
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GAME_TYPES = {2: "regular", 3: "playoffs"}


class AcquisitionError(RuntimeError):
    """Erreur explicite : aucune donnée incorrecte ne devient un cache valide."""


class RequestLimiter:
    """Espacer les départs HTTP, même si plusieurs saisons sont acquises en parallèle."""

    def __init__(self, delay=0.25):
        self.delay = delay
        self.lock = Lock()
        self.last_request = None

    def wait(self):
        with self.lock:
            if self.last_request is not None:
                time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()


def season_id(start_year: int) -> int:
    """2017 -> 20172018 (saison 2017-18)."""
    if isinstance(start_year, bool) or not isinstance(start_year, int):
        raise ValueError("L'année de début doit être un entier, par exemple 2017.")
    if not 1917 <= start_year <= 2098:
        raise ValueError("Année de début de saison hors limites.")
    return int(f"{start_year}{start_year + 1}")


def game_info(game_id: int) -> tuple[int, int]:
    """Décomposer YYYYTTNNNN en année de début et type (2 ou 3)."""
    text = str(game_id)
    if not text.isdigit() or len(text) != 10:
        raise ValueError("game_id doit contenir exactement 10 chiffres.")
    year, kind = int(text[:4]), int(text[4:6])
    season_id(year)
    if kind not in GAME_TYPES:
        raise ValueError("Seuls les matchs réguliers (02) et les séries (03) sont retenus.")
    return year, kind


def _write_json(path: Path, value: object) -> None:
    """Remplacement atomique : une interruption ne laisse pas un JSON tronqué."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise AcquisitionError(f"Cache illisible : {path}. Utiliser --force pour le remplacer.") from error


class NHLClient:
    """Client avec cache, délai entre requêtes et reprises sur erreurs temporaires."""

    def __init__(
        self, data_dir: str | Path | None = None, *, offline: bool = False,
        delay: float = 0.25, retries: int = 3, timeout: float = 30,
        limiter: RequestLimiter | None = None,
    ):
        if delay < 0 or retries < 0 or timeout <= 0:
            raise ValueError("delay/retries doivent être positifs ou nuls ; timeout > 0.")
        self.data_dir = Path(data_dir or os.environ.get("NHL_DATA_DIR", "data/raw"))
        self.offline = offline
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.request_count = 0
        self.cache_hits = 0
        self._limiter = limiter or RequestLimiter(delay)

    def _get_json(self, url: str) -> dict:
        if self.offline:
            raise AcquisitionError(f"Mode hors ligne : requête interdite ({url}).")
        for attempt in range(self.retries + 1):
            self._limiter.wait()
            self.request_count += 1
            request = Request(url, headers={"User-Agent": "IFT3700-NHL-project/1.0", "Accept": "application/json"})
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    value = json.load(response)
                if not isinstance(value, dict):
                    raise AcquisitionError(f"L'API n'a pas renvoyé un objet JSON : {url}")
                return value
            except HTTPError as error:
                retryable = error.code == 429 or 500 <= error.code <= 599
                if not retryable or attempt == self.retries:
                    raise AcquisitionError(f"HTTP {error.code} : {url}") from error
                retry_after = error.headers.get("Retry-After", "") if error.headers else ""
                wait = min(30, float(retry_after)) if retry_after.isdigit() else min(30, 2 ** attempt)
            except (URLError, TimeoutError, OSError) as error:
                if attempt == self.retries:
                    raise AcquisitionError(f"Connexion impossible : {url} ({error})") from error
                wait = min(30, 2 ** attempt)
            except (ValueError, UnicodeError) as error:
                raise AcquisitionError(f"Réponse JSON invalide : {url}") from error
            time.sleep(wait)
        raise AssertionError("Boucle de reprise terminée sans résultat.")

    def game_path(self, game_id: int) -> Path:
        year, kind = game_info(game_id)
        return self.data_dir / str(season_id(year)) / GAME_TYPES[kind] / f"{game_id}.json"

    @staticmethod
    def _validate_game(data: object, game_id: int) -> dict:
        year, kind = game_info(game_id)
        if not isinstance(data, dict) or data.get("id") != game_id:
            raise AcquisitionError(f"Identifiant absent ou incorrect pour le match {game_id}.")
        if data.get("season") != season_id(year) or data.get("gameType") != kind:
            raise AcquisitionError(f"Saison ou type incohérent pour le match {game_id}.")
        if data.get("gameState") not in {"OFF", "FINAL"}:
            raise AcquisitionError(f"Le match {game_id} n'est pas terminé : {data.get('gameState')}.")
        if not isinstance(data.get("plays"), list) or not data["plays"]:
            raise AcquisitionError(f"Événements absents pour le match {game_id}.")
        if any(not isinstance(play, dict) or "eventId" not in play for play in data["plays"]):
            raise AcquisitionError(f"Structure d'événement invalide pour le match {game_id}.")
        return data

    def get_game(self, game_id: int, *, force: bool = False) -> dict:
        """Charger le JSON local, ou télécharger/valider/sauvegarder le match."""
        path = self.game_path(game_id)
        if path.exists() and not force:
            value = self._validate_game(_read_json(path), game_id)
            self.cache_hits += 1
            return value
        if self.offline:
            raise AcquisitionError(f"Match absent du cache : {path}")
        url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
        value = self._validate_game(self._get_json(url), game_id)
        _write_json(path, value)
        return value

    @staticmethod
    def _validate_catalog(data: object, year: int) -> list[int]:
        if not isinstance(data, dict) or data.get("season") != season_id(year):
            raise AcquisitionError("Saison du catalogue absente ou incorrecte.")
        rows, total = data.get("data"), data.get("total")
        if not isinstance(rows, list) or not isinstance(total, int) or total != len(rows) or total == 0:
            raise AcquisitionError("Catalogue vide ou incomplet.")
        identifiers = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), int):
                raise AcquisitionError("Identifiant invalide dans le catalogue.")
            identifier = row["id"]
            text = str(identifier)
            if len(text) != 10 or int(text[:4]) != year:
                raise AcquisitionError("Match d'une autre saison dans le catalogue.")
            if identifier in seen:
                raise AcquisitionError("Match dupliqué dans le catalogue.")
            seen.add(identifier)
            if int(text[4:6]) in GAME_TYPES:
                if not isinstance(row.get("gameStateId"), int):
                    raise AcquisitionError("État du match absent dans le catalogue.")
                # L'état 7 est le match terminé dans ce catalogue historique.
                # Les séries incluent aussi des matchs FUT qui n'ont jamais été nécessaires.
                if row["gameStateId"] == 7:
                    identifiers.append(identifier)
        if not identifiers or not any(str(g)[4:6] == "02" for g in identifiers):
            raise AcquisitionError("Le catalogue ne contient aucun match régulier.")
        return sorted(identifiers)

    def list_games(self, year: int, *, game_types: tuple[int, ...] = (2, 3), force: bool = False) -> list[int]:
        """Lire le catalogue paginé complet ; les IDs de séries ne sont pas consécutifs."""
        sid = season_id(year)
        if not game_types or any(kind not in GAME_TYPES for kind in game_types):
            raise ValueError("game_types doit contenir 2 et/ou 3.")
        path = self.data_dir / "catalogs" / f"{sid}.json"
        if path.exists() and not force:
            identifiers = self._validate_catalog(_read_json(path), year)
            self.cache_hits += 1
        else:
            if self.offline:
                raise AcquisitionError(f"Catalogue absent du cache : {path}")
            rows, seen, total = [], set(), None
            while total is None or len(rows) < total:
                query = urlencode({
                    "cayenneExp": f"season={sid}", "start": len(rows), "limit": 100,
                    "sort": json.dumps([{"property": "id", "direction": "ASC"}]),
                })
                page = self._get_json(f"https://api.nhle.com/stats/rest/en/game?{query}")
                batch, page_total = page.get("data"), page.get("total")
                if not isinstance(batch, list) or not isinstance(page_total, int) or page_total <= 0:
                    raise AcquisitionError(f"Catalogue de {sid} vide ou mal formé.")
                if total is not None and page_total != total:
                    raise AcquisitionError("Le catalogue a changé pendant la pagination ; relancer.")
                total = page_total
                if not batch or len(rows) + len(batch) > total:
                    raise AcquisitionError("Pagination du catalogue incomplète ou incohérente.")
                for row in batch:
                    if not isinstance(row, dict) or not isinstance(row.get("id"), int) or row["id"] in seen:
                        raise AcquisitionError("Pagination répétée ou identifiant invalide.")
                    seen.add(row["id"])
                rows.extend(batch)
            catalog = {
                "season": sid, "total": total, "data": rows,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "source": "https://api.nhle.com/stats/rest/en/game",
            }
            identifiers = self._validate_catalog(catalog, year)
            _write_json(path, catalog)
        return [g for g in identifiers if int(str(g)[4:6]) in game_types]

    def download_season(
        self, year: int, *, game_types: tuple[int, ...] = (2, 3),
        force: bool = False, limit: int | None = None,
        workers: int = 1,
    ) -> dict:
        """Télécharger/recharger chaque match et écrire un rapport d'exhaustivité."""
        if limit is not None and limit <= 0:
            raise ValueError("limit doit être positif.")
        if not 1 <= workers <= 8:
            raise ValueError("workers doit être entre 1 et 8.")
        identifiers = self.list_games(year, game_types=game_types, force=force)
        selected = identifiers if limit is None else identifiers[:limit]
        report = {
            "season": season_id(year), "game_types": list(game_types),
            "expected": len(identifiers), "selected": len(selected),
            "downloaded": [], "cached": [], "failed": {},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        catalog_path = self.data_dir / "catalogs" / f"{season_id(year)}.json"
        if catalog_path.exists():
            catalog = _read_json(catalog_path)
            report["unplayed_catalog_ids"] = [
                row["id"] for row in catalog["data"]
                if int(str(row["id"])[4:6]) in game_types and row["gameStateId"] != 7
            ]
        def fetch(identifier):
            local = self if workers == 1 else NHLClient(
                self.data_dir, offline=self.offline, delay=self.delay, retries=self.retries,
                timeout=self.timeout, limiter=self._limiter,
            )
            hits = local.cache_hits
            try:
                local.get_game(identifier, force=force)
                category = "cached" if local.cache_hits > hits else "downloaded"
                return identifier, category, None, local.request_count if workers > 1 else 0
            except AcquisitionError as error:
                return identifier, "failed", str(error), local.request_count if workers > 1 else 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for index, (identifier, category, error, requests) in enumerate(pool.map(fetch, selected), 1):
                self.request_count += requests
                if workers > 1 and category == "cached":
                    self.cache_hits += 1
                if category == "failed":
                    report["failed"][str(identifier)] = error
                    print(f"[{year} {index}/{len(selected)}] {identifier} : ÉCHEC ({error})", flush=True)
                    continue
                report[category].append(identifier)
                print(f"[{year} {index}/{len(selected)}] {identifier} : {category}", flush=True)
        report["complete"] = not report["failed"] and len(selected) == len(identifiers)
        # Un essai limité ne remplace pas le rapport d'une acquisition complète.
        scope = "_sample" if limit is not None else "_" + "-".join(map(str, game_types))
        _write_json(self.data_dir / "reports" / f"acquisition_{season_id(year)}{scope}.json", report)
        return report
```
