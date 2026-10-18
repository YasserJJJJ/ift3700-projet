"""Explorateur des événements bruts avec ipywidgets et matplotlib."""

from __future__ import annotations

import html
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .acquisition import AcquisitionError, NHLClient, season_id

RINK = Path(__file__).resolve().parents[1] / "figures" / "nhl_rink.png"


def draw_event(game: dict, index: int):
    """Dessiner les coordonnées brutes ; ne pas changer les côtés du match."""
    event = game["plays"][index]
    details = event.get("details", {})
    figure, axis = plt.subplots(figsize=(11, 5))
    axis.imshow(plt.imread(RINK), extent=(-100, 100, -42.5, 42.5), origin="upper")
    x, y = details.get("xCoord"), details.get("yCoord")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)) and np.isfinite([x, y]).all():
        axis.scatter([x], [y], s=180, color="#162f89", edgecolors="white", linewidths=2, zorder=3)
        axis.annotate(f"({x}, {y})", (x, y), xytext=(8, 10), textcoords="offset points")
    else:
        axis.text(0, 0, "Cet événement ne contient pas de coordonnées.",
                  ha="center", bbox={"facecolor": "white", "alpha": 0.9})
    period = event.get("periodDescriptor", {}).get("number", "?")
    axis.set_title(f"Match {game['id']} · {event.get('typeDescKey', '?')} · "
                   f"P{period} {event.get('timeInPeriod', '?')} · événement {event.get('eventId', '?')}")
    axis.set(xlim=(-100, 100), ylim=(-42.5, 42.5), xlabel="x (pieds)", ylabel="y (pieds)")
    axis.set_aspect("equal")
    figure.tight_layout()
    return figure


def build_explorer(data_dir=None, *, offline=True):
    """Retourner un widget : saison -> type -> match -> tous ses événements."""
    import ipywidgets as widgets
    from IPython.display import HTML, display

    client = NHLClient(data_dir, offline=offline)
    season = widgets.Dropdown(options=[(f"{y}-{str(y+1)[2:]}", y) for y in range(2016, 2024)], description="Saison :")
    kind = widgets.Dropdown(options=[("Saison régulière", 2), ("Séries", 3)], description="Type :")
    game = widgets.Dropdown(options=[], description="Match :", layout=widgets.Layout(width="420px"))
    event = widgets.IntSlider(value=0, min=0, max=0, description="Événement :", continuous_update=False,
                              layout=widgets.Layout(width="700px"))
    previous = widgets.Button(description="← Précédent")
    following = widgets.Button(description="Suivant →")
    status = widgets.HTML()
    output = widgets.Output()
    state = {"game": None, "updating": False}

    def render(change=None):
        if state["updating"] or state["game"] is None:
            return
        data = state["game"]
        selected = data["plays"][event.value]
        with output:
            output.clear_output(wait=True)
            figure = draw_event(data, event.value)
            display(figure)
            plt.close(figure)
            display(HTML("<pre style='max-height:350px;overflow:auto'>" +
                         html.escape(json.dumps(selected, ensure_ascii=False, indent=2)) + "</pre>"))

    def load_game(change=None):
        if state["updating"] or game.value is None:
            return
        state["updating"] = True
        state["game"] = None
        try:
            data = client.get_game(game.value)
            state["game"] = data
            event.value = 0
            event.max = len(data["plays"]) - 1
            away = data.get("awayTeam", {}).get("abbrev", "Visiteurs")
            home = data.get("homeTeam", {}).get("abbrev", "Domicile")
            status.value = html.escape(f"{away} chez {home} · {data.get('gameDate', '')} · {len(data['plays'])} événements")
        except AcquisitionError as error:
            status.value = html.escape(str(error))
            output.clear_output()
        finally:
            state["updating"] = False
        render()

    def load_options(change=None):
        state["updating"] = True
        state["game"] = None
        try:
            identifiers = client.list_games(season.value, game_types=(kind.value,))
            game.options = [(str(identifier), identifier) for identifier in identifiers]
            if identifiers:
                game.value = identifiers[0]
            if not identifiers:
                status.value = "Aucun match pour cette sélection."
                output.clear_output()
        except AcquisitionError as error:
            game.options = []
            status.value = html.escape(str(error))
            output.clear_output()
        finally:
            state["updating"] = False
        load_game()

    season.observe(load_options, names="value")
    kind.observe(load_options, names="value")
    game.observe(load_game, names="value")
    event.observe(render, names="value")
    previous.on_click(lambda button: setattr(event, "value", max(event.min, event.value - 1)))
    following.on_click(lambda button: setattr(event, "value", min(event.max, event.value + 1)))
    load_options()
    return widgets.VBox([widgets.HBox([season, kind]), game, status, event,
                         widgets.HBox([previous, following]), output])
