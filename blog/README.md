# Article Jekyll du projet

Ce site utilise le [modèle fourni par le cours](https://github.com/milarobotlearningcourse/data_science_blog),
avec son thème Lanyon et sa licence. Les posts de démonstration ont été remplacés
par un article unique pour le jalon 1.

L'article contient les résultats du corpus réel complet : 10 395 matchs, cinq
figures simples et cinq cartes interactives. `apercu.html` permet de le lire
localement dans un navigateur, avec les cartes et leurs menus.
La capture réelle du widget est intégrée et les membres de l'équipe sont indiqués dans `about.md`.

`python3 -m ift3700.run`, depuis le dossier parent, régénère tableaux, figures et
cartes à partir du cache. Le texte de l'article, rédigé à la main, n'est pas
modifié ; seule l'option `--regenerate-blog` le réécrit (après sauvegarde).

Pour consulter le site localement, avec Ruby ≥ 3.2 et Bundler :

```bash
bundle install
bundle exec jekyll serve
```

Ouvrir l'adresse locale affichée. Pour générer seulement le site :

```bash
bundle exec jekyll build
```

Les cartes sont intégrées via des fragments `_includes/shotmap_*.html`.
La bibliothèque Plotly est locale ; les cartes ne nécessitent pas Internet.
Les HTML autonomes correspondants sont produits dans `outputs/maps/` du projet.
Ne pas publier sur GitHub Pages pendant le cours.

Le site a été construit avec Ruby 3.3.12, Bundler 2.6.9 et Jekyll 4.4.1.
`Gemfile.lock` conserve les versions utilisées et inclut les plateformes Mac
Intel et Apple Silicon.

Le dossier `_site/` n'est pas versionné (il est exclu par `.gitignore`) : il faut
donc construire le site avant de le consulter. Sans Ruby, ouvrir directement
`apercu.html` dans un navigateur : il contient le même article et les cartes
interactives.

Après `bundle exec jekyll build`, on peut aussi servir la version construite
depuis la racine du projet :

```bash
python3 -m http.server 8000 --directory blog/_site
```

Ouvrir `http://localhost:8000` et garder le terminal ouvert. Les chemins des
ressources sont prévus pour un serveur local ; ne pas ouvrir `_site/index.html`
par double-clic. Après une modification de l'article, relancer
`bundle exec jekyll build` dans `blog`.
