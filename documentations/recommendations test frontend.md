Pour une vérification visuelle immédiate, installez simplement ces extensions :

### Chrome et Brave — Responsive Viewer

[Installer Responsive Viewer](https://chromewebstore.google.com/detail/responsive-viewer/inmopeiepgfljkpkidclfgbgbmfcennb)

C’est mon premier choix :

- 400 000 utilisateurs ;
- plusieurs écrans simultanément ;
- comparaison mobile, tablette et desktop ;
- fonctionne également dans Brave ;
- idéal pour repérer rapidement les débordements.

Brave accepte les extensions du Chrome Web Store puisqu’il repose sur Chromium.

### Firefox — Mobile Simulator

[Installer Mobile Simulator pour Firefox](https://addons.mozilla.org/en-US/firefox/addon/simulateur-mobile/)

Il propose :

- plusieurs appareils côte à côte ;
- smartphones et tablettes prédéfinis ;
- dimensions personnalisées ;
- rotation portrait/paysage ;
- comparaison visuelle multi-écrans.

Alternative récente : [Pixefy pour Firefox](https://addons.mozilla.org/en-US/firefox/addon/pixefy/), qui propose des aperçus synchronisés sur plusieurs tailles, mais possède encore peu d’utilisateurs.

### Configuration Hydra recommandée

Créez ces dimensions personnalisées dans les deux extensions :

| Profil            | Largeur × hauteur |
| ----------------- | ----------------- |
| Petit mobile      | 320 × 568         |
| Mobile courant    | 360 × 800         |
| iPhone moderne    | 390 × 844         |
| Grand mobile      | 430 × 932         |
| Tablette portrait | 768 × 1024        |
| Tablette paysage  | 1024 × 768        |
| Laptop            | 1366 × 768        |
| Desktop           | 1440 × 900        |
| Grand écran       | 1920 × 1080       |

Pour le prototype ouvert avec `file:///`, activez dans Chrome ou Brave :

```
Extensions
→ Responsive Viewer
→ Détails
→ Autoriser l’accès aux URL de fichiers
```

Dans l’immédiat, **Responsive Viewer dans Chrome/Brave + Mobile Simulator dans Firefox** couvrira parfaitement votre besoin de contrôle à l’œil. BrowserStack et Playwright pourront attendre la phase de validation automatisée.
