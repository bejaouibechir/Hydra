# Trouver les consultants et freelances data — les six canaux

> Arrêté le 25/09/2026.
>
> **Le profil prioritaire n'est ni les startups ni les grandes entreprises : ce sont les
> consultants et freelances data.** Un consultant qui adopte Hydra le déploie chez plusieurs
> clients — un utilisateur devient trois à cinq installations. Il a le problème tous les jours,
> il décide seul, et il parle publiquement de ses outils parce que c'est son marketing.
>
> Hors entourage direct, dont Bechir s'occupe lui-même.

---

## Pourquoi pas les startups

- **Elles n'ont aucune licence ETL à économiser.** Elles n'en ont jamais acheté : elles utilisent
  des scripts Python et cron, ou dbt Core qui est gratuit. L'argument « nous sommes gratuits » ne
  mord pas sur elles, elles sont déjà à zéro.
- Les licences chères — Informatica, Talend Enterprise, Fivetran, Matillion, SSIS via SQL Server —
  sont le problème des **entreprises établies**.
- **Ce qui est vrai en revanche : leur vitesse de décision.** Pas de comité d'achat, pas de
  validation sécurité de six mois. Garder ce critère, abandonner celui du prix.

## 1. Les communautés Slack de l'écosystème data — le plus dense, le plus sous-exploité

- **dbt Community Slack** — plusieurs dizaines de milliers de membres, proportion énorme de
  consultants et freelances. Canaux utiles : `#tools-general`,
  `#advice-data-stack-architecture`, et les canaux régionaux dont `#local-paris`.
- **Locally Optimistic** — plus senior : leads de données et consultants.
- **Data Engineering Discord**
- **r/dataengineering**

**L'avantage décisif sur une liste :** on ne contacte personne. **On répond à des questions, et
trois cents personnes voient le faire.** Un consultant qui voit résoudre un problème de pipeline
devant témoins retient le nom.

## 2. GitHub — des praticiens identifiables, et un contact socialement normal

Chercher des dépôts contenant des pipelines réels : DAG Airflow, projets dbt, scripts de
migration. Les auteurs sont des praticiens, souvent avec site ou email dans le profil.

**Ce qui rend ce canal unique :** la culture open source rend le contact attendu. Ouvrir une
discussion ou commenter une issue n'est pas une intrusion, contrairement à un email. C'est le seul
canal où approcher un inconnu est normal.

```
path:*.py "airflow" "DAG" language:Python stars:>5
"dbt run" consulting in:readme
```

## 3. Les annuaires de partenaires des concurrents — la liste toute faite

**Talend**, **Fivetran**, **dbt Labs**, **Matillion** publient des listes publiques de partenaires
et de consultants certifiés — littéralement un annuaire de gens dont le métier est de déployer de
l'ETL chez des clients.

- C'est la réponse la plus directe à « comment obtenir une liste ».
- **Réserve :** ils ont un intérêt économique dans l'outil qu'ils revendent. Viser les
  indépendants plutôt que les cabinets.

## 4. Ceux qui écrivent sur l'ETL

Auteurs sur **Medium**, **dev.to**, **Substack** et blogs personnels.

- Identifiables et joignables.
- Surtout : **ils écrivent** — donc ils parleront de l'outil s'il les intéresse. Un consultant qui
  blogue vaut dix consultants silencieux.
- **L'approche qui fonctionne :** commenter leur article de façon substantielle. Jamais leur
  écrire pour parler de soi.

## 5. Malt et LinkedIn — pour la France

- **Malt** — profils publics filtrables : `data engineer`, `ETL`, `Talend`, `SSIS`.
- **LinkedIn** — par titre : `Consultant Data`, `Freelance Data Engineer`,
  `Ingénieur Data indépendant`. Sans Sales Navigator les recherches sont bridées, mais pour une
  vingtaine de personnes c'est suffisant.

## 6. Les meetups data

Listes d'intervenants publiques sur Meetup et les sites de conférences. Quelqu'un qui a donné un
talk sur les pipelines est un praticien qui aime en parler.

---

## La contrainte qui décide de tout

**Une liste de cent consultants ne vaut rien. Vingt contacts individuels, chacun avec une raison
précise de lire le message, valent tout.**

Le message qui marche n'est **jamais** « essayez mon outil ». C'est l'un de ces deux-là :

1. *« J'ai lu votre article sur X. J'ai construit un moteur qui traite ce cas différemment, voici
   comment — ça vous paraît tenir ? »*
2. *« Vous décriviez ce problème dans cette issue. Je l'ai résolu, voici le YAML, ça tourne. »*

**Le second convertit environ trois fois mieux**, parce que le travail a été fait à sa place.

### L'argument qui le concerne lui, et pas ses clients

Un pipeline déclaratif **se relit, se transmet et s'audite**. C'est exactement ce qu'un consultant
vend : la maintenabilité de ce qu'il laisse derrière lui. L'argument du prix ne mord pas sur lui —
celui de la transmissibilité, si.

### Deux points à anticiper

- **L'AGPL-3.0 sera une objection.** Hydra est un outil qu'on utilise, pas une bibliothèque qu'on
  embarque, et l'usage interne ne déclenche rien — mais il faut une réponse écrite et visible sur
  le site, sinon un juriste bloque sans qu'on le sache jamais.
- **Ne jamais basculer dans l'envoi de masse.** Écarté le 24/09 : Sirene ne contient pas d'emails,
  le ciblage y est impossible (le code NAF ne dit pas qui fait de l'ETL), et un domaine de deux
  mois qui envoie en masse détruit sa réputation d'expéditeur — y compris pour la newsletter et
  les échanges avec les pilotes. S'ajoute le risque de réputation : dans les communautés
  techniques, l'étiquette de spammeur ne part plus, et le lancement vise Hacker News.

---

## Prouver l'usage, le jour venu

> Hacker News n'est pas un organisme : aucun dossier, aucune validation. On poste un lien, la
> communauté juge. La preuve sert à répondre au premier commentateur qui demandera
> « est-ce que quelqu'un s'en sert vraiment ? » — et cette question tombe toujours.

Par ordre de force :

1. **Le pilote qui commente lui-même dans le fil** — un compte avec un historique, qui dit ce qui
   marche et ce qui manque. Impossible à fabriquer. Demander aux pilotes s'ils ont un compte HN.
2. **Du code public** — un dépôt du pilote contenant des manifestes Hydra. Vérifiable par
   n'importe qui.
3. **Un article écrit par le pilote** sur son propre blog. Externe, daté, indexé.
4. **Une citation nominative** avec nom, rôle, entreprise, et lien vers le profil.
5. **Les issues ouvertes par des tiers** sur le dépôt — personne n'ouvre une issue sur un outil
   qu'il n'utilise pas. Preuve passive et gratuite ; c'est aussi à quoi servent les tickets
   « good first issue ».

**Ce qui se retourne contre soi :** « trois entreprises nous font confiance » sans noms ; des
logos sans autorisation écrite ; des témoignages anonymisés ; les téléchargements PyPI présentés
comme des utilisateurs (ils comptent les miroirs et les CI).

**Quand demander :** au moment où le pilote commence à utiliser Hydra, pas le jour du lancement.
Et demander le minimum — pas un témoignage marketing, juste l'autorisation d'être cité avec une
phrase qu'il valide.

**Le ton :** *« trois équipes l'utilisent en production, dont deux que je peux nommer »* est plus
crédible que toute formulation suggérant davantage. Sur HN, la modestie chiffrée est un signal de
sérieux.

**Et le point le plus important :** ce qui compte davantage que les utilisateurs, c'est que le
produit marche quand on l'essaie dans les dix minutes. Le premier commentaire est souvent « je
viens de tester ». D'où Killercoda avant tout le reste.
