# Projet LNH — IFT3700 — jalon 1

Ce dossier contient une version de travail exécutée des tâches 1 à 5 du jalon 1,
pour le volet **IFT3700** : code, trois notebooks, figures, cartes interactives
et article Markdown/Jekyll avec les résultats réels. Les **10 395 matchs** des
huit saisons ont été téléchargés ; le tableau contient **650 432 tirs cadrés et
buts**, fusillades comprises. Les chiffres artificiels des tests ne figurent pas
dans le blog livré.

Pour lire l'article et utiliser les menus des cinq cartes sans installer Python
ou Ruby, ouvrir **`blog/apercu.html`** dans un navigateur.
Cet aperçu local accompagne les sources Jekyll ; il ne remplace pas leur
construction. La capture est intégrée et le site Jekyll a été construit et
contrôlé sur le Mac de l'équipe.

Équipe : Mohamed Yasser Jabari (20270150), Cheikh Ahmed Khalifa (20228606) et
Enric Soldevila (20247337).

## Première utilisation : tâche 1

Les données brutes ne sont pas incluses dans le dépôt (environ 10 400 fichiers JSON) :
les commandes ci-dessous les téléchargent dans `data/raw/`. Une fois en cache,
elles relisent les fichiers existants sans nouvelle requête. Les totaux par saison figurent dans
`docs/acquisition_summary.csv`.

Python 3.11 ou plus récent suffit ; aucun paquet externe n'est requis pour
l'acquisition. Ouvrir un terminal **à la racine du projet**.
Sur Windows, remplacer `python3` par `py` au besoin.

1. Télécharger un match et vérifier que son JSON est disponible :

   ```bash
   python3 -m ift3700.acquire --game 2017020001
   ```

2. Relancer la même commande : le fichier existant est chargé sans requête HTTP.
   Le mode hors ligne permet de vérifier ce comportement :

   ```bash
   python3 -m ift3700.acquire --game 2017020001 --offline
   ```

3. Télécharger **2016-17 à 2023-24**, saison régulière **et** séries :

   ```bash
   python3 -m ift3700.acquire --start-season 2016 --end-season 2023
   ```

   Les années sont celles du **début** des saisons. Un essai court peut se faire
   avec `--season 2017 --limit 3`, mais ne remplace pas l'acquisition complète.
   L'acquisition intégrale demande plusieurs milliers de requêtes et prend du temps.
   Une interruption peut être suivie d'une relance de la même commande : les
   matchs déjà sauvegardés sont relus localement.

4. Vérifier les huit rapports dans `data/raw/reports/`. Une acquisition complète
   des deux types produit des fichiers `acquisition_20162017_2-3.json` à
   `acquisition_20232024_2-3.json`, chacun avec `complete: true` et `failed: {}`.
   Un échec reste signalé et la commande renvoie un code de sortie non nul.

## Organisation du cache

- `data/raw/catalogs/20172018.json` : catalogue complet d'une saison.
- `data/raw/20172018/regular/2017020001.json` : JSON brut d'un match régulier.
- `data/raw/20172018/playoffs/2017030416.json` : JSON brut d'un match des séries.
- `data/raw/reports/` : résultats de l'acquisition, dont les échecs éventuels.

Le chemin peut être choisi avec `--data-dir /chemin/vers/donnees`, ou la variable
d'environnement `NHL_DATA_DIR`. Python propose également
`NHLClient(data_dir="/chemin/vers/donnees")`.
Le JSON play-by-play est sauvegardé sans nettoyage ni ajout de champs.
Les catalogues regroupent les lignes brutes des pages et leur provenance.
Les matchs terminés du catalogue ont l'état `gameStateId=7`. Les rencontres
prévues de séries qui n'ont jamais eu lieu restent dans le catalogue, mais ne
sont pas téléchargées ; leurs IDs figurent dans les rapports. Un catalogue
sans état du match provoque une erreur plutôt qu'une acquisition dite complète.

La commande peut traiter plusieurs saisons et matchs en parallèle. Tous les
clients partagent un délai minimal entre départs HTTP (`0.25` seconde par
défaut), et les erreurs 429 déclenchent une pause. `--workers 1 --game-workers 1`
permet une acquisition entièrement séquentielle.

Un cache invalide provoque une erreur explicite. `--force` permet de le remplacer
avec une nouvelle réponse validée. L'ancien fichier reste intact si cette
nouvelle requête échoue. `--offline` interdit toute requête réseau.

Le dossier `data/` est ignoré par Git : **ne pas déposer les données brutes sur
GitHub**.

## Vérification locale du code

```bash
python3 -m unittest discover -s tests -v
```

Ces tests utilisent des réponses artificielles et vérifient la pagination,
le cache, la validation, les reprises, la normalisation des côtés et les
dénominateurs. Un test exécute le pipeline complet sur huit saisons artificielles
dans un dossier temporaire. Les huit rapports réels et le contrôle des 250
équipes-saisons contre les statistiques officielles constituent les vérifications
du corpus livré ; voir `docs/verification.md` et `outputs/standings_verification.json`.

## Tâches 2 à 5, après acquisition

Créer un environnement et installer les dépendances, depuis ce dossier :

```bash
python3 -m venv .venv
```

Activer l'environnement : `source .venv/bin/activate` sur macOS/Linux,
ou `.venv\Scripts\activate` sur Windows. Puis :

```bash
python3 -m pip install --require-hashes -r requirements-analysis.lock
python3 -m pip install --no-build-isolation --no-deps -e .
python3 -m jupyterlab
```

Cette installation verrouillée de l'environnement d'analyse demande Python
3.12 ou 3.13 ; le Mac fourni utilise Python 3.13.5. `requirements-analysis.lock`
fixe les versions de toutes les dépendances et leurs empreintes. Les versions
principales sont celles de l'environnement Mac qui fonctionne déjà.
L'acquisition seule reste compatible avec Python 3.11 et n'exige aucun paquet
externe. Voir `docs/reproductibilite.md` pour les versions et les contrôles.
L'installation flexible `pip install -e ".[analysis]"` reste possible, mais
peut sélectionner d'autres versions que celles qui ont été vérifiées.

1. `notebooks/02_explorateur.ipynb` : sélectionner une saison, le type de match,
   le match et l'événement. Comparer quelques événements avec le site LNH, puis
   prendre une capture réelle avec les menus et la patinoire.
2. `notebooks/03_donnees_et_figures.ipynb` : examiner le tableau et les figures
   une à une. Les valeurs manquantes restent manquantes.
3. Générer tous les résultats (tableaux, figures, cartes) :

   ```bash
   python3 -m ift3700.run
   ```

   L'article `blog/_posts/2026-10-08-milestone-1.md` est rédigé à la main : s'il
   existe, la commande met à jour les figures et les cartes du blog **sans jamais
   modifier son texte**. L'option `--regenerate-blog` réécrit l'article à partir
   du modèle automatique, après en avoir sauvegardé une copie dans
   `outputs/article_avant_regeneration.md`. Ce pipeline est **hors ligne** et
   exige les huit saisons complètes du cache. Il ne remplace pas une acquisition
   manquante par un sous-ensemble silencieux.
4. Les CSV, cinq figures simples et cinq cartes HTML autonomes se trouvent dans
   `outputs/`. Les figures et fragments de cartes sont également copiés dans le
   blog. Les décomptes d'exclusions sont écrits dans `outputs/analysis_exclusions.json`.
   `blog/apercu.html` permet de lire l'article et ses cartes localement avant
   d'installer Ruby.
   Cet aperçu n'est pas la construction Jekyll de la remise.
5. Dans `blog/`, avec Ruby ≥ 3.2 et Bundler :

   ```bash
   bundle install
   bundle exec jekyll serve
   ```

   Ouvrir l'adresse locale affichée et relire les résultats avant remise.

La commande `run` ne modifie pas le texte de l'article, rédigé à la main ; seule
l'option `--regenerate-blog` le réécrit, après en avoir sauvegardé une copie.
Pour contrôler les classements contre les données officielles, on peut aussi
mettre en cache les huit résumés avec `python3 -m ift3700.standings` ; le pipeline
les compare automatiquement lorsqu'ils sont disponibles.

La tâche 4 porte sur les saisons régulières et compte les tirs cadrés, buts
inclus. Les cartes couvrent 2016-17 à 2020-21, soit cinq saisons. Les données
de séries sont également téléchargées et conservées dans le tableau.
Les classements du blog sont reconstitués à partir des matchs, avec l'exception
historique de la règle 84.2 annotée pour `2023021166` (points et
pourcentage des points possibles) ; le rang par points conserve les ex æquo,
sans appliquer les bris d'égalité officiels.

## Explications et provenance

- `notebooks/01_acquisition.ipynb` : exemples Python de la tâche 1.
- `notebooks/02_explorateur.ipynb` : tâche 2 et instructions de capture.
- `notebooks/03_donnees_et_figures.ipynb` : tâches 3 à 5.
- `docs/sources.md` : références et déclaration de l'aide de l'IA.
- `docs/verification.md` : contrôles effectués sur les données réelles.

Les membres de l'équipe figurent dans `blog/_config.yml` et `blog/about.md`.
