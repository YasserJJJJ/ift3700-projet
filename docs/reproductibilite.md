# Environnement Python reproductible — 9 octobre 2026

## Versions retenues

Les sept bibliothèques principales utilisent les versions relevées dans le
ZIP du Mac de l'équipe, dont le Python est 3.13.5 :

| Bibliothèque | Version |
| --- | --- |
| pandas | 2.3.3 |
| NumPy | 2.5.3 |
| Matplotlib | 3.11.2 |
| Plotly | 7.1.0 |
| ipywidgets | 8.1.9 |
| JupyterLab | 4.6.4 |
| Mistune | 3.3.4 |

Setuptools 84.0.0 permet de construire le paquet local. Les versions des
dépendances indirectes sont également fixées dans `requirements-analysis.lock`,
avec les empreintes SHA-256 des distributions autorisées. Le verrou est prévu
pour Python 3.12 ou 3.13, avec des conditions spécifiques aux plateformes.
NumPy 2.5.3 exige Python >= 3.12. L'acquisition seule conserve sa compatibilité
Python >= 3.11 et son fonctionnement sans bibliothèque externe.

## Installation depuis zéro

Depuis la racine du projet, avec Python 3.12 ou 3.13 :

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --require-hashes -r requirements-analysis.lock
python3 -m pip install --no-build-isolation --no-deps -e .
python3 -m pip check
python3 -m unittest discover -s tests -v
```

Sur Windows, l'activation est `.venv\Scripts\activate`.
Pour vérifier une installation neuve en gardant son environnement existant,
créer un environnement dans un autre dossier, par exemple `.venv-verification`.
Ne pas copier un environnement virtuel d'une machine à une autre.

Les dépendances sont installées avec contrôle des empreintes. Le paquet local
est ensuite installé sans télécharger d'autres dépendances ni créer un
environnement de construction implicite. UV n'est pas nécessaire pour utiliser
le verrou avec pip ; il a servi à générer ce fichier.

## Vérifications réalisées

- Environnement virtuel neuf sous Ubuntu 24.04 et Python 3.12.14.
- Installation par pip de toutes les dépendances avec `--require-hashes` réussie.
- Installation éditable du paquet local sans résolution supplémentaire réussie.
- `pip check` : aucune dépendance incompatible.
- Les 33 tests passent, dont le pipeline complet sur un corpus artificiel isolé.
- Le test du pipeline supprime uniquement la capture de sa copie temporaire
  pour tester explicitement le cas sans capture. Le résultat ne dépend plus de
  la présence d'une capture dans le projet de travail.
- Match réel 2017020001 lu hors ligne : clés uniques dans le dataframe et
  événement manqué 63 tracé à (37, 26), sans requête HTTP.
- Résolution du verrou contrôlée pour Python 3.13 sur Mac Apple Silicon, avec
  distributions binaires. Ce contrôle ne constitue pas une exécution sur Mac.

Le test complet sur le corpus réel déjà acquis n'a pas été relancé : l'article,
les données et les résultats de l'équipe ont été conservés.

## Régénérer volontairement le verrou

Avec UV 0.12.23, depuis la racine du projet :

```bash
uv pip compile requirements-analysis.in --universal --python-version 3.12 --generate-hashes --output-file requirements-analysis.lock
```

Une régénération peut changer des dépendances indirectes ; refaire les contrôles
dans un environnement neuf avant d'adopter le nouveau fichier. Le verrou doit
être conservé dans Git avec le code. `blog/Gemfile.lock` verrouille séparément
les dépendances du blog Jekyll.

Références :
- [Installations reproductibles avec pip](https://pip.pypa.io/en/stable/topics/repeatable-installs/).
- [Résolution universelle avec UV](https://docs.astral.sh/uv/concepts/resolution/).
