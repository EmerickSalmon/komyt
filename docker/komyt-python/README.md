# komyt-python image

Pré-installe tout ce dont `opencode` a besoin pour implémenter + vérifier du
code Python sans que Komyt ait à installer des outils au démarrage du conteneur.

## Build

```bash
docker build -t komyt-python:latest docker/komyt-python
```

## Contenu

- Python 3.12 (base: `python:3.12-slim`)
- Lint / format : `flake8`, `black`, `ruff`, `isort`, `pylint`
- Types : `mypy`
- Sécurité : `bandit`
- Tests : `pytest`, `pytest-cov`, `pytest-asyncio`, `pytest-mock`, `pytest-xdist`, `coverage`
- Agent : `opencode` CLI (invoqué par Komyt via `opencode run '<prompt>'`)

## Auth

`opencode` a besoin d'une clé API pour appeler un modèle. Komyt injecte
`ANTHROPIC_API_KEY` (ou la clé équivalente) au démarrage du conteneur.

## Test rapide

```bash
docker run --rm komyt-python:latest opencode --version
docker run --rm komyt-python:latest flake8 --version
docker run --rm komyt-python:latest pytest --version
```
