# Sources et aide utilisée

Consignes : `milestone-1/README_fr.md` du dépôt du cours
(copie locale : `consignes/README_fr.md`). Le périmètre est IFT3700 : les parties
marquées « IFT6758 seulement » ne sont pas incluses.

## Références de la tâche 1

- [Modèle de projet du cours](https://github.com/milarobotlearningcourse/data_science_project) :
  organisation générale en package, données, notebooks et figures. Le module
  d'acquisition proposé ici a été écrit pour le play-by-play actuel ; l'ancien
  exemple Hockey Reference du modèle n'a pas été repris.
- [Documentation non officielle actuelle](https://github.com/Zmalski/NHL-API-Reference) :
  endpoint `https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play`
  et API des statistiques `https://api.nhle.com/stats/rest/en/game`.
- [Discussion sur le catalogue des matchs](https://github.com/Zmalski/NHL-API-Reference/issues/23) :
  requête par saison `cayenneExp=season=20172018`.
- [Ancienne documentation — identifiants](https://github.com/dword4/nhlapi#game-ids) :
  structure `YYYYTTNNNN`, types `02` et `03`. Les autres endpoints de l'ancienne
  API ne sont pas employés. Aucun identifiant de série n'est deviné : ils sont
  lus dans le catalogue.
- [Bibliothèque standard Python](https://docs.python.org/3/library/urllib.request.html) :
  `urllib.request` pour les requêtes et `json` pour les fichiers.

## Références des autres tâches

- [Patinoire du modèle du cours](https://github.com/milarobotlearningcourse/data_science_project/blob/main/figures/nhl_rink.png) :
  image reprise telle quelle dans `figures/nhl_rink.png` et utilisée dans le widget
  et les cartes. Dimensions physiques : 200 × 85 pieds, ligne du filet à 89 pieds.
- [Modèle de blog du cours](https://github.com/milarobotlearningcourse/data_science_blog) :
  layouts, feuilles de style Lanyon/Poole, navigation et Gemfile repris et adaptés.
  Licence MIT conservée dans `blog/LICENSE.md` ; les articles d'exemple ne sont
  pas repris. Empreintes des fichiers téléchargés dans `docs/template_files.json`.
- [ipywidgets](https://ipywidgets.readthedocs.io/en/stable/examples/Widget%20Events.html) :
  menus, curseur et callbacks. L'outil du projet a été écrit pour ce devoir.
- [NumPy histogram2d](https://numpy.org/doc/stable/reference/generated/numpy.histogram2d.html) :
  classes spatiales ; la matrice est transposée pour les axes de Plotly.
- [Plotly — menus](https://plotly.com/python/dropdowns/) et
  [export HTML](https://plotly.com/python/interactive-html-export/) :
  cartes interactives et exports. La bibliothèque JavaScript distribuée avec
  Plotly est copiée localement, avec ses notices intégrées.
- [Hockeyviz — lecture d'une carte de tirs](https://hockeyviz.com/howto/shotMap) :
  référence conceptuelle indiquée par le devoir. Aucune carte de Hockeyviz ni
  fonction spécialisée de hockey n'est reprise pour calculer nos résultats.
- [Statistiques officielles par équipe](https://api.nhle.com/stats/rest/en/team/summary) :
  filtres `seasonId` et `gameTypeId=2`. Les réponses en cache permettent de vérifier
  les matchs joués, victoires, défaites, défaites en prolongation et points
  reconstitués. Résultat du contrôle dans `outputs/standings_verification.json`.
- [Règles officielles 2023-24, règle 84.2](https://media.nhl.com/site/asset/public/ext/2023-24/2023-24Rulebook.pdf)
  et [compte rendu officiel du match 2023021166](https://www.nhl.com/news/vegas-golden-knights-minnesota-wild-game-recap-march-30) :
  annotation explicite du point de prolongation perdu. Un filet désert ne suffit
  pas à appliquer cette règle automatiquement : le cas d'une pénalité différée
  doit être distingué. L'annotation est limitée au corpus historique étudié ;
  une extension à d'autres saisons exige de contrôler leurs résultats officiels.

## Déclaration de l'aide de l'IA

Nous avons eu recours à plusieurs outils d'IA pendant ce jalon et nous les
déclarons ici :

- **ChatGPT/Codex** (OpenAI) nous a aidés à interpréter les consignes et a produit
  une première version du code des tâches 1 à 5, des tests, des notebooks et
  du texte du blog.
- **Claude** (Anthropic) nous a servi à revoir l'ensemble du code et à le rendre
  réutilisable : un pipeline qui se relance hors ligne à partir du cache, et un
  article rédigé à la main que `run.py` ne vient plus écraser. Il nous a aussi
  aidés à compléter ce qui manquait, notamment la correction de l'orientation
  des coordonnées lorsque le côté fourni par l'API contredit les zones, les
  compléments d'interprétation des sections 4.3 et 5.1 et la lisibilité de
  la figure 4.3.
- **ChatGPT Astra** a joué le rôle de second relecteur, indépendant du premier,
  pour vérifier que nous n'avions pas laissé d'erreurs dans le code, les chiffres
  ou les formulations. Ces vérifications ont notamment signalé l'anomalie
  d'orientation corrigée ensuite.

Les résultats chiffrés de l'article proviennent des fonctions d'analyse
appliquées aux données réelles du cache. Le code est vérifié par des tests sur
des réponses artificielles et par des contrôles sur les données réelles,
documentés dans `docs/verification.md`. Nous restons responsables du code,
des analyses et du contenu remis, et sommes en mesure de les expliquer.
