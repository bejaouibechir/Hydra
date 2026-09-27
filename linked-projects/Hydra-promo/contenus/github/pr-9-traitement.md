# PR #9 — « docs: clarify what hdrctl validate checks » — marche à suivre

> Première contribution externe (Voyagerroc-Lab, ouverte le 19/09). Ordre : publier 0.10.2 → commenter → fusionner.

## Mon avis de relecture

**Le contenu est exact** : j'ai comparé chaque affirmation au code. Les trois manifestes requis, le contrôle de `pipeline.from` / `pipeline.to`, le renvoi vers `hdrctl test` pour les connexions : tout est juste. La modification du `.gitignore` est correcte (le dossier `docs/` est ignoré, avec des exceptions explicites).

**Un seul point faible :** la puce sur `--strict` dit « the additional checks implemented for strict validation », ce qui ne veut rien dire. C'était compréhensible avant ton correctif ; avec la 0.10.2, on peut être précis.

---

## Étape 1 — Commentaire à poster sur la PR

> Onglet *Conversation* de la PR → champ en bas → coller → **Comment**.

```
Thanks for this — the content is accurate and it closes a real gap.

One change before I merge. The `--strict` bullet is vague because strict mode did not do much until now.
Version 0.10.2 (released today) makes it concrete, so please replace that bullet with:

- With `--strict`, Hydra additionally lists the transformation operations it recognised and checks the
  syntax of `filter` and `calculate` expressions using pandas' own parser, without evaluating them.
  An expression such as `price * (qty` fails validation instead of failing mid-run.

Two small additions that would make the page more useful, if you are willing:

- `hdrctl validate` exits with code 0 on success and 1 on failure, so it can gate a CI job.
- `--strict` does not connect to any system either; only `hdrctl test` does.

Happy to merge once that is in.
```

## Étape 2 — Selon sa réponse

- **Il met à jour la PR** → relis la puce, puis **Squash and merge** (bouton vert), et poste :
  ```
  Merged — thanks again. This is the first external contribution to Hydra ETL.
  ```
- **Aucune réponse au bout de 5 jours** → fusionne quand même (le texte est correct), puis corrige toi-même la puce dans un commit de suivi. Son commit reste dans l'historique, donc la contribution est préservée.
- **Le texte te semble hors sujet ou mal écrit** → tu peux refuser, mais ferme la PR avec un mot aimable et une raison précise. Un refus sec décourage les suivants.

## Étape 3 — Après la fusion

- Vérifier que `docs/VALIDATION.md` est bien visible sur GitHub (le `.gitignore` l'autorise explicitement).
- Le ticket #7 se ferme tout seul (la PR contient « Closes #7 »).
- Me prévenir : je reprends le texte de `contenus/pages/validation.md` pour éviter le doublon entre le dépôt et le site, et on garde une seule source de vérité.

## Ce que ça vaut pour la promo

Un dépôt avec une PR externe fusionnée et un `CONTRIBUTING.md` respecté est plus crédible qu'un dépôt à un seul auteur. À mentionner au Show HN, sans exagérer : c'est une contribution de documentation, pas de code.

⚠️ Rappel : ce compte a été créé le 11/09 et affiche plus de 500 dépôts. Ne pas compter son étoile ni son fork comme une adoption réelle dans les indicateurs.
