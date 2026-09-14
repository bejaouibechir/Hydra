# Brief — Contenu de la landing page hydraetl.com

Document interne (français). Le contenu produit, lui, est en **anglais** (charte, règle 8).

---

## Partie A — Feuille de route

| # | Étape | Sortie | Qui |
|---|---|---|---|
| 1 | Figer les faits et les chiffres | la section « Faits » du prompt B | Bechir valide |
| 2 | Produire le texte anglais des 10 blocs | `landing.copy.md` | ChatGPT (prompt B) |
| 3 | Arbitrer le texte, couper au budget de mots | `landing.copy.md` v2 | Bechir |
| 4 | Spécifier les 6 SVG | `BRIEF_LANDING_SVG.md` | fait |
| 5 | Générer les SVG | `src/assets/landing/*.svg` | ChatGPT |
| 6 | Intégrer dans Astro (`src/pages/index.astro`) | page | dev |
| 7 | Vérifier : script de charte, Lighthouse, clavier seul | rapport | CI |

**Règle d'ordre** : le texte avant les images. Un SVG dessiné avant que la phrase du bloc soit
arrêtée est un SVG à refaire.

**Budget global** : 250 mots de prose pour toute la page, hors code, hors YAML, hors légendes de
schéma. Dix blocs → **25 mots par bloc**, soit un titre et une phrase.

---

## Partie B — Prompt à coller dans ChatGPT

````text
RÔLE
Tu es rédacteur technique pour la page d'accueil d'un outil ETL open source destiné à des
data engineers et des développeurs Python. Tu écris en anglais, ton factuel, zéro superlatif.

PRODUIT
Hydra (hydra-etl) : moteur ETL déclaratif en Python. Un projet Hydra est un ensemble de
fichiers YAML — pas du code à maintenir. Un moteur les exécute (Extract → Transform → Load).
Hydra Studio est un éditeur visuel : on construit le pipeline à la souris, il sort en YAML.
Une extension native en Rust (hydra-native) accélère certaines opérations, en option.

FAITS VÉRIFIÉS — n'utilise que ceux-là, n'en invente aucun, ne les arrondis pas
- Connecteurs natifs : CSV, JSON, Parquet, PostgreSQL, MySQL/MariaDB, Web API. MongoDB en plugin.
- Moteurs d'exécution : pandas et DuckDB.
- 18 opérations de transformation dans le moteur.
- 12 points d'extension, tous sur le même mécanisme de registre : connectors, engines,
  operations, auth providers, cache backends, compilers, error handlers, hooks, metrics sinks,
  pagination strategies, retry policies, web API policies.
- Accélération Rust, mesures sur 1 000 000 de lignes :
  - lecture CSV : 3,55 s → 0,89 s (×4)
  - écriture CSV, 700 000 lignes : 1,26 s → 0,55 s (×2,31)
  - opération cast sur 5 colonnes : 1 609 ms → 620 ms (×2,6)
  - job complet S1 : ×1,65 · job complet S3 : ×2,02
- Le choix du moteur se fait par opération ; si le chemin Rust ne s'applique pas, Python reprend
  automatiquement, sans erreur. Résultats identiques octet pour octet.
- Parité vérifiée : 26 000 fichiers CSV aléatoires, 0 écart en lecture ; 1 500 fichiers comparés
  octet pour octet en écriture ; 1 000 000 de flottants comparés à repr() de CPython, 0 écart.
- Publié sur PyPI : hydra-native 0.1.0, 19 wheels (Linux, macOS, Windows) + sdist, attestations
  Sigstore, CI verte.
- Installation : pip install hydra-etl · accélération : pip install "hydra-etl[native]"
- Aucune infrastructure requise : pas de scheduler, pas de cluster, pas d'entrepôt de données.
  Un pipeline Hydra tourne sur un portable.
- Limite assumée : Hydra vise le pipeline qui tourne sur une machine. Pas d'exécution distribuée.

CONTRAINTES ABSOLUES
1. Anglais. Ton factuel. Aucun superlatif, aucun emoji, aucune promesse au futur.
   Interdits : "revolutionary", "blazing fast", "game changer", "seamless", "effortless",
   "the best", "simply". On écrit ce que l'outil fait, pas ce qu'il fera.
2. Budget : 250 mots de prose pour TOUTE la page. Ne comptent pas : le code, le YAML, les
   libellés de schéma, les en-têtes de tableau. Compte les mots et donne le total à la fin.
3. Un verdict tient en un chiffre et six mots. Pas de paragraphe explicatif.
4. Toute affirmation comparative est chiffrée. "faster" est interdit ; "3.55 s to 0.89 s on
   1M rows" est permis.
5. Tout exemple YAML montré doit être un manifeste correct et exécutable. Jamais d'exemple
   fautif, jamais d'erreur mise en scène.
6. Aucun secret en clair dans un exemple : écrire ${SECRET.X}.
7. On nomme ce que le concurrent fait mieux. La crédibilité vient de là.

STRUCTURE IMPOSÉE — 10 blocs, dans cet ordre
Pour chaque bloc, produis : le titre (≤ 7 mots), la phrase (≤ 20 mots), le code ou les données
s'il y en a, le libellé du bouton s'il y en a, et le texte alternatif du schéma.

1. HERO — une phrase qui dit ce que fait Hydra, et un bloc YAML de 10 lignes éditable à côté
   de son résultat. Le lecteur doit pouvoir modifier quelque chose en moins de 5 secondes.
2. UN JOB DE BOUT EN BOUT — YAML → extract / transform / load → fichier de sortie réel.
   [schéma svg-01]
3. LE DSL EN 10 LIGNES — le manifeste minimal, copiable, qui s'exécute.
4. CONNECTEURS — les 6 natifs + le plugin. [schéma svg-02]
5. PERFORMANCE — les chiffres ci-dessus, avec le commutateur python / rust. [schéma svg-03]
6. EXTENSIBILITÉ — les 12 points d'extension. [schéma svg-04]
7. HYDRA STUDIO — le canvas visuel qui produit du YAML. [schéma svg-05]
8. POSITIONNEMENT — où Hydra se place face à Airflow, dbt, Airbyte, Databricks.
   Les axes de comparaison autorisés, et eux seuls : temps avant le premier pipeline qui tourne,
   infrastructure requise, format du pipeline, construction visuelle, tourne sur un portable,
   coût d'entrée, accélération native. Termine par la limite assumée, en une phrase.
   [schéma svg-06]
9. SIGNES DE SÉRIEUX — PyPI, wheels des trois systèmes, CI verte, parité testée.
10. INSTALLATION — la commande, un seul bouton, vers /install.

FORMAT DE SORTIE
Markdown. Un titre de niveau 2 par bloc, numéroté comme ci-dessus. Sous chaque titre :
- **Title:** …
- **Sentence:** …
- **Code / data:** … (ou "none")
- **CTA:** … (ou "none")
- **Figure alt text:** … (ou "none")
- **Prose words:** n
Termine par le total de mots de prose de la page et la liste des faits que tu as utilisés.

AVANT DE RÉPONDRE, VÉRIFIE
- Le total de mots de prose est ≤ 250. S'il dépasse, coupe et recompte.
- Aucun mot de la liste des interdits n'apparaît.
- Chaque chiffre cité figure dans la section FAITS, à l'identique.
- Le bloc 8 contient la phrase de limite.
- Chaque schéma a un texte alternatif qui a du sens sans l'image.
````

---

## Partie C — Vérification avant intégration

- [ ] Moins de 250 mots de prose (script de charte)
- [ ] Premier geste possible en moins de 5 secondes
- [ ] Tous les chiffres tracés à une mesure du dépôt
- [ ] Aucun superlatif, aucun emoji
- [ ] Chaque YAML montré s'exécute réellement
- [ ] Chaque schéma a son texte alternatif
- [ ] Page navigable au clavier seul, contraste AA
- [ ] Aucun appel réseau au chargement
