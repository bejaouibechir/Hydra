"""
State Manager - Gestion état pour extraction incrémentale.

Permet de ne récupérer que les nouvelles données depuis dernière extraction.

Exemple:
    Première extraction: récupère tous items
    Extractions suivantes: seulement items avec updated_at > last_state
"""

import json
import os
from typing import Any, Optional, Dict
from datetime import datetime
from pathlib import Path


class StateManager:
    """
    Gestionnaire d'état pour extractions incrémentales.
    
    Fonctionnalités:
    - Sauvegarde état entre exécutions
    - Support différents types de state (timestamp, ID, cursor)
    - Thread-safe (write atomic)
    
    Configuration DSL:
        sources:
          api:
            type: web_api
            incremental:
              enabled: true
              state_field: updated_at
              state_file: .hydra/state/api_state.json
    """
    
    def __init__(
        self,
        state_file: str,
        state_field: str = "updated_at",
        initial_state: Optional[Any] = None
    ):
        """
        Initialise state manager.
        
        Args:
            state_file: Chemin fichier state
            state_field: Champ pour tracking (updated_at, id, etc.)
            initial_state: Valeur initiale si fichier absent
        """
        self.state_file = Path(state_file)
        self.state_field = state_field
        self.initial_state = initial_state
        self._current_state: Optional[Any] = None
    
    def load_state(self) -> Optional[Any]:
        """
        Charge état depuis fichier.
        
        Returns:
            État sauvegardé ou initial_state si absent.
        """
        if not self.state_file.exists():
            self._current_state = self.initial_state
            return self.initial_state
        
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
                self._current_state = data.get("state")
                return self._current_state
        except Exception as e:
            raise StateError(f"Failed to load state from {self.state_file}: {e}") from e
    
    def save_state(self, new_state: Any) -> None:
        """
        Sauvegarde nouvel état.
        
        Args:
            new_state: Nouvelle valeur d'état
        """
        # Créer dossier si nécessaire
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Préparer données
        state_data = {
            "state": new_state,
            "state_field": self.state_field,
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        # Écriture atomique (via temp file)
        temp_file = self.state_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w') as f:
                json.dump(state_data, f, indent=2)
            
            # Atomic rename
            temp_file.replace(self.state_file)
            self._current_state = new_state
        
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            raise StateError(f"Failed to save state to {self.state_file}: {e}") from e
    
    def get_current_state(self) -> Optional[Any]:
        """Retourne état actuel (chargé en mémoire)."""
        if self._current_state is None:
            return self.load_state()
        return self._current_state
    
    def update_state_from_items(self, items: list) -> None:
        """
        Met à jour état depuis items extraits.
        
        Prend le max du state_field parmi items.
        
        Args:
            items: Items extraits (dicts)
        """
        if not items:
            return
        
        max_state = None
        for item in items:
            if isinstance(item, dict) and self.state_field in item:
                value = item[self.state_field]
                if max_state is None or value > max_state:
                    max_state = value
        
        if max_state is not None:
            self.save_state(max_state)
    
    def reset(self) -> None:
        """Supprime fichier state (force full reload)."""
        if self.state_file.exists():
            self.state_file.unlink()
        self._current_state = None


class StateError(Exception):
    """Erreur gestion état."""
    pass
