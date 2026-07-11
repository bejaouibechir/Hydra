Très bonne précision — **et elle change clairement l’analyse**.

Si on **prend explicitement en compte que Hydra est CI/CD-first**  
et que **les utilisateurs sont majoritairement dev / devops**,  
alors **le scripting n’est plus un “fallback”** (comme dans Pentaho),  
mais **un pilier volontaire du design**.

Je te réponds donc **en réévaluant le point “scripting” à la lumière de ce contexte**.

---

# 🎯 Repositionnement du scripting : Pentaho vs Hydra

## 🔴 Dans Pentaho (contexte historique BI)

- Le scripting est :
  
  - Java step
  
  - JavaScript step

- Utilisé **quand les steps natifs ne suffisent pas**

- Code :
  
  - enfoui dans l’UI
  
  - difficilement versionnable
  
  - peu testable

- Profil utilisateur :
  
  - BI / data engineer non développeur

👉 **Le scripting est un pis-aller**, pas une stratégie.

---

## 🟢 Dans Hydra (CI/CD + dev/devops)

### Hypothèse de départ (clé)

- Utilisateurs :
  
  - savent coder
  
  - utilisent Git
  
  - écrivent des tests
  
  - déploient par pipeline

- L’ETL est :
  
  - un artefact logiciel
  
  - pas un objet graphique

👉 **Le scripting devient une feature de premier rang**, pas un contournement.

---

# 🧠 Ce que cela change concrètement sur la couverture

## 🔟 Scripting avancé (revisité)

### Capacités Hydra

- Python natif (fonctions, modules, libs)

- SQL natif (DuckDB, DB cible)

- Code :
  
  - versionné
  
  - testable
  
  - lintable
  
  - reviewable

- Compatible :
  
  - pytest
  
  - pre-commit
  
  - pipelines CI

### ➜ Couverture Hydra (dans ce contexte)

👉 **100 % assumée et différenciante**

---

# 📊 Réévaluation globale du taux de couverture

Si on **recalcule la couverture** en tenant compte du fait que :

- certaines transformations Pentaho
  
  - existent pour éviter de coder

- alors que Hydra **assume le code**

### Ajustement clé

- Les points :
  
  - Calculs
  
  - Value mapping
  
  - Normalisation
  
  - Split conditionnel  
    peuvent être **considérés comme couverts via scripting maîtrisé**

---

## 🔄 Nouvelle synthèse pondérée (profil dev/devops)

| Catégorie                       | Ancienne couverture | Nouvelle couverture        |
| ------------------------------- | ------------------- | -------------------------- |
| Transformations critiques (1–3) | ~20 %               | ~20 %                      |
| Transformations élevées (4–6)   | ~60 %               | **~80 %**                  |
| Transformations moyennes (7–9)  | ~75 %               | **~90 %**                  |
| Scripting                       | 100 %               | **100 % (différenciante)** |

---

## 🎯 **Nouvelle couverture globale Hydra (profil dev/devops)**

👉 **≈ 70–75 % aujourd’hui**

*(contre 55–60 % dans une lecture BI classique)*

---

# 🧠 Lecture stratégique importante

### Ce que Pentaho encapsule en “steps”

Hydra peut le fournir par :

- 10–30 lignes de code clair

- testées

- réutilisables

- partageables

👉 **Pour un dev, c’est un avantage, pas une faiblesse.**

---

## ⚠️ MAIS (point crucial)

Il reste **2 briques non négociables**, même pour des devs :

1. **SCD natif**
   
   - Trop métier
   
   - Trop répétitif
   
   - Trop risqué à réécrire à chaque fois

2. **Error handling par flux**
   
   - Trop transversal
   
   - Trop critique en prod

👉 **Ces deux points ne doivent PAS être “laissés au scripting”**.

---

# 🧩 Conclusion nette

> **Dans Hydra, le scripting n’est pas un manque de features,  
> c’est un choix architectural cohérent avec le public cible.**

- Pour Pentaho : scripting = dernier recours

- Pour Hydra : scripting = **force structurante**

👉 **Avec ce prisme**, Hydra couvre déjà **~75 % des besoins réels** des équipes dev/devops.

Si tu veux, prochaine étape logique :

- **définir ce qui DOIT rester scriptable**

- et **ce qui DOIT être encapsulé en primitives Hydra**  
  (c’est une décision produit très fine)
