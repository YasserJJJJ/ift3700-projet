"""Petits matchs entièrement artificiels pour vérifier les calculs."""

from ift3700.acquisition import game_info, season_id


def synthetic_game(identifier=2017020001):
    year, kind = game_info(identifier)
    return {
        "id": identifier, "season": season_id(year), "gameType": kind, "gameState": "OFF",
        "gameDate": f"{year}-10-05", "periodDescriptor": {"number": 3, "periodType": "REG"},
        "homeTeam": {"id": 1, "abbrev": "AAA", "score": 2},
        "awayTeam": {"id": 2, "abbrev": "BBB", "score": 1},
        "rosterSpots": [{"playerId": 11, "firstName": {"default": "Test"}, "lastName": {"default": "Shooter"}},
                        {"playerId": 22, "firstName": {"default": "Test"}, "lastName": {"default": "Goalie"}}],
        "plays": [
            {"eventId": 1, "typeDescKey": "faceoff", "periodDescriptor": {"number": 1, "periodType": "REG"},
             "timeInPeriod": "00:00", "homeTeamDefendingSide": "left"},
            {"eventId": 2, "typeDescKey": "shot-on-goal", "periodDescriptor": {"number": 1, "periodType": "REG"},
             "timeInPeriod": "00:10", "situationCode": "1551", "homeTeamDefendingSide": "left",
             "details": {"eventOwnerTeamId": 1, "xCoord": 79, "yCoord": 0, "shootingPlayerId": 11,
                         "goalieInNetId": 22, "shotType": "wrist"}},
            {"eventId": 3, "typeDescKey": "goal", "periodDescriptor": {"number": 1, "periodType": "REG"},
             "timeInPeriod": "01:00", "situationCode": "1451", "homeTeamDefendingSide": "left",
             "details": {"eventOwnerTeamId": 1, "xCoord": 89, "yCoord": 10, "scoringPlayerId": 11,
                         "goalieInNetId": 22, "shotType": "wrist"}},
            {"eventId": 4, "typeDescKey": "shot-on-goal", "periodDescriptor": {"number": 2, "periodType": "REG"},
             "timeInPeriod": "00:10", "situationCode": "1551", "homeTeamDefendingSide": "right",
             "details": {"eventOwnerTeamId": 1, "xCoord": -79, "yCoord": -5, "shootingPlayerId": 11, "shotType": "slap"}},
            {"eventId": 5, "typeDescKey": "shot-on-goal", "periodDescriptor": {"number": 2, "periodType": "REG"},
             "timeInPeriod": "00:20", "homeTeamDefendingSide": "right", "details": {"eventOwnerTeamId": 2}},
            {"eventId": 6, "typeDescKey": "missed-shot", "periodDescriptor": {"number": 2, "periodType": "REG"}},
            {"eventId": 7, "typeDescKey": "blocked-shot", "periodDescriptor": {"number": 2, "periodType": "REG"}},
        ],
    }
