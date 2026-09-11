"""
Auth Provider Interface - Contrat abstrait pour authentification Web API.

Ce fichier définit l'interface stable qui permettra la migration future
vers SharedAuthService ou EventStreamAuth sans casser le code existant.

Pattern: Strategy Pattern pour pluggabilité des mécanismes d'auth.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional


class AuthProvider(ABC):
    """
    Interface abstraite pour fournisseurs d'authentification.
    
    Cette interface est le CONTRAT STABLE entre le connecteur et
    les différentes implémentations d'auth (in-memory, shared, event stream).
    
    Principes de design:
    - Simple : une seule responsabilité (fournir headers d'auth)
    - Extensible : nouvelles implémentations possibles sans casser l'existant
    - Testable : facile à mocker pour les tests
    
    Implémentations prévues:
    - Sprint 1: APIKeyAuth, BearerTokenAuth, OAuth2InMemoryAuth
    - Sprint 5: SharedAuthService (cache partagé Redis)
    - v2.0: EventStreamAuthProvider (Kafka/streaming)
    """
    
    @abstractmethod
    def get_headers(self) -> Dict[str, str]:
        """
        Retourne les headers HTTP d'authentification.
        
        Cette méthode est appelée avant chaque requête HTTP.
        L'implémentation doit gérer:
        - Cache de tokens (si applicable)
        - Refresh automatique (si expiré)
        - Thread-safety (si multi-threading)
        
        Returns:
            Dict[str, str]: Headers à ajouter à la requête HTTP.
            
        Examples:
            >>> auth = APIKeyAuth(key="secret123")
            >>> auth.get_headers()
            {"X-API-Key": "secret123"}
            
            >>> auth = BearerTokenAuth(token="abc...")
            >>> auth.get_headers()
            {"Authorization": "Bearer abc..."}
        
        Raises:
            AuthenticationError: Si impossible d'obtenir credentials valides.
        """
        pass
    
    def on_auth_failure(self, status_code: int, response_body: Optional[str] = None) -> None:
        """
        Hook appelé quand le serveur retourne une erreur d'authentification.
        
        Permet à l'implémentation de réagir (ex: forcer refresh du token,
        invalider cache, logger erreur, etc.).
        
        Cette méthode est OPTIONNELLE. Implémentation par défaut = ne rien faire.
        
        Args:
            status_code: Code HTTP (401, 403, etc.)
            response_body: Corps de la réponse (pour debug)
        
        Examples:
            >>> # OAuth2 pourrait forcer refresh du token
            >>> def on_auth_failure(self, status_code, response_body):
            ...     if status_code == 401:
            ...         self._invalidate_token_cache()
        """
        pass  # Implémentation par défaut : ne rien faire
    
    def validate(self) -> None:
        """
        Valide la configuration d'auth au démarrage.
        
        Appelée une fois lors de l'instanciation du connecteur.
        Permet de fail-fast si config invalide (clé manquante, etc.).
        
        Cette méthode est OPTIONNELLE. Implémentation par défaut = pas de validation.
        
        Raises:
            ValueError: Si configuration invalide.
        
        Examples:
            >>> auth = APIKeyAuth(key="")
            >>> auth.validate()
            ValueError: API key cannot be empty
        """
        pass  # Implémentation par défaut : pas de validation


class AuthenticationError(Exception):
    """
    Exception levée quand l'authentification échoue de manière irrémédiable.
    
    Utilisée pour distinguer:
    - Erreurs transitoires (429, 5xx) → retry possible
    - Erreurs auth fatales (401, 403) → arrêt immédiat
    """
    pass
