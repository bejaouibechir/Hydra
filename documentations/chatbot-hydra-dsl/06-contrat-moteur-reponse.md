# Contrat du moteur de réponse statique

**Étape 6 — Terminée**  
**Projet cible :** `hydra-site-template`  
**Hébergement :** Astro statique sur GitHub Pages

## 1. Localisation retenue

Le projet Astro réel est :

```text
hydra-site-template/
```

Le contrat du chatbot est placé dans :

```text
hydra-site-template/src/lib/chatbot/
├── types.ts
└── contract.ts
```

Le chatbot du mockup Playground reste une simulation indépendante. Il ne constitue pas le moteur du site Astro.

## 2. Contraintes structurantes

Le moteur MVP doit respecter :

- sortie Astro `static` ;
- aucun backend requis ;
- aucun appel réseau au chargement ;
- aucune clé API dans le navigateur ;
- corpus embarqué au build ;
- interface publique en anglais ;
- JavaScript chargé uniquement avec l'îlot interactif ;
- chemins compatibles avec `import.meta.env.BASE_URL` ;
- aucune affirmation d'exécution réelle ;
- cas inconnu ou non supporté toujours affiché.

## 3. Entrée du moteur

Le moteur reçoit un `ChatRequest` :

```ts
interface ChatRequest {
  contractVersion: '1.0';
  requestId: string;
  locale: 'en';
  question: string;
  assistanceLevel: 'hint_1' | 'hint_2' | 'explanation' | 'solution';
  context: ChatContext;
}
```

Le contexte peut contenir :

- la notion et la leçon actives ;
- le YAML affiché ;
- les fichiers du job ;
- les lignes d'entrée et de sortie ;
- les erreurs de validation ;
- l'opération ou la propriété sélectionnée ;
- le mode `local_simulation` ou `static_example` ;
- un signal de secret potentiel.

Le contexte est transmis explicitement par la page Learn. Le moteur ne lit pas arbitrairement le DOM.

## 4. Sortie du moteur

Le moteur retourne un `ChatResponse` :

```ts
interface ChatResponse {
  contractVersion: '1.0';
  requestId: string;
  answer: string;
  citations: ChatCitation[];
  assistanceLevel: AssistanceLevel;
  scopeDecision: ScopeDecision;
  confidence: number;
  matchedExampleIds: string[];
  actions: SuggestedAction[];
  executionNotice?: string;
}
```

Cette structure est directement comparable au dataset d'évaluation de l'étape 5.

## 5. Décisions de périmètre

Le moteur doit produire une décision explicite parmi :

```text
answer
answer_with_limitation
answer_unknown_feature
decline
decline_and_redirect
decline_external_action
secret_warning
refuse_instruction_override
no_match
```

L'interface ne doit jamais rester silencieuse lorsqu'aucune réponse n'est trouvée.

## 6. Actions suggérées

Le moteur peut proposer au maximum trois actions :

```text
show_next_hint
show_solution
load_example
open_guide
open_playground
open_migrate
```

Une action n'est jamais exécutée automatiquement. L'utilisateur doit l'activer.

## 7. Citations

Chaque citation contient :

- un identifiant stable ;
- un libellé court ;
- un type : schéma, exemple, Guide ou compatibilité ;
- un chemin source interne ;
- un lien public compatible avec la base GitHub Pages.

Le moteur retournera au maximum trois citations par réponse.

## 8. Limites contractuelles

```text
Question : 500 caractères maximum
Réponse : 140 mots maximum
Citations : 3 maximum
Actions : 3 maximum
Confiance : valeur entre 0 et 1
Langue MVP : anglais
```

Ces limites protègent la lisibilité mobile, le budget de mots et la taille du composant.

## 9. Validation à l'exécution

`contract.ts` expose :

```ts
isChatRequest(value)
isChatResponse(value)
```

Ces gardes vérifient les champs obligatoires, les versions, les valeurs énumérées, la longueur des réponses et les limites d'actions/citations.

Une réponse non conforme doit être remplacée par une réponse locale sûre avec `scopeDecision: 'no_match'` lors de l'étape d'implémentation.

## 10. Architecture d'intégration prévue

```text
Page Astro Learn
      ↓ contexte explicite
Îlot Chatbot client:idle
      ↓ ChatRequest
Moteur statique TypeScript
      ↓ recherche dans examples.json et schémas préparés
ChatResponse
      ↓
Interface : réponse + citations + actions
```

Le dataset d'évaluation ne fait pas partie de cette chaîne et ne sera pas publié.

## 11. Répartition des prochaines étapes

### Étape 7

- synchroniser le corpus vers `src/data/hydra-dsl/` ;
- normaliser et indexer les textes côté build ;
- implémenter la recherche pondérée ;
- gérer les secrets, limites connues et questions hors périmètre ;
- produire un `ChatResponse` conforme.

### Étape 8

- créer l'îlot d'interface ;
- connecter le contexte Learn ;
- gérer clavier, focus, annonces et responsive ;
- afficher citations et actions.

### Étape 9

- faire passer les 100 scénarios au moteur ;
- produire un score par catégorie ;
- bloquer les régressions critiques.

## 12. Vérification réalisée

Les fichiers TypeScript du contrat ont été compilés en mode strict avec succès, sans ajouter de dépendance au projet Astro.
