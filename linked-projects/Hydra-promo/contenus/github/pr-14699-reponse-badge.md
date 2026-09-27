# PR awesome-mcp-servers #14699 — état final au 21/09/2026

## Résultat

**Les trois labels sont verts** : `has-emoji`, `has-glama`, `valid-name`. Contrôles **✓ 2/2**.
Le label `missing-glama` a basculé en `has-glama` **automatiquement**, sans intervention :
le bot relit Glama à chaque nouveau commit sur la branche de la PR.

Il ne reste que la revue humaine de `punkpeye`.

## Ce qui a débloqué la situation

Le mainteneur avait écrit : *« The server is listed on Glama and claimed, but the quality score
has not been evaluated yet (it's currently set to '?'). Glama must evaluate the quality score
(any grade is acceptable) before we can accept the listing. »*

Note obtenue : **83 %**, avec **A** en licence, **A** en qualité des définitions de tools, **A**
en maintenance. Marche à suivre complète dans `contenus/annuaires/fiches-annuaires.md` §1.

## La ligne finale, telle qu'elle est dans la PR

```markdown
- [bejaouibechir/Hydra](https://github.com/bejaouibechir/Hydra) [![bejaouibechir/Hydra MCP server](https://glama.ai/mcp/servers/bejaouibechir/Hydra/badges/score.svg)](https://glama.ai/mcp/servers/bejaouibechir/Hydra) 🐍 🏠 🍎 🪟 🐧 - MCP server for Hydra ETL, a declarative YAML ETL engine. Lets AI assistants draft pipelines (CSV, Parquet, PostgreSQL, MySQL, MongoDB, web APIs) and validate them with Hydra before any data is touched. Install: `pip install "hydra-etl[mcp]"`.
```

## Trois pièges rencontrés — à retenir pour les prochaines PR

1. **La branche de la PR était `patch-2`, pas `patch-1`.** Toujours lire l'en-tête du diff
   (« merge N commits into X from <owner>:<branche> ») avant d'ouvrir une URL d'édition.
   Un commit a atterri sur `patch-1` par erreur ; branche supprimée ensuite (aucune PR
   associée : `is:pr author:bejaouibechir` sur le dépôt amont donnait `Open 1 · Closed 0`).
2. **Le badge se place après le lien du dépôt, avant les émojis** — pas en fin de ligne,
   contrairement à ce que dit le message du bot (« after the server description »). La pratique
   réelle de la liste, lisible sur les entrées voisines, prime sur le message du bot.
3. **L'URL du badge est `/badges/score.svg`**, pas `/badge` comme l'indique le bot. C'est ce que
   fournit l'onglet **GitHub Badge** de l'admin Glama et ce qu'utilisent les entrées voisines.
   Vérification : ouvrir l'URL du SVG dans le navigateur. Le `Preview` de GitHub est inutilisable
   sur ce README (« Error getting preview ») : le fichier est trop gros pour son rendu à la volée.

## Commentaire posté au mainteneur

```markdown
The Glama quality score is now evaluated: **83%**, with **A** for license, **A** for tool definition quality and **A** for maintenance — https://glama.ai/mcp/servers/bejaouibechir/Hydra

The score badge is in the entry, placed right after the repository link to match the surrounding lines. All three labels are green and checks pass.

Thanks for the precise pointer.
```

Ni signature, ni email, ni lien vers le site : la divulgation d'auteur est déjà dans le corps de
la PR (« Disclosure: I'm the author ») et la convention de ces listes est sobre.
