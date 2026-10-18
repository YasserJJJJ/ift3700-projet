"""Assembler les réponses du jalon dans un article Jekyll unique."""

from pathlib import Path
import shutil

import pandas as pd

from .analysis import regular_events
from .acquisition import season_id

PROJECT = Path(__file__).resolve().parents[1]

# Annotation historique, confirmée par le compte rendu officiel de la LNH.
# Règle 84.2 : retirer volontairement le gardien en OT peut faire perdre le point.
# Le seul code de situation ne permet pas d'écarter une pénalité différée.
# On annote donc le cas confirmé, plutôt que tous les buts en filet désert.
# https://www.nhl.com/news/vegas-golden-knights-minnesota-wild-game-recap-march-30
OT_POINT_FORFEITS = {(2023021166, 30)}


def _table(frame):
    return '<div class="table-scroll">' + frame.to_html(index=False, escape=True, na_rep="—", float_format=lambda x: f"{x:.2f}") + '</div>'


def standings_from_games(exposure):
    """Points de saison régulière ; classement par points sans bris d'égalité."""
    selected = exposure.loc[exposure["game_type"].eq(2)].copy()
    if selected[["score", "opponent_score", "last_period_type"]].isna().any().any():
        raise ValueError("Métadonnées insuffisantes pour reconstituer les points du classement.")
    if selected["score"].eq(selected["opponent_score"]).any():
        raise ValueError("Un match terminé a des scores égaux : vérifier le JSON brut.")
    selected["wins"] = selected["score"].gt(selected["opponent_score"]).astype(int)
    forfeited = pd.Series(False, index=selected.index)
    for game_id, team_id in OT_POINT_FORFEITS:
        mask = selected["game_id"].eq(game_id) & selected["team_id"].eq(team_id)
        if mask.any() and not (selected.loc[mask, "wins"].eq(0) & selected.loc[mask, "last_period_type"].eq("OT")).all():
            raise ValueError("L'annotation d'un point perdu en prolongation ne correspond pas au match.")
        forfeited |= mask
    selected["ot_point_forfeits"] = forfeited.astype(int)
    selected["ot_losses"] = (selected["wins"].eq(0) & selected["last_period_type"].isin(["OT", "SO"]) & ~forfeited).astype(int)
    selected["points"] = selected["wins"] * 2 + selected["ot_losses"]
    table = selected.groupby(["season", "team"]).agg(games=("game_id", "nunique"), wins=("wins", "sum"),
                                                       ot_losses=("ot_losses", "sum"), points=("points", "sum"),
                                                       ot_point_forfeits=("ot_point_forfeits", "sum"))
    table["losses"] = table["games"] - table["wins"] - table["ot_losses"]
    table["points_pct"] = table["points"] / (2 * table["games"]) * 100
    table["rank_by_points"] = table.groupby(level="season")["points"].rank(method="min", ascending=False).astype(int)
    return table.reset_index()


def _map_discussion(rates, team):
    import numpy as np
    info = rates["teams"].get(team)
    if info is None:
        return f"{team} est absent des données de cette saison."
    excess = info["excess"]
    high = np.unravel_index(np.argmax(excess), excess.shape)
    low = np.unravel_index(np.argmin(excess), excess.shape)
    def location(index):
        row, col = index
        return f"x ∈ [{rates['xedges'][col]:g}, {rates['xedges'][col+1]:g}], y ∈ [{rates['yedges'][row]:g}, {rates['yedges'][row+1]:g}]"
    return (f"En {rates['year']}-{str(rates['year']+1)[2:]}, {team} produit {info['rate'].sum():.2f} tirs cadrés "
            f"par heure-équipe dans la zone offensive, soit un écart total de {excess.sum():+.2f} avec la ligue. "
            f"La classe la plus positive est {location(high)} ({excess[high]:+.3f} tirs/heure-équipe), "
            f"et la plus négative est {location(low)} ({excess[low]:+.3f}). "
            "Ces extrêmes décrivent des classes spatiales ; une seule classe peut être sensible à l'échantillonnage.")


def _central_rate(rates, team):
    """Classes centrées près du filet : x de 70 à 90, y de -17.5 à 17.5 pieds."""
    import numpy as np
    centers_x = (rates["xedges"][:-1] + rates["xedges"][1:]) / 2
    centers_y = (rates["yedges"][:-1] + rates["yedges"][1:]) / 2
    region = np.ix_(np.abs(centers_y) <= 15, (centers_x >= 70) & (centers_x < 90))
    return float(rates["teams"][team]["rate"][region].sum())


def acquisition_text():
    code = (PROJECT / "ift3700/acquisition.py").read_text(encoding="utf-8")
    return f"""## 1. Acquisition des données

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
{code.rstrip()}
```
"""


def feature_discussion():
    return """### 3.1. Force réelle sur la glace

L'API actuelle peut fournir un `situationCode` sur les tirs et les buts : ses
quatre chiffres décrivent la présence du gardien visiteur, le nombre de patineurs
visiteurs, le nombre de patineurs du domicile et la présence du gardien du
domicile. Nous conservons les nombres de patineurs lorsqu'ils sont disponibles.
Pour un but, en l'absence d'un champ explicite EV/PP/SH, comparer les patineurs
permet une classification lorsque les deux gardiens sont présents. Si un gardien
est retiré, cette comparaison ne suffit pas à identifier une pénalité : la
classification reste manquante plutôt que de confondre filet désert et avantage.

Pour les événements sans ce code, on pourrait parcourir **tous** les événements
chronologiquement et maintenir les pénalités actives avec leurs durées. Il faut
tenir compte des pénalités coïncidentes, des doubles mineures, des majeures, de
la fin éventuelle d'une mineure après un but en avantage, des changements de
période et des règles de prolongation. Les retraits de gardien ajoutent une
autre difficulté. Les événements ne décrivent pas nécessairement chaque
changement de joueur : sans état fiable ou données de présences, certaines
forces exactes doivent rester inconnues. Une reconstruction supplémentaire
fondée sur les pénalités n'est pas implémentée pour ce jalon.

### 3.2. Caractéristiques supplémentaires possibles

- **Distance au filet** : après normalisation du sens d'attaque, mesurer la
  distance euclidienne au but situé en `(89, 0)` pieds. Cette caractéristique
  est déjà utilisée pour les figures ; sans coordonnées ou direction fiable,
  elle reste manquante.
- **Angle du tir** : calculer l'angle par rapport à l'axe du filet à partir des
  coordonnées normalisées, en traitant explicitement les tirs derrière la ligne
  de but. Il pourrait distinguer deux tirs aussi proches mais différemment orientés.
- **Rebond potentiel** : repérer un second tir de la même équipe quelques secondes
  après un premier tir cadré, dans la même période, sans interruption entre les
  deux. La fenêtre temporelle doit être déclarée et validée ; ce serait un proxy,
  car le jeu décrit ne prouve pas toujours qu'il s'agit d'un rebond.
- **Contre-attaque potentielle** : repérer une récupération ou une séquence allant
  rapidement de la zone défensive vers un tir offensif. Les événements sont
  espacés et la possession n'est pas observée en continu, donc il faudrait
  présenter cette variable comme un indicateur approximatif.
"""


def write_blog(frame=None, exposure=None, simple=None, maps=None, *, screenshot=None):
    blog = PROJECT / "blog"
    assets = blog / "public/figures"
    assets.mkdir(parents=True, exist_ok=True)
    header = '---\nlayout: post\ntitle: "Jalon 1 — Exploration des événements de la LNH"\ndate: 2026-10-08\nmaps: true\n---\n\n'
    intro = "Ce jalon couvre l'acquisition, un explorateur interactif, les données ordonnées et les visualisations du volet **IFT3700**.\n\n"
    ready = all(value is not None for value in [frame, exposure, simple, maps])
    if not ready:
        intro += ('<div class="pending">Brouillon : les résultats des données réelles ne sont pas encore calculés. '
                  'Exécuter le téléchargement complet, puis <code>python3 -m ift3700.run</code>. '
                  'Les exemples artificiels des tests ne constituent pas les résultats du devoir.</div>\n\n')
    text = header + intro + acquisition_text()
    text += """\n## 2. Outil de débogage interactif

L'outil permet de choisir la saison, le type de match, le match et l'événement.
Il dessine les coordonnées brutes sur la patinoire fournie et montre le JSON de
l'événement, y compris lorsque ses coordonnées sont absentes.

```python
from IPython.display import display
from ift3700.explorer import build_explorer
display(build_explorer("data/raw", offline=True))
```

"""
    if screenshot is not None:
        screenshot = Path(screenshot)
        if screenshot.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            raise ValueError("La capture du widget doit être PNG ou JPEG.")
        shutil.copy2(screenshot, assets / ("widget" + screenshot.suffix.lower()))
    screenshots = sorted(assets.glob("widget.*"))
    if screenshots:
        text += f"![Capture de l'outil interactif]({{{{ '/public/figures/{screenshots[0].name}' | relative_url }}}})\n\n"
    else:
        text += '<div class="pending">Capture réelle de l’explorateur à ajouter après son exécution dans Jupyter.</div>\n\n'
    text += "Code de l'outil :\n\n```python\n" + (PROJECT / "ift3700/explorer.py").read_text().rstrip() + "\n```\n\n"
    text += """## 3. Données ordonnées

Une ligne correspond à un tir cadré (`shot-on-goal`) ou un but (`goal`), avec une
clé unique `(game_id, event_id)`. Les tirs manqués et bloqués sont exclus. Les noms
des joueurs sont joints aux identifiants via `rosterSpots` ; une information
absente reste manquante. Il n'y a pas de suppression globale des événements
incomplets : chaque analyse ne retire que les lignes dont elle a besoin.

Les colonnes `x` et `y` conservent les coordonnées originales. Les coordonnées
normalisées placent le filet attaqué à droite. Le côté du domicile est pris dans
`homeTeamDefendingSide` pour chaque événement. Certains JSON changent de repère
au milieu d'une période déclarée : nous utilisons alors le côté de l'événement
et signalons le conflit dans la provenance. Si ce champ manque, un côté de
période cohérent est utilisable. Sinon, les zones `O` et `D`
des tirs/buts indiquent le côté attaqué : un tir en zone offensive se trouve
du côté du filet adverse, et un tir en zone défensive du côté du filet de
l'équipe qui tire. Nous retenons les votes unanimes d'une période ; une majorité
d'au moins 90 % est également utilisable si au moins trois votes existent,
mais elle est marquée comme inférée. Un événement contredisant cette majorité
conserve une direction inconnue. En dernier recours, seulement en l'absence
de tout vote de zone, une autre inférence exige au moins trois tirs cadrés/buts dans la période et
une médiane des abscisses, ajustées selon l'équipe, éloignée d'au moins 25 pieds
du centre. Sinon, la direction et la distance restent inconnues. Une rotation
de 180° change le signe de **x et y**. Les tirs de fusillade restent dans le
tableau mais sont exclus des analyses agrégées. Les sources de direction et
les cas de métadonnées contradictoires sont conservés dans `direction_source`
et décomptés à la fin de l'article.

Extrait `head(10)` :

"""
    text += _table(frame.head(10)) + "\n\n" if ready else "*Le tableau sera inséré à partir des matchs réels.*\n\n"
    text += feature_discussion()
    text += "\n## 4. Visualisations simples\n\n"
    text += """Nous analysons la saison régulière et excluons les fusillades. Un « tir » dans
le dénominateur est un tir cadré, **but inclus** : le taux vaut
`100 × buts / (tirs arrêtés + buts)`. Les filets déserts sont inclus et peuvent
modifier les taux, notamment à grande distance. Ces associations décrivent les
événements observés ; elles ne mesurent pas seules une probabilité causale.

### 4.1. Types de tirs

Les barres superposent les buts au total des tirs cadrés en 2019-20. Elles rendent
les volumes directement comparables ; les pourcentages affichés distinguent la
fréquence d'un type de sa conversion.

"""
    if ready:
        types = simple["types"]
        common = types["shots"].idxmax()
        dangerous = types["goal_pct"].idxmax()
        text += (f"Le type le plus courant est **{common}** ({int(types.loc[common, 'shots'])} tirs). "
                 f"Le taux de conversion observé le plus élevé est celui de **{dangerous}** "
                 f"({types.loc[dangerous, 'goal_pct']:.2f} %, {int(types.loc[dangerous, 'goals'])} buts sur "
                 f"{int(types.loc[dangerous, 'shots'])} tirs). La taille de l'échantillon doit être considérée "
                 "avant de généraliser ce classement.\n\n")
        text += "![Volumes par type de tir]({{ '/public/figures/shot_types.png' | relative_url }})\n\n"
        text += _table(types.reset_index()) + "\n\n"
    else:
        text += "*Figure, type le plus courant et type au meilleur taux : en attente des données.*\n\n"
    text += """### 4.2. Distance et chance de but, de 2018-19 à 2020-21

Les courbes montrent les taux par classes de 5 pieds et leurs intervalles
binomiaux de Wilson à 95 %. Les effectifs sont affichés sous chaque courbe ; les
points avec moins de 30 tirs ne sont pas tracés, mais restent dans les agrégats.
Cette figure montre la forme de la relation et les endroits où les estimations
sont peu précises. La distance est `sqrt((89 - x_normalisé)^2 + y_normalisé^2)`.

"""
    if ready:
        comparisons = []
        for year in [2018, 2019, 2020]:
            text += f"![Distance et conversion {year}-{str(year+1)[2:]}]({{{{ '/public/figures/distance_{year}.png' | relative_url }}}})\n\n"
            subset, _ = regular_events(frame, year)
            for low, high in [(0, 20), (20, 40), (40, 60), (60, 200)]:
                rows = subset.loc[subset["distance_ft"].ge(low) & subset["distance_ft"].lt(high)]
                comparisons.append({"saison": f"{year}-{str(year+1)[2:]}", "distance (pieds)": f"[{low}, {high}[",
                                    "tirs": len(rows), "buts": int(rows["is_goal"].sum()),
                                    "conversion (%)": float(rows["is_goal"].mean() * 100) if len(rows) else float("nan")})
        comparison = pd.DataFrame(comparisons)
        text += _table(comparison) + "\n\n"
        nearby = comparison.loc[comparison["distance (pieds)"].eq("[0, 20["), "conversion (%)"]
        text += (f"Pour les tirs à moins de 20 pieds, l'écart entre le plus petit et le plus grand taux "
                 f"des trois saisons est de **{nearby.max() - nearby.min():.2f} points de pourcentage**. "
                 "Le tableau permet de comparer les saisons à distances semblables, plutôt que de comparer "
                 "seulement leur taux global. Les intervalles et les volumes aident à juger la portée des écarts ; "
                 "la sélection des tirs, les équipes, les filets déserts et le calendrier peuvent aussi changer. "
                 "Les trois courbes présentent une baisse marquée du taux jusqu'à environ 60 pieds, "
                 "puis une partie éloignée plus irrégulière et moins précise. La forme générale demeure "
                 "semblable entre ces saisons ; les variations visibles à longue distance ont de grands "
                 "intervalles et ne suffisent pas à établir un changement durable.\n\n")
        decreases = []
        for year in [2018, 2019, 2020]:
            rows = comparison.loc[comparison["saison"].eq(f"{year}-{str(year+1)[2:]}")]
            near = rows.loc[rows["distance (pieds)"].eq("[0, 20["), "conversion (%)"].iloc[0]
            far = rows.loc[rows["distance (pieds)"].eq("[40, 60["), "conversion (%)"].iloc[0]
            decreases.append(near > far)
        if all(decreases):
            text += ("Dans chacune des trois saisons, le taux des tirs à moins de 20 pieds est supérieur "
                     "à celui des tirs entre 40 et 60 pieds. La relation générale entre proximité et "
                     "conversion persiste donc sur cette comparaison. La courbe n'est pas nécessairement "
                     "monotone : les tirs éloignés dans un filet désert et les petits effectifs peuvent "
                     "produire des remontées à grande distance.\n\n")
    else:
        text += "*Les trois courbes et leur comparaison chiffrée seront calculées après acquisition.*\n\n"
    text += """### 4.3. Distance et type de tir

La carte de conversion de 2019-20 croise le type de tir et la classe de distance.
Une case grise contient moins de 30 tirs ou aucun tir. Cette représentation permet
de comparer des types à distance semblable ; le taux global d'un type peut refléter
les positions d'où il est utilisé. Les effectifs par case sont fournis dans le CSV.

"""
    if ready:
        text += "![Conversion par distance et type]({{ '/public/figures/distance_by_type.png' | relative_url }})\n\n"
        eligible = simple["combined"].loc[simple["combined"]["shots"].ge(30)]
        if not eligible.empty:
            label = eligible["goal_pct"].idxmax()
            best = eligible.loc[label]
            text += (f"Parmi les cases comportant au moins 30 tirs, le taux le plus élevé est observé pour "
                     f"**{label[0]}**, à **{label[1]} pieds** : {best.goal_pct:.2f} % sur {int(best.shots)} tirs. "
                     "Ce maximum est descriptif ; plusieurs comparaisons et des effectifs différents peuvent "
                     "faire apparaître un maximum peu stable.\n\n")
    else:
        text += "*Carte et observation principale en attente des données.*\n\n"
    text += """## 5. Cartes de tirs offensives interactives

### 5.1. Méthode et interprétation

Nous construisons les cartes à partir d'histogrammes NumPy et de graphiques Plotly
standards, sans bibliothèque de visualisation de hockey. Les tirs cadrés, buts
inclus, sont tournés vers le filet de droite, puis regroupés en classes de
**5 × 5 pieds** dans la zone offensive (`25 ≤ x ≤ 100`). Aucun lissage n'est appliqué.
Les coordonnées physiques sont placées sur l'image de la patinoire avec les
bornes `[-100, 100] × [-42.5, 42.5]` ; pour une image de largeur W et hauteur H,
les pixels sont `(x+100)/200 × (W-1)` et `(42.5-y)/85 × (H-1)`.

Pour une classe spatiale b et une saison :

```
taux_ligue(b)  = nombre_tirs_ligue(b) / (2 × nombre_matchs_ligue)
taux_équipe(b) = nombre_tirs_équipe(b) / nombre_matchs_équipe
excès(b)       = taux_équipe(b) - taux_ligue(b)
```

Chaque match terminé compte dans les dénominateurs, même si ses tirs ont des
coordonnées manquantes. L'hypothèse de 60 minutes par match donne l'unité
**tirs par heure-équipe**. Les prolongations ne changent pas cette exposition
simplifiée ; les filets déserts sont inclus. Les cartes sont celles de la saison
régulière. Le rouge indique davantage de tirs que la moyenne, et le bleu moins.
L'échelle diverge autour de zéro et reste identique pour les cinq saisons.
Il s'agit de différences brutes par classe, ni de pourcentages ni de buts attendus.

Nous présentons une carte pour chacune des **cinq saisons de 2016-17 à 2020-21**.
Le menu de chaque carte permet de sélectionner toutes les équipes de sa saison.

"""
    if ready:
        for rates in maps:
            text += f"### Saison {rates['year']}-{str(rates['year']+1)[2:]}\n\n{{% include shotmap_{season_id(rates['year'])}.html %}}\n\n"
    else:
        text += "*Les cinq cartes seront exportées et intégrées par le pipeline.*\n\n"
    text += "### 5.2. Colorado, de 2016-17 à 2020-21\n\n"
    if ready:
        text += _map_discussion(maps[0], "COL") + "\n\n" + _map_discussion(maps[4], "COL") + "\n\n"
        standings = standings_from_games(exposure)
        selected = standings.loc[standings["team"].eq("COL") & standings["season"].isin([20162017, 20202021])]
        text += _table(selected) + "\n\n"
        if "COL" in maps[0]["teams"] and "COL" in maps[4]["teams"]:
            delta = maps[4]["teams"]["COL"]["rate"].sum() - maps[0]["teams"]["COL"]["rate"].sum()
            central_delta = _central_rate(maps[4], "COL") - _central_rate(maps[0], "COL")
            text += (f"Entre ces deux saisons, le volume offensif du Colorado change de **{delta:+.2f} tirs "
                     f"par heure-équipe**, dont **{central_delta:+.2f}** dans le rectangle proche du filet "
                     "(`70 ≤ x < 90`, `-17.5 ≤ y < 17.5` pieds). Ce décompte porte sur les classes "
                     "de la carte et fournit une comparaison concrète de la zone centrale.\n\n")
            if len(selected) == 2:
                point_values = selected.set_index("season")["points_pct"]
                points_delta = point_values.loc[20202021] - point_values.loc[20162017]
                if delta > 0 and points_delta > 0:
                    text += (f"La hausse du volume offensif accompagne une hausse de **{points_delta:.2f} points "
                             "de pourcentage** dans les points obtenus sur les points possibles. Cette "
                             "évolution est cohérente avec une équipe devenue plus performante, sans "
                             "démontrer que le volume de tirs explique à lui seul le changement.\n\n")
        text += ("Ce tableau reconstitue les points depuis les scores et le type de la dernière période "
                 "(2 points par victoire, 1 par défaite en prolongation/fusillade, sous réserve de la règle 84.2). "
                 "Le cas de point perdu du match `2023021166` est annoté explicitement à partir du "
                 "[compte rendu officiel](https://www.nhl.com/news/vegas-golden-knights-minnesota-wild-game-recap-march-30). "
                 "Nous ne déduisons pas cette exception de tout but en filet désert : une pénalité "
                 "différée peut maintenir le point. Les huit résumés officiels mis en cache permettent "
                 "de contrôler matchs, victoires, défaites et points pour chaque équipe. Le rang est calculé "
                 "par points avec ex æquo ; les bris d'égalité officiels ne sont pas appliqués. Le pourcentage "
                 "des points possibles aide à comparer les calendriers de longueurs différentes. "
                 "Comparer les zones rouges et bleues des deux cartes avec ce tableau permet de relier "
                 "l'évolution du volume offensif aux résultats, sans attribuer la performance aux seuls tirs.\n\n")
    else:
        text += "*Comparaison des cartes et des points du classement à calculer.*\n\n"
    text += "### 5.3. Buffalo et Tampa Bay, de 2018-19 à 2020-21\n\n"
    if ready:
        for rates in maps[2:]:
            for team in ["BUF", "TBL"]:
                text += _map_discussion(rates, team) + "\n\n"
            if all(team in rates["teams"] for team in ["BUF", "TBL"]):
                buffalo, tampa = _central_rate(rates, "BUF"), _central_rate(rates, "TBL")
                text += (f"Dans le rectangle proche du filet défini ci-dessus, Tampa Bay obtient "
                         f"**{tampa:.2f} tirs par heure-équipe**, contre **{buffalo:.2f}** pour Buffalo, "
                         f"soit un écart de **{tampa-buffalo:+.2f}** en {rates['year']}-{str(rates['year']+1)[2:]}. "
                         "Cette comparaison mesure le volume dans une zone fixe ; elle ne suffit pas "
                         "à mesurer la qualité de chaque occasion ni sa conversion.\n\n")
        selected = standings.loc[standings["team"].isin(["BUF", "TBL"]) & standings["season"].isin([20182019, 20192020, 20202021])]
        text += _table(selected) + "\n\n"
    else:
        text += "*Les observations spatiales et les résultats de ces six équipes-saisons seront insérés après acquisition.*\n\n"
    text += ("Un excès de tirs près du filet peut être compatible avec une attaque qui obtient davantage "
             "d'occasions proches ; un déficit peut indiquer moins de volume dans ces zones. Ces cartes "
             "ne donnent toutefois pas un portrait complet : elles ignorent le taux de conversion, "
             "les tirs manqués/bloqués, la défense, la qualité du gardien, le contexte des adversaires, "
             "les passes et les écrans. Une carte de saison régulière ne démontre pas la cause "
             "d'un succès en séries. Les saisons 2019-20 et 2020-21 ont aussi des calendriers particuliers ; "
             "la normalisation par match aide à comparer les volumes, sans effacer les différences de contexte.\n\n")
    text += "## Données manquantes et événements exclus\n\n"
    if ready:
        report_rows = [{"analyse": name, **report} for name, report in simple["reports"].items()]
        report_rows += [{"analyse": f"carte_{rates['year']}", **rates["report"]} for rates in maps]
        text += _table(pd.DataFrame(report_rows)) + "\n\n"
        missing = frame.isna().sum().rename("valeurs_manquantes").rename_axis("colonne").reset_index()
        text += _table(missing) + "\n\n"
        text += _table(frame["direction_source"].fillna("unknown").value_counts().rename("événements").rename_axis("source_direction").reset_index()) + "\n\n"
    else:
        text += "*Les décomptes exacts seront fournis à partir du dataframe réel.*\n\n"
    text += "## Sources et déclaration de l’aide de l’IA\n\n"
    text += (PROJECT / "docs/sources.md").read_text(encoding="utf-8").replace("# Sources et aide utilisée\n", "").replace("## Références de la tâche 1", "### Références").replace("## Déclaration de l'aide de l'IA", "### Aide de l'IA")
    post = blog / "_posts/2026-10-08-milestone-1.md"
    post.parent.mkdir(parents=True, exist_ok=True)
    post.write_text(text, encoding="utf-8")
    return post
