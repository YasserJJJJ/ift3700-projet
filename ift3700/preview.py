"""Aperçu local de l'article et des cartes, avant construction du site Jekyll."""

import re
from pathlib import Path


def make_preview(blog_dir):
    """Résoudre uniquement nos includes/URLs ; Jekyll reste la source du site remis."""
    import mistune
    blog = Path(blog_dir)
    post = blog / "_posts/2026-10-08-milestone-1.md"
    source = post.read_text(encoding="utf-8").split("---", 2)[2]
    def include(match):
        name = match.group(1)
        if "/" in name or ".." in name:
            raise ValueError("Include invalide.")
        return (blog / "_includes" / name).read_text(encoding="utf-8")
    source = re.sub(r"\{%\s*include\s+([\w.-]+)\s*%\}", include, source)
    source = re.sub(r"\{\{\s*'(/[^']+)'\s*\|\s*relative_url\s*\}\}", lambda m: m.group(1).lstrip("/"), source)
    markdown = mistune.create_markdown(escape=False, plugins=["table"])
    rendered = markdown(source)
    document = ('<!doctype html><html lang="fr"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>Jalon 1 — IFT3700</title><link rel="stylesheet" href="public/css/poole.css">'
                '<link rel="stylesheet" href="public/css/lanyon.css"><link rel="stylesheet" href="public/css/project.css">'
                '<script src="public/js/plotly.min.js"></script></head><body>'
                '<main class="container content"><h1>Jalon 1 — Exploration des événements de la LNH</h1>'
                '<p><small>Aperçu local. Le site final est construit avec Jekyll à partir du même article.</small></p>'
                + rendered + '</main></body></html>')
    target = blog / "apercu.html"
    target.write_text(document, encoding="utf-8")
    return target
