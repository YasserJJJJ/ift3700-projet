"""Cartes construites avec histogrammes NumPy et graphiques Plotly standards."""

from __future__ import annotations

import base64
from pathlib import Path

import numpy as np
import plotly.graph_objects as go

from .acquisition import season_id
from .analysis import regular_events
from .explorer import RINK


def physical_to_pixel(x, y, width, height):
    """Coordonnées patinoire -> image : origine en haut à gauche."""
    return (np.asarray(x) + 100) / 200 * (width - 1), (42.5 - np.asarray(y)) / 85 * (height - 1)


def map_rates(frame, exposure, year, *, bin_width=5):
    """Différence brute : tirs d'équipe/G_équipe - tirs de ligue/(2G_ligue)."""
    if bin_width <= 0 or 75 % bin_width or 85 % bin_width:
        raise ValueError("La taille de classe doit diviser 75 et 85 pieds, par exemple 5.")
    games = exposure.loc[exposure["season"].eq(season_id(year)) & exposure["game_type"].eq(2)].copy()
    if games.empty or games.duplicated(["game_id", "team_id"]).any():
        raise ValueError("Exposition absente ou dupliquée.")
    if not games.groupby("game_id").size().eq(2).all():
        raise ValueError("Chaque match doit contribuer exactement deux équipes.")
    selected, report = regular_events(frame, year)
    if not selected["game_id"].isin(games["game_id"]).all():
        raise ValueError("Les événements contiennent un match absent des dénominateurs.")
    missing = selected[["x_normalized", "y_normalized", "team_id"]].isna().any(axis=1)
    report["excluded_missing_coordinates_direction_or_team"] = int(missing.sum())
    selected = selected.loc[~missing].copy()
    invalid = selected["x_normalized"].abs().gt(100) | selected["y_normalized"].abs().gt(42.5)
    report["excluded_out_of_rink"] = int(invalid.sum())
    selected = selected.loc[~invalid].copy()
    outside = selected["x_normalized"].lt(25)
    report["outside_offensive_zone"] = int(outside.sum())
    selected = selected.loc[~outside].copy()
    report["included"] = len(selected)
    xedges = np.arange(25, 100 + bin_width, bin_width)
    yedges = np.arange(-42.5, 42.5 + bin_width, bin_width)

    def histogram(rows):
        return np.histogram2d(rows["x_normalized"].to_numpy(dtype=float), rows["y_normalized"].to_numpy(dtype=float),
                              bins=(xedges, yedges))[0].T

    league_games = games["game_id"].nunique()
    league_rate = histogram(selected) / (2 * league_games)
    result = {}
    for team_id, group in games.groupby("team_id"):
        labels = group["team"].dropna().unique()
        if len(labels) != 1:
            raise ValueError("Abréviation d'équipe manquante ou ambiguë.")
        team_events = selected.loc[selected["team_id"].eq(team_id)]
        team_games = group["game_id"].nunique()
        rate = histogram(team_events) / team_games
        result[str(labels[0])] = {
            "team_id": int(team_id), "games": int(team_games), "shots": len(team_events),
            "rate": rate, "excess": rate - league_rate,
        }
    report["league_games"] = int(league_games)
    report["league_team_hours"] = int(2 * league_games)
    return {"year": year, "xedges": xedges, "yedges": yedges, "league_rate": league_rate,
            "teams": result, "report": report}


def make_map_figure(rates, *, color_limit=None):
    """Une trace par équipe, menu déroulant ; même échelle entre saisons."""
    teams = sorted(rates["teams"])
    if not teams:
        raise ValueError("Aucune équipe disponible.")
    maximum = max(float(np.abs(team["excess"]).max()) for team in rates["teams"].values())
    bound = color_limit if color_limit is not None else maximum
    bound = max(float(bound), 1e-9)
    figure = go.Figure()
    x = (rates["xedges"][:-1] + rates["xedges"][1:]) / 2
    y = (rates["yedges"][:-1] + rates["yedges"][1:]) / 2
    for index, team in enumerate(teams):
        values = rates["teams"][team]
        figure.add_trace(go.Heatmap(
            x=x, y=y, z=values["excess"], zmin=-bound, zmax=bound, zmid=0,
            colorscale="RdBu_r", opacity=0.78, visible=index == 0, name=team,
            colorbar={"title": {"text": "Écart en tirs<br>/ heure-équipe"}},
            customdata=np.stack([values["rate"], rates["league_rate"]], axis=-1),
            hovertemplate=(team + "<br>x=%{x:.1f}, y=%{y:.1f} pieds<br>Équipe : %{customdata[0]:.3f}" +
                           "<br>Ligue : %{customdata[1]:.3f}<br>Écart : %{z:.3f} tirs/h-équipe<extra></extra>"),
        ))
    def title(team):
        values = rates["teams"][team]
        year = rates["year"]
        return f"{team} · {year}-{str(year+1)[2:]} · saison régulière<br><sup>{values['games']} matchs · {values['shots']} tirs en zone offensive · classes de 5 pieds</sup>"
    image_data = "data:image/png;base64," + base64.b64encode(RINK.read_bytes()).decode("ascii")
    figure.add_layout_image(dict(source=image_data, xref="x", yref="y", x=-100, y=42.5,
                                 sizex=200, sizey=85, sizing="stretch", layer="below"))
    figure.update_layout(
        title={"text": title(teams[0]), "x": 0.1}, height=680,
        margin={"l": 50, "r": 100, "t": 150, "b": 70},
        xaxis={"range": [25, 100], "title": "x normalisé (pieds)", "constrain": "domain", "showgrid": False},
        yaxis={"range": [-42.5, 42.5], "title": "y normalisé (pieds)", "scaleanchor": "x", "scaleratio": 1, "showgrid": False},
        updatemenus=[{"buttons": [{"label": team, "method": "update",
                                  "args": [{"visible": [value == team for value in teams]}, {"title.text": title(team)}]}
                                 for team in teams], "x": 0, "y": 1.15, "xanchor": "left", "yanchor": "top"}],
        annotations=[{"text": "Rouge : davantage de tirs que la ligue ; bleu : moins. Filets déserts inclus.",
                      "xref": "paper", "yref": "paper", "x": 0, "y": -0.12, "showarrow": False, "xanchor": "left"}],
    )
    return figure


def export_maps(frame, exposure, output_dir, *, include_dir=None):
    """Exporter une carte par saison, de 2016-17 à 2020-21 inclusivement."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    seasons = [map_rates(frame, exposure, year) for year in range(2016, 2021)]
    bound = max(float(np.abs(team["excess"]).max()) for rates in seasons for team in rates["teams"].values())
    if include_dir is not None:
        Path(include_dir).mkdir(parents=True, exist_ok=True)
    for rates in seasons:
        figure = make_map_figure(rates, color_limit=bound)
        name = f"shotmap_{season_id(rates['year'])}.html"
        # HTML autonome, fonctionne sans connexion Internet.
        figure.write_html(output / name, include_plotlyjs=True, full_html=True,
                          div_id=f"map-{rates['year']}", config={"responsive": True, "displaylogo": False})
        if include_dir is not None:
            figure.write_html(Path(include_dir) / name, include_plotlyjs=False, full_html=False,
                              div_id=f"map-{rates['year']}", config={"responsive": True, "displaylogo": False})
        summary = [{"team": label, "games": value["games"], "offensive_shots": value["shots"],
                    "offensive_shots_per_hour": float(value["rate"].sum()),
                    "excess_offensive_shots_per_hour": float(value["excess"].sum())}
                   for label, value in sorted(rates["teams"].items())]
        import pandas as pd
        pd.DataFrame(summary).to_csv(output / f"shotmap_{rates['year']}_summary.csv", index=False)
    return seasons
