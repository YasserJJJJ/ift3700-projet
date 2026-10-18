# Vérifications du jalon 1 — mises à jour le 11 octobre 2026

## Résultats réels

- Les huit rapports d'acquisition indiquent `complete: true` et aucune erreur.
  Le cache contient **10 395 matchs terminés** de 2016-17 à 2023-24 : 9 658
  matchs réguliers et 737 de séries. Certains matchs de séries prévus après
  l'élimination d'une équipe n'ont jamais été joués ; leurs IDs sont signalés
  séparément et ne sont pas comptés comme des échecs.
- Le pipeline hors ligne lit tous ces matchs et produit **650 432 événements**
  (63 546 buts), les CSV, cinq figures simples, cinq cartes HTML autonomes et
  cinq fragments de cartes intégrés à l'article. Les 4 316 événements de
  fusillade restent dans le tableau et sont exclus des analyses agrégées.
- Les résumés officiels de la LNH confirment matchs, victoires, défaites,
  défaites en prolongation et points pour **250 équipes-saisons**. Le seul cas
  historique de point perdu (règle 84.2) est documenté et annoté explicitement
  dans l'article et le code.
- Onze événements ont été contrôlés sur plusieurs matchs réels, anciennes et
  nouvelles saisons. `orientation_audit.csv` garde leurs IDs, côtés et
  coordonnées brutes/normalisées. Il relève notamment les périodes où le côté
  défendu change dans les événements du JSON : le code privilégie alors le côté
  fourni pour l'événement et marque la provenance.
- Les figures ont été ouvertes et inspectées. Les exclusions, valeurs
  manquantes et sources de directions sont écrites dans
  `outputs/analysis_exclusions.json` et `outputs/data_quality.json`.
- `blog/apercu.html`, ses cinq cartes et la bibliothèque Plotly locale sont
  générés. Le notebook de la tâche 2 passe les tests de sélection de match,
  saison, type d'événement, et d'événement sans coordonnées.
- Les **37 tests locaux passent**, dont le pipeline de bout en bout sur un
  corpus artificiel isolé. Ces fixtures servent uniquement aux tests et ne
  figurent pas dans les résultats de l'article.

## État avant la remise

- La capture de l'explorateur est intégrée à la section 2 du blog.
- Les membres de l'équipe sont indiqués dans `blog/_config.yml` et `blog/about.md`.
- Le site a été construit avec Jekyll sur le Mac de l'équipe.
- Les interprétations des sections 4 et 5 ont été réécrites et leurs chiffres
  vérifiés à partir des données. `python3 -m ift3700.run` ne modifie plus le
  texte de l'article (option `--regenerate-blog` pour le réécrire).

## Méthodes et limites gardées visibles

- Orientation (11 octobre) : dans sept périodes de trois matchs (`2019020249`,
  `2019020256`, `2020020175`), le côté `homeTeamDefendingSide` de l'API est inversé
  pour toute la période ; toutes les zones `O`/`D` le contredisent. La zone prime
  alors (152 événements, `zone_code_overrides_api_side`). Neuf événements isolés
  dont le côté contredit la zone gardent une direction inconnue
  (`unknown_api_side_zone_conflict`). Après correction, aucun tir ou but à plus de
  25 pieds du centre ne contredit sa zone déclarée. Exemple vérifié : but de Buffalo,
  match `2019020256`, événement 73, maintenant à 25,61 pieds au lieu de 158,81.
  Seules les analyses de 2019-20 et 2020-21 changent ; les chiffres du blog ont été
  mis à jour. 37 tests passent, dont un sur cet événement réel.
- Les directions ambiguës restent manquantes. Une médiane de coordonnées ne
  tranche pas des votes contradictoires de zones ; avec une majorité inférée,
  un événement qui la contredit reste également inconnu. Les comptes par source
  figurent dans le rapport de qualité.
- Les analyses de tâches 4 et 5 portent sur la saison régulière. Elles gardent
  les filets déserts, excluent les fusillades et déclarent les exclusions
  requises par chaque figure.
- Les intervalles des figures de distance sont des intervalles descriptifs de
  Wilson à 95 %. Les cartes utilisent des classes de 5 × 5 pieds sans lissage,
  une échelle commune et l'hypothèse d'une heure par équipe et par match.
- Les statistiques de points valident le total des points, pas le bris
  d'égalité qui détermine certains rangs officiels.
- Les cartes couvrent les cinq saisons de 2016-17 à 2020-21, inclusivement.

L'aide de l'IA utilisée pour ce projet est déclarée dans `docs/sources.md`.
