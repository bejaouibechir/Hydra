Voici la **priorisation claire par phases Hydra**, alignée avec le **besoin réel**, le **risque** et la **valeur**.  
Objectif : maximiser l’impact sans dégrader la simplicité du moteur.

---

## 🟢 PHASE 1 — MVP (couvrir ~70–75 % des usages réels)

### 1) 1 source → N transformations → 1 destination

Besoin : ~35 %  
Statut : ✅ déjà couvert  
Pourquoi :

- cas ETL fondamental

- zéro ambiguïté

- excellent pour onboarding utilisateurs

👉 **Indispensable, cœur d’Hydra**

---

### 2) N sources → N transformations verticales → 1 destination

Besoin : ~25 %  
Statut : ✅ déjà couvert  
Pourquoi :

- normalisation par source très fréquente

- converge naturellement vers union / join

- lisible et robuste

👉 **Indispensable, différenciant dès le MVP**

---

### 3) N sources → transformation globale multi-sources → 1 destination

Besoin : ~12 %  
Statut : ✅ déjà couvert  
Pourquoi :

- cas BI / DW classique

- DuckDB apporte un énorme avantage ici

- reste linéaire et explicable

👉 **Indispensable pour crédibilité “data”**

---

➡️ **Total Phase 1 : ~72 % des besoins utilisateurs**

---

## 🟡 PHASE 2 — Production stable (~20 % des usages)

### 4) 1 source → N transformations → N destinations

Besoin : ~10 %  
Statut : 🔜 à implémenter  
Pourquoi :

- export multiple (DW + fichier + audit)

- valeur métier claire

- nécessite une policy d’erreur par destination

Recommandation :

- fan-out **séquentiel explicite**

- pas de parallélisme caché

👉 **À faire après hooks + error policies**

---

### 5) 1 source → aucune transformation → 1 destination

Besoin : ~5 %  
Statut : ✅ trivial  
Pourquoi :

- ingestion brute

- réplication simple

👉 **Gratuit, mais non prioritaire**

---

### 6) N sources → aucune transformation → 1 destination

Besoin : ~3 %  
Statut : ⚠️ optionnel  
Pourquoi :

- staging brut

- peu utilisé mais parfois nécessaire

👉 **À supporter implicitement, sans feature dédiée**

---

➡️ **Total Phase 2 : ~18 %**

---

## 🔴 PHASE 3 — Avancé / Enterprise (~5–8 % max)

### 7) N sources → N transformations → N destinations

Besoin : ~8 %  
Statut : ❌ pas MVP  
Pourquoi :

- vrai besoin plateforme

- très risqué si mal modélisé

- explosion de complexité si implicite

Recommandation :

- **multi-pipelines explicites uniquement**

- chaque pipeline testable et relançable seul

👉 **À faire uniquement quand Hydra est mature**

---

### 8) N sources → fan-out conditionnel → N destinations

Besoin : ~2 %  
Statut : 🚫 à éviter tôt  
Pourquoi :

- logique métier déguisée

- difficile à debugger

- forte dette cognitive

👉 **À repousser très loin, voire ne jamais implémenter**

---

## 📊 Vue synthèse (priorité Hydra)

| Phase          | Couverture besoin | Combinaisons |
| -------------- | ----------------- | ------------ |
| Phase 1 (MVP)  | ~72 %             | 1, 2, 3      |
| Phase 2 (Prod) | ~18 %             | 4, 5, 6      |
| Phase 3 (Adv)  | ~8 %              | 7, 8         |

---

## 🧠 Décision stratégique clé (à conserver)

> **Hydra n’implémente que ce qui reste lisible sans diagramme complexe.**  
> Tout le reste doit être une composition explicite de pipelines.

Si tu veux, prochaine étape possible :

- transformer cette liste en **roadmap officielle Hydra**

- ou tester un **cas réel borderline** pour décider s’il mérite une implémentation native.
