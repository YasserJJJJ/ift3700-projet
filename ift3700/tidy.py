"""Transformer les tirs cadrés et les buts en une ligne par événement."""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import pandas as pd

from .acquisition import AcquisitionError, NHLClient


def _name(value):
    if isinstance(value, dict):
        return value.get("default") or value.get("fr")
    return value if isinstance(value, str) else None


def _number(value):
    # Une absence n'est pas zéro ; exclure également les booléens et les infinis.
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def _situation(code):
    """Code AGoalie-ASkaters-HSkaters-HGoalie, par exemple 1551."""
    text = str(code) if code is not None else ""
    if len(text) == 4 and text.isdigit() and text[0] in "01" and text[3] in "01":
        return tuple(map(int, text))
    return (None,) * 4


def _period_directions(game):
    """Direction offensive du domicile, par période, avec provenance."""
    directions = {}
    samples = defaultdict(list)
    zone_votes = defaultdict(list)
    side_votes = defaultdict(list)
    home = game["homeTeam"]["id"]
    away = game["awayTeam"]["id"]
    for play in game["plays"]:
        if play.get("periodDescriptor", {}).get("periodType") == "SO":
            continue
        period = play.get("periodDescriptor", {}).get("number")
        side = play.get("homeTeamDefendingSide")
        if side in {"left", "right"}:
            direction = 1 if side == "left" else -1
            side_votes[period].append(direction)
        details = play.get("details", {})
        owner = details.get("eventOwnerTeamId")
        x = _number(details.get("xCoord"))
        if play.get("typeDescKey") in {"shot-on-goal", "goal"} and x is not None and owner in {home, away}:
            samples[period].append(x if owner == home else -x)
            zone = details.get("zoneCode")
            if zone in {"O", "D"} and abs(x) >= 25:
                attack = (1 if x > 0 else -1) * (1 if zone == "O" else -1)
                zone_votes[period].append(attack if owner == home else -attack)
    conflicts = set()
    for period, votes in side_votes.items():
        if len(set(votes)) == 1:
            directions[period] = (votes[0], "api")
        else:
            conflicts.add(period)
    for period, votes in zone_votes.items():
        # Le côté fourni par l'API est parfois inversé pour une période entière
        # (ex. match 2019020256). Si au moins cinq zones O/D le contredisent
        # toutes, sans exception, la zone prime sur ce côté.
        current = directions.get(period)
        if current is not None and current[1] == "api" and len(votes) >= 5 and all(v == -current[0] for v in votes):
            directions[period] = (-current[0], "zone_code_overrides_api_side")
    for period, votes in zone_votes.items():
        if period not in directions:
            agreement = abs(sum(votes)) / len(votes)
            if agreement == 1:
                source = "api_zone_code_side_conflict" if period in conflicts else "api_zone_code"
                directions[period] = (1 if sum(votes) > 0 else -1, source)
            elif len(votes) >= 3 and agreement >= 0.8:
                source = "inferred_zone_majority_side_conflict" if period in conflicts else "inferred_zone_majority"
                directions[period] = (1 if sum(votes) > 0 else -1, source)
    for period, values in samples.items():
        # Une médiane ne résout pas des indications de zones contradictoires.
        if period not in directions and not zone_votes[period] and len(values) >= 3:
            median = float(np.median(values))
            if abs(median) >= 25:
                source = "inferred_period_median_side_conflict" if period in conflicts else "inferred_period_median"
                directions[period] = (1 if median > 0 else -1, source)
    for period in conflicts:
        directions.setdefault(period, (None, "unknown_side_conflict"))
    return directions


def game_to_frame(game: dict) -> pd.DataFrame:
    """Conserver tirs/buts et valeurs manquantes, puis normaliser les côtés."""
    home_id, away_id = game["homeTeam"]["id"], game["awayTeam"]["id"]
    teams = {home_id: game["homeTeam"].get("abbrev"), away_id: game["awayTeam"].get("abbrev")}
    players = {}
    for player in game.get("rosterSpots", []):
        first, last = _name(player.get("firstName")), _name(player.get("lastName"))
        players[player.get("playerId")] = " ".join(part for part in [first, last] if part) or None
    directions = _period_directions(game)
    rows = []
    for play in game["plays"]:
        event_type = play.get("typeDescKey")
        if event_type not in {"shot-on-goal", "goal"}:
            continue
        details = play.get("details", {})
        period_desc = play.get("periodDescriptor", {})
        period = period_desc.get("number")
        owner = details.get("eventOwnerTeamId")
        if owner not in teams:
            owner = None
        shooter_id = details.get("scoringPlayerId") if event_type == "goal" else details.get("shootingPlayerId")
        goalie_id = details.get("goalieInNetId")
        x, y = _number(details.get("xCoord")), _number(details.get("yCoord"))
        home_direction, direction_source = directions.get(period, (None, None))
        # Certains JSON changent de repère au milieu d'une période déclarée.
        # Le côté fourni pour cet événement prime sur une direction de période.
        side = play.get("homeTeamDefendingSide")
        if side in {"left", "right"} and direction_source != "zone_code_overrides_api_side":
            home_direction = 1 if side == "left" else -1
            direction_source = "api_event_side_conflict" if direction_source and "side_conflict" in direction_source else "api"
        direction = home_direction if owner == home_id else -home_direction if owner == away_id and home_direction else None
        # Contrôle final, quelle que soit la provenance : une direction qui place
        # un tir de zone offensive dans la moitié défensive (ou l'inverse) n'est
        # pas fiable. Les coordonnées brutes restent ; direction et distance
        # deviennent manquantes.
        if direction is not None and x is not None and abs(x) >= 25:
            zone = details.get("zoneCode")
            if (zone == "O" and direction * x < 0) or (zone == "D" and direction * x > 0):
                unresolved = "unknown_zone_conflict" if direction_source and direction_source.startswith("inferred") \
                    else "unknown_api_side_zone_conflict"
                direction, direction_source = None, unresolved
        xn, yn = (direction * x if direction is not None and x is not None else None,
                  direction * y if direction is not None and y is not None else None)
        valid_coords = xn is not None and yn is not None and abs(xn) <= 100 and abs(yn) <= 42.5
        distance = math.hypot(89 - xn, yn) if valid_coords else None
        ag, ask, hsk, hg = _situation(play.get("situationCode"))
        opponent_goalie = ag if owner == home_id else hg if owner == away_id else None
        own_sk, opponent_sk = (hsk, ask) if owner == home_id else (ask, hsk) if owner == away_id else (None, None)
        empty_net = details.get("emptyNet")
        if not isinstance(empty_net, bool):
            empty_net = opponent_goalie == 0 if opponent_goalie is not None else None
        # Tirs et buts : champ explicite s'il existe, sinon situationCode avec les deux gardiens présents.
        # Un filet vide (6 contre 5, pénalité différée, fusillade) laisse la catégorie manquante.
        strength = None
        explicit = details.get("strength")
        if isinstance(explicit, dict):
            explicit = explicit.get("code")
        if isinstance(explicit, str) and explicit.upper() in {"EV", "PP", "SH"}:
            strength = explicit.upper()
        elif own_sk is not None and opponent_sk is not None and ag == 1 and hg == 1:
            strength = "EV" if own_sk == opponent_sk else "PP" if own_sk > opponent_sk else "SH"
        strength_detail = f"{own_sk}c{opponent_sk}" if own_sk is not None and opponent_sk is not None else None
        rows.append({
            "game_id": game["id"], "event_id": play.get("eventId"), "season": game["season"],
            "game_type": game["gameType"], "game_date": game.get("gameDate"),
            "period": period, "period_type": period_desc.get("periodType"),
            "time_in_period": play.get("timeInPeriod"), "team_id": owner, "team": teams.get(owner),
            "event_type": event_type, "is_goal": event_type == "goal", "x": x, "y": y,
            "shooter_id": shooter_id, "shooter_name": players.get(shooter_id),
            "goalie_id": goalie_id, "goalie_name": players.get(goalie_id),
            "shot_type": details.get("shotType") or None, "empty_net": empty_net, "strength": strength,
            "strength_detail": strength_detail,
            "situation_code": play.get("situationCode"), "own_skaters": own_sk, "opponent_skaters": opponent_sk,
            "x_normalized": xn, "y_normalized": yn, "direction_source": direction_source,
            "distance_ft": distance,
        })
    columns = ["game_id", "event_id", "season", "game_type", "game_date", "period", "period_type",
               "time_in_period", "team_id", "team", "event_type", "is_goal", "x", "y", "shooter_id",
               "shooter_name", "goalie_id", "goalie_name", "shot_type", "empty_net", "strength", "strength_detail",
               "situation_code", "own_skaters", "opponent_skaters", "x_normalized", "y_normalized",
               "direction_source", "distance_ft"]
    frame = pd.DataFrame(rows, columns=columns)
    for column in ["game_id", "event_id", "season", "game_type", "period", "team_id", "shooter_id", "goalie_id", "own_skaters", "opponent_skaters"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Int64")
    for column in ["is_goal", "empty_net"]:
        frame[column] = frame[column].astype("boolean")
    for column in ["x", "y", "x_normalized", "y_normalized", "distance_ft"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Float64")
    if frame["event_id"].isna().any() or frame.duplicated(["game_id", "event_id"]).any():
        raise AcquisitionError(f"Clé d'événement manquante ou dupliquée, match {game['id']}.")
    return frame


def build_dataset(data_dir=None, years=range(2016, 2024)):
    """Exiger tous les matchs du catalogue ; retourner événements et exposition."""
    client = NHLClient(data_dir, offline=True)
    frames, matches = [], []
    for year in years:
        for identifier in client.list_games(year):
            game = client.get_game(identifier)
            frames.append(game_to_frame(game))
            for location in ["homeTeam", "awayTeam"]:
                team = game[location]
                matches.append({"game_id": game["id"], "season": game["season"], "game_type": game["gameType"],
                                "team_id": team["id"], "team": team.get("abbrev"), "home": location == "homeTeam",
                                "score": team.get("score"),
                                "opponent_score": game["awayTeam" if location == "homeTeam" else "homeTeam"].get("score"),
                                "last_period_type": game.get("periodDescriptor", {}).get("periodType")
                                    or game.get("gameOutcome", {}).get("lastPeriodType")})
    if not frames:
        raise AcquisitionError("Aucun match disponible.")
    shots = pd.concat(frames, ignore_index=True)
    exposure = pd.DataFrame(matches)
    if shots.duplicated(["game_id", "event_id"]).any() or exposure.duplicated(["game_id", "team_id"]).any():
        raise AcquisitionError("Matchs ou événements dupliqués dans l'ensemble des données.")
    return shots, exposure


def quality_report(frame: pd.DataFrame) -> dict:
    """Rapport sans suppression globale : chaque analyse filtrera ses colonnes."""
    return {
        "retained_events": len(frame), "goals": int(frame["is_goal"].sum()),
        "missing": {column: int(frame[column].isna().sum()) for column in frame.columns},
        "shootout_events": int(frame["period_type"].eq("SO").sum()),
        "orientation_sources": frame["direction_source"].fillna("unknown").value_counts().to_dict(),
    }
