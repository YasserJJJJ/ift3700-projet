"""Contrôler les classements reconstitués avec les statistiques officielles."""

import json
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd

from .acquisition import AcquisitionError, NHLClient, _read_json, _write_json, season_id
from .report import standings_from_games


def download_summaries(data_dir=None, years=range(2016, 2024)):
    """Huit petites réponses de statistiques officielles, également mises en cache."""
    client = NHLClient(data_dir)
    for year in years:
        sid = season_id(year)
        path = client.data_dir / "standings" / f"{sid}.json"
        if path.exists():
            _validate_summary(_read_json(path), sid)
            continue
        query = urlencode({"isAggregate": "false", "isGame": "false", "start": 0, "limit": 100,
                           "cayenneExp": f"seasonId={sid} and gameTypeId=2"})
        value = client._get_json("https://api.nhle.com/stats/rest/en/team/summary?" + query)
        _validate_summary(value, sid)
        _write_json(path, value)
        print(f"Classement officiel {sid} : {len(value['data'])} équipes.", flush=True)


def _validate_summary(value, sid):
    if not isinstance(value, dict) or not value.get("data") or value.get("total") != len(value["data"]):
        raise AcquisitionError("Statistiques officielles vides ou incomplètes.")
    required = ["teamId", "seasonId", "gamesPlayed", "wins", "losses", "otLosses", "points"]
    for row in value["data"]:
        if any(not isinstance(row.get(key), int) for key in required) or row["seasonId"] != sid:
            raise AcquisitionError("Statistiques officielles : saison ou valeurs invalides.")
        if row["gamesPlayed"] != row["wins"] + row["losses"] + row["otLosses"] or row["points"] != 2 * row["wins"] + row["otLosses"]:
            raise AcquisitionError("Statistiques officielles incohérentes.")
    return value["data"]


def verify_points(exposure, data_dir=None):
    """Comparer toutes les équipes ; le pipeline reste hors ligne."""
    client = NHLClient(data_dir, offline=True)
    seasons = sorted(exposure["season"].unique())
    paths = [client.data_dir / "standings" / f"{sid}.json" for sid in seasons]
    if not all(path.exists() for path in paths):
        return {"performed": False, "reason": "Caches officiels absents ; python -m ift3700.standings permet de les télécharger."}
    official = pd.concat([pd.DataFrame(_validate_summary(_read_json(path), int(sid))) for path, sid in zip(paths, seasons)])
    computed = standings_from_games(exposure)
    identifiers = exposure[["season", "team", "team_id"]].drop_duplicates()
    computed = computed.merge(identifiers, on=["season", "team"], validate="one_to_one")
    joined = computed.merge(official, left_on=["season", "team_id"], right_on=["seasonId", "teamId"],
                            suffixes=("_computed", "_official"), validate="one_to_one")
    if len(joined) != len(computed) or len(joined) != len(official):
        raise AcquisitionError("Équipes absentes lors de la comparaison du classement officiel.")
    fields = {"games": "gamesPlayed", "wins_computed": "wins_official", "losses_computed": "losses_official",
              "ot_losses": "otLosses", "points_computed": "points_official"}
    for left, right in fields.items():
        if not joined[left].eq(joined[right]).all():
            raise AcquisitionError(f"Le classement reconstitué ne correspond pas aux statistiques officielles : {left}.")
    return {"performed": True, "team_seasons_checked": len(joined), "fields_checked": list(fields), "all_equal": True}


if __name__ == "__main__":
    download_summaries()
