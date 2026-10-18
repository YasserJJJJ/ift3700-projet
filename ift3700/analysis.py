"""Figures de la tâche 4 : dénominateurs explicites et exclusions rapportées."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .acquisition import season_id


def regular_events(frame, year):
    selected = frame.loc[frame["season"].eq(season_id(year)) & frame["game_type"].eq(2)].copy()
    if selected.empty:
        raise ValueError(f"Aucune donnée régulière pour {year}.")
    shootouts = selected["period_type"].eq("SO").fillna(False)
    return selected.loc[~shootouts].copy(), {"regular_events": len(selected), "excluded_shootouts": int(shootouts.sum())}


def wilson_interval(goals, shots):
    """Intervalle binomial de Wilson à 95 %, sans division par zéro."""
    goals, shots = np.asarray(goals, dtype=float), np.asarray(shots, dtype=float)
    p = np.divide(goals, shots, out=np.zeros_like(goals), where=shots > 0)
    z = 1.96
    denominator = 1 + z ** 2 / np.maximum(shots, 1)
    center = (p + z ** 2 / (2 * np.maximum(shots, 1))) / denominator
    radius = z * np.sqrt(p * (1 - p) / np.maximum(shots, 1) + z ** 2 / (4 * np.maximum(shots, 1) ** 2)) / denominator
    lower, upper = np.maximum(0, center - radius) * 100, np.minimum(1, center + radius) * 100
    lower[shots == 0], upper[shots == 0] = np.nan, np.nan
    return lower, upper


def _group_percent(frame, column):
    table = frame.groupby(column, observed=False)["is_goal"].agg(shots="size", goals="sum")
    table["goals"] = table["goals"].astype(int)
    table["goal_pct"] = 100 * table["goals"] / table["shots"].replace(0, np.nan)
    low, high = wilson_interval(table["goals"], table["shots"])
    table["ci_low"], table["ci_high"] = low, high
    return table


def shot_types(frame, year):
    selected, report = regular_events(frame, year)
    report["excluded_missing_shot_type"] = int(selected["shot_type"].isna().sum())
    selected = selected.dropna(subset=["shot_type"])
    table = _group_percent(selected, "shot_type").sort_values("shots", ascending=False)
    if table.empty:
        raise ValueError("Aucun type de tir disponible.")
    return table, report


def distance_table(frame, year, *, by_type=False, step=5):
    selected, report = regular_events(frame, year)
    requirements = ["distance_ft"] + (["shot_type"] if by_type else [])
    missing = selected[requirements].isna().any(axis=1)
    report["excluded_missing_required_fields"] = int(missing.sum())
    selected = selected.loc[~missing].copy()
    report["included"] = len(selected)
    bins = np.arange(0, 200 + step, step)
    selected["distance_bin"] = pd.cut(selected["distance_ft"].astype(float), bins=bins, right=False, include_lowest=True)
    if selected["distance_bin"].isna().any():
        raise ValueError("Une distance sort de la plage [0, 200[ pieds.")
    if by_type:
        grouped = selected.groupby(["shot_type", "distance_bin"], observed=False)["is_goal"].agg(shots="size", goals="sum")
        grouped["goals"] = grouped["goals"].astype(int)
        grouped["goal_pct"] = 100 * grouped["goals"] / grouped["shots"].replace(0, np.nan)
        return grouped, report
    grouped = _group_percent(selected, "distance_bin")
    grouped["midpoint_ft"] = [interval.mid for interval in grouped.index]
    return grouped, report


def make_simple_figures(frame, output_dir, *, year=2019, min_shots=30):
    """Exporter cinq figures et leurs agrégats, jamais inventer leurs résultats."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    reports = {}
    types, report = shot_types(frame, year)
    reports["shot_types"] = report
    types.to_csv(output / "shot_types.csv")
    figure, axis = plt.subplots(figsize=(11, 5))
    positions = np.arange(len(types))
    axis.bar(positions, types["shots"], color="#b5c5d5", label="Tirs cadrés, buts inclus")
    axis.bar(positions, types["goals"], color="#254c85", label="Buts")
    for position, (_, row) in zip(positions, types.iterrows()):
        axis.annotate(f"{row.goal_pct:.1f} %", (position, row.shots), ha="center", va="bottom", xytext=(0, 3), textcoords="offset points")
    axis.set(xticks=positions, xticklabels=types.index, ylabel="Nombre d'événements",
             title=f"Types de tirs · {year}-{str(year+1)[2:]} · saison régulière")
    axis.tick_params(axis="x", rotation=25)
    axis.margins(y=0.18)
    axis.legend()
    figure.tight_layout()
    figure.savefig(output / "shot_types.png", dpi=170)
    plt.close(figure)
    distance_tables = {}
    for current_year in [2018, 2019, 2020]:
        table, report = distance_table(frame, current_year)
        distance_tables[current_year] = table
        reports[f"distance_{current_year}"] = report
        table.to_csv(output / f"distance_{current_year}.csv")
        valid = table["shots"].ge(min_shots)
        reports[f"distance_{current_year}"]["bins_hidden_low_sample"] = int((~valid & table["shots"].gt(0)).sum())
        figure, (axis, counts) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
        visible = table.loc[valid]
        axis.errorbar(visible["midpoint_ft"], visible["goal_pct"],
                      yerr=np.maximum(0, np.vstack([visible["goal_pct"] - visible["ci_low"], visible["ci_high"] - visible["goal_pct"]])),
                      marker="o", markersize=4, capsize=2, color="#254c85")
        axis.set(ylabel="Buts / tirs cadrés (%)", title=f"Distance et conversion · {current_year}-{str(current_year+1)[2:]} · saison régulière")
        axis.set_ylim(bottom=0)
        axis.grid(alpha=0.2)
        counts.bar(table["midpoint_ft"], table["shots"], width=4.5, color="#b5c5d5")
        counts.set(xlabel="Distance au filet attaqué (pieds)", ylabel="Tirs", xlim=(0, 200))
        figure.text(0.02, 0.01, f"Classes de 5 pieds ; intervalles à 95 % ; points montrés si n ≥ {min_shots}. Filets déserts inclus.", fontsize=9)
        figure.tight_layout(rect=(0, 0.035, 1, 1))
        figure.savefig(output / f"distance_{current_year}.png", dpi=170)
        plt.close(figure)
    combined, report = distance_table(frame, year, by_type=True)
    reports["distance_by_type"] = report
    combined.to_csv(output / "distance_by_type.csv")
    percentages = combined["goal_pct"].unstack("distance_bin")
    sizes = combined["shots"].unstack("distance_bin")
    masked = np.ma.masked_where(sizes.to_numpy() < min_shots, percentages.to_numpy(dtype=float))
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad("#eeeeee")
    figure, axis = plt.subplots(figsize=(14, 5))
    # Échelle bornée au maximum affiché (arrondi à 10 %) pour garder les contrastes lisibles.
    vmax = max(10, 10 * np.ceil(masked.max() / 10)) if masked.count() else 100
    image = axis.imshow(masked, aspect="auto", origin="upper", cmap=cmap, vmin=0, vmax=vmax)
    columns = list(percentages.columns)
    axis.set(yticks=np.arange(len(percentages)), yticklabels=percentages.index,
             xticks=np.arange(0, len(columns), 4), xticklabels=[str(int(columns[i].left)) for i in range(0, len(columns), 4)],
             xlabel="Début de la classe de distance de 5 pieds", ylabel="Type de tir",
             title=f"Conversion selon distance et type · {year}-{str(year+1)[2:]} · n ≥ {min_shots}")
    figure.colorbar(image, ax=axis, label="Buts / tirs cadrés (%)")
    figure.text(0.02, 0.01, "Gris : classe avec moins de 30 tirs, ou sans tir. Filets déserts inclus.", fontsize=9)
    figure.tight_layout(rect=(0, 0.04, 1, 1))
    figure.savefig(output / "distance_by_type.png", dpi=170)
    plt.close(figure)
    return {"types": types, "distances": distance_tables, "combined": combined, "reports": reports}
