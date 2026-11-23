# Skill « cours » pour Claude Code

Un agent qui **écoute ton cours au micro du Mac**, le **transcrit en direct** (Whisper, en local) et te rend à la fin une **fiche de révision** : l'essentiel en 5 lignes, plan, cours mis au propre, définitions, devoirs et dates, questions de révision. Les digressions du prof sont mises de côté.

Le son et le texte restent sur ton ordinateur pendant l'écoute. Seule la fiche finale est rédigée par Claude.

## Comment ça s'utilise

Dans Claude Code, ouvert dans ton dossier :

| Tu écris | Ce qui se passe |
|---|---|
| `cours maths` | l'écoute démarre (matière : maths) |
| `cours statut` | où en est l'écoute, le micro capte-t-il bien |
| `fin cours` | arrêt, fin de la transcription, puis la fiche |
| `cours fichier ~/Desktop/cours.m4a` | transcrit et résume un enregistrement existant (audio ou vidéo) |

Chaque cours est rangé dans `cours/<date>_<matière>/` : `transcription.md` puis `restitution.md`.

## Installation

Il faut un Mac, Python 3.9 ou plus, et [Claude Code](https://claude.com/claude-code).

```bash
git clone https://github.com/mouridendao96-ui/skill-cours.git
```

```bash
cd skill-cours
```

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

Puis ouvre Claude Code dans ce dossier et écris `cours test`. La première fois :
- macOS demande l'accès au **micro** : accepte (Réglages Système › Confidentialité et sécurité › Micro) ;
- le modèle Whisper (environ 1,5 Go) se télécharge. Ensuite, tout marche sans internet.

Tu peux aussi copier le dossier `.claude/` dans un projet existant, à condition d'y créer le `.venv` de la même façon.

## Ce qu'il y a dedans

- `.claude/skills/cours/SKILL.md` : les consignes données à Claude (commandes courtes).
- `.claude/skills/cours/scripts/cours.py` : l'écoute, le découpage en blocs de 5 minutes et la transcription.
- `.claude/agents/restituteur-cours.md` : l'agent qui transforme la transcription en fiche de révision.

## Réglages

- Plus rapide mais moins précis : `COURS_MODELE=small`.
- Cours dans une autre langue : `--langue en` ou `--langue auto`.
- Garde l'ordinateur ouvert et près du prof : il ne se met pas en veille pendant l'écoute.

## Important

Demande l'accord du prof avant d'enregistrer, et respecte les règles de ton établissement.
