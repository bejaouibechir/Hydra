"""
Retry Policy - Gestion des retries avec backoff exponentiel.

Implémente la logique de retry pour erreurs transitoires:
- 429 Too Many Requests (avec respect Retry-After)
- 5xx Server Errors (502, 503, 504)
- Timeouts réseau

Pattern: Policy Object pour externaliser la logique de résilience.
"""

from typing import Optional, Set
import time
import random


class RetryPolicy:
    """
    Politique de retry avec backoff exponentiel et jitter.
    
    Fonctionnalités:
    - Backoff exponentiel: 1s, 2s, 4s, 8s, ...
    - Jitter aléatoire (évite thundering herd)
    - Respect header Retry-After (429)
    - Classification erreurs retriable vs fatal
    
    Configuration DSL:
        sources:
          api:
            type: web_api
            retry:
              max_attempts: 3
              initial_backoff: 1.0
              max_backoff: 60.0
              retriable_status_codes: [429, 502, 503, 504]
    
    Exemples:
        >>> policy = RetryPolicy(max_attempts=3)
        >>> 
        >>> # Première tentative échoue avec 503
        >>> if policy.should_retry(status_code=503, attempt=1):
        ...     wait_time = policy.get_wait_time(status_code=503, attempt=1)
        ...     time.sleep(wait_time)  # Attend ~1s avec jitter
        >>> 
        >>> # Deuxième tentative échoue avec 429 + Retry-After: 30
        >>> if policy.should_retry(status_code=429, attempt=2, retry_after=30):
        ...     wait_time = policy.get_wait_time(status_code=429, attempt=2, retry_after=30)
        ...     time.sleep(wait_time)  # Attend 30s (header prioritaire)
    """
    
    # Status codes considérés comme retriable par défaut
    DEFAULT_RETRIABLE_CODES = {429, 502, 503, 504}
    
    def __init__(
        self,
        max_attempts: int = 3,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
        backoff_multiplier: float = 2.0,
        jitter: bool = True,
        retriable_status_codes: Optional[Set[int]] = None
    ):
        """
        Initialise la politique de retry.
        
        Args:
            max_attempts: Nombre maximum de tentatives (défaut: 3)
            initial_backoff: Délai initial en secondes (défaut: 1.0)
            max_backoff: Délai maximum en secondes (défaut: 60.0)
            backoff_multiplier: Multiplicateur pour backoff exponentiel (défaut: 2.0)
            jitter: Ajouter jitter aléatoire pour éviter thundering herd (défaut: True)
            retriable_status_codes: Codes HTTP retriable (défaut: 429, 502, 503, 504)
        
        Examples:
            >>> # Configuration standard
            >>> policy = RetryPolicy()
            >>> 
            >>> # Configuration agressive (retry rapide)
            >>> policy = RetryPolicy(
            ...     max_attempts=5,
            ...     initial_backoff=0.5,
            ...     max_backoff=30.0
            ... )
        """
        self.max_attempts = max_attempts
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter
        # FIX: Utiliser 'is not None' au lieu de 'or' pour supporter set() vide
        self.retriable_status_codes = retriable_status_codes if retriable_status_codes is not None else self.DEFAULT_RETRIABLE_CODES
    
    def should_retry(
        self,
        status_code: int,
        attempt: int,
        retry_after: Optional[int] = None
    ) -> bool:
        """
        Détermine si une nouvelle tentative doit être effectuée.
        
        Args:
            status_code: Code HTTP de l'erreur
            attempt: Numéro de la tentative actuelle (1-based)
            retry_after: Valeur du header Retry-After si présent
        
        Returns:
            True si retry possible, False sinon.
        
        Examples:
            >>> policy = RetryPolicy(max_attempts=3)
            >>> 
            >>> # 503 Server Error, première tentative
            >>> policy.should_retry(status_code=503, attempt=1)
            True
            >>> 
            >>> # 503 Server Error, troisième tentative (max atteint)
            >>> policy.should_retry(status_code=503, attempt=3)
            False
            >>> 
            >>> # 401 Unauthorized (non retriable)
            >>> policy.should_retry(status_code=401, attempt=1)
            False
        """
        # Vérifier si max tentatives atteint
        if attempt >= self.max_attempts:
            return False
        
        # Vérifier si code HTTP est retriable
        if status_code not in self.retriable_status_codes:
            return False
        
        return True
    
    def get_wait_time(
        self,
        status_code: int,
        attempt: int,
        retry_after: Optional[int] = None
    ) -> float:
        """
        Calcule le temps d'attente avant retry.
        
        Priorité:
        1. Header Retry-After (si présent et code 429)
        2. Backoff exponentiel avec jitter
        
        Args:
            status_code: Code HTTP de l'erreur
            attempt: Numéro de la tentative (1-based)
            retry_after: Valeur du header Retry-After en secondes
        
        Returns:
            Temps d'attente en secondes.
        
        Examples:
            >>> policy = RetryPolicy(initial_backoff=1.0, jitter=False)
            >>> 
            >>> # Première tentative: 1s
            >>> policy.get_wait_time(status_code=503, attempt=1)
            1.0
            >>> 
            >>> # Deuxième tentative: 2s
            >>> policy.get_wait_time(status_code=503, attempt=2)
            2.0
            >>> 
            >>> # 429 avec Retry-After: utilise header (prioritaire)
            >>> policy.get_wait_time(status_code=429, attempt=1, retry_after=30)
            30.0
        """
        # Priorité au header Retry-After pour 429
        if status_code == 429 and retry_after is not None:
            return float(retry_after)
        
        # Backoff exponentiel: initial * (multiplier ^ (attempt - 1))
        backoff = self.initial_backoff * (self.backoff_multiplier ** (attempt - 1))
        
        # Limiter au max_backoff
        backoff = min(backoff, self.max_backoff)
        
        # Ajouter jitter si activé (±25% aléatoire)
        if self.jitter:
            jitter_factor = random.uniform(0.75, 1.25)
            backoff *= jitter_factor
        
        return backoff
    
    def validate(self) -> None:
        """
        Valide la configuration de retry.
        
        Raises:
            ValueError: Si paramètres invalides.
        """
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be >= 1, got: {self.max_attempts}")
        
        if self.initial_backoff <= 0:
            raise ValueError(f"initial_backoff must be > 0, got: {self.initial_backoff}")
        
        if self.max_backoff <= 0:
            raise ValueError(f"max_backoff must be > 0, got: {self.max_backoff}")
        
        if self.max_backoff < self.initial_backoff:
            raise ValueError(
                f"max_backoff ({self.max_backoff}) must be >= initial_backoff ({self.initial_backoff})"
            )
        
        if self.backoff_multiplier <= 1.0:
            raise ValueError(f"backoff_multiplier must be > 1.0, got: {self.backoff_multiplier}")
        
        if not self.retriable_status_codes:
            raise ValueError("retriable_status_codes cannot be empty")