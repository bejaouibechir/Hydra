"""
Error Classifier - Classification erreurs HTTP retriable vs fatal.

Détermine si une erreur HTTP justifie un retry ou doit être fatal.

Catégories:
- RETRIABLE: Erreurs temporaires (429, 5xx, timeout)
- FATAL: Erreurs permanentes (401, 404, 400)
- UNKNOWN: Cas ambigus
"""

from enum import Enum
from typing import Optional, Set


class ErrorCategory(Enum):
    """Catégories d'erreurs."""
    RETRIABLE = "retriable"  # Temporaire, retry possible
    FATAL = "fatal"          # Permanente, arrêt immédiat
    UNKNOWN = "unknown"      # Ambigu, décision contexte


class ErrorClassifier:
    """
    Classificateur d'erreurs HTTP.
    
    Fonctionnalités:
    - Classification status codes
    - Distinction retriable vs fatal
    - Configurable (codes custom)
    
    Configuration DSL:
        sources:
          api:
            type: web_api
            error_classification:
              retriable_codes: [429, 502, 503, 504]
              fatal_codes: [400, 401, 403, 404, 422]
    """
    
    # Classification par défaut
    DEFAULT_RETRIABLE = {429, 502, 503, 504, 408}  # Too Many, Bad Gateway, Unavailable, Timeout
    DEFAULT_FATAL = {400, 401, 403, 404, 422, 451}  # Bad Request, Unauthorized, Forbidden, Not Found
    
    def __init__(
        self,
        retriable_codes: Optional[Set[int]] = None,
        fatal_codes: Optional[Set[int]] = None
    ):
        """
        Initialise classificateur.
        
        Args:
            retriable_codes: Codes HTTP retriable (défaut: 429, 5xx)
            fatal_codes: Codes HTTP fatal (défaut: 4xx sauf 429)
        """
        self.retriable_codes = retriable_codes if retriable_codes is not None else self.DEFAULT_RETRIABLE
        self.fatal_codes = fatal_codes if fatal_codes is not None else self.DEFAULT_FATAL
    
    def classify(self, status_code: int, response_body: Optional[str] = None) -> ErrorCategory:
        """
        Classifie une erreur HTTP.
        
        Args:
            status_code: Code HTTP (ex: 429, 503)
            response_body: Corps réponse (pour analyse future)
        
        Returns:
            ErrorCategory (RETRIABLE, FATAL, UNKNOWN)
        
        Examples:
            >>> classifier = ErrorClassifier()
            >>> classifier.classify(429)
            <ErrorCategory.RETRIABLE: 'retriable'>
            >>> classifier.classify(404)
            <ErrorCategory.FATAL: 'fatal'>
            >>> classifier.classify(418)  # I'm a teapot
            <ErrorCategory.UNKNOWN: 'unknown'>
        """
        # Classification explicite
        if status_code in self.retriable_codes:
            return ErrorCategory.RETRIABLE
        
        if status_code in self.fatal_codes:
            return ErrorCategory.FATAL
        
        # Heuristiques par défaut
        if 500 <= status_code < 600:
            return ErrorCategory.RETRIABLE  # 5xx = serveur temporaire
        
        if 400 <= status_code < 500:
            return ErrorCategory.FATAL  # 4xx = client error
        
        return ErrorCategory.UNKNOWN
    
    def is_retriable(self, status_code: int, response_body: Optional[str] = None) -> bool:
        """
        Vérifie si erreur retriable.
        
        Args:
            status_code: Code HTTP
            response_body: Corps réponse
        
        Returns:
            True si retriable, False sinon.
        """
        category = self.classify(status_code, response_body)
        return category == ErrorCategory.RETRIABLE
    
    def is_fatal(self, status_code: int, response_body: Optional[str] = None) -> bool:
        """
        Vérifie si erreur fatale.
        
        Args:
            status_code: Code HTTP
            response_body: Corps réponse
        
        Returns:
            True si fatal, False sinon.
        """
        category = self.classify(status_code, response_body)
        return category == ErrorCategory.FATAL
    
    def validate(self) -> None:
        """Valide configuration."""
        # Vérifier pas de conflit
        overlap = self.retriable_codes & self.fatal_codes
        if overlap:
            raise ValueError(
                f"Codes cannot be both retriable and fatal: {overlap}"
            )
