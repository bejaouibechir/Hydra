"""
Rate Limit Policy - Limitation de débit interne avec Token Bucket.

Implémente le contrôle de débit pour éviter les bans API:
- Token Bucket algorithm (standard industrie)
- Burst support (rafales courtes tolérées)
- Thread-safe (multi-threading)
- Respect limites API

Pattern: Policy Object pour contrôle débit.
"""

import time
import threading
from typing import Optional


class RateLimitPolicy:
    """
    Politique de limitation de débit avec Token Bucket.
    
    Algorithme Token Bucket:
    - Bucket contient N tokens max
    - 1 requête consomme 1 token
    - Tokens se régénèrent à vitesse constante (requests_per_second)
    - Si bucket vide → attente régénération
    
    Fonctionnalités:
    - Rate limiting précis (requests per second)
    - Burst support (rafales courtes OK)
    - Thread-safe (lock)
    - Blocking wait (attend token disponible)
    
    Configuration DSL:
        sources:
          api:
            type: web_api
            rate_limit:
              requests_per_second: 10
              burst: 50  # max tokens accumulés
              wait_timeout: 60  # max secondes d'attente
    
    Exemples:
        >>> policy = RateLimitPolicy(requests_per_second=10, burst=20)
        >>> 
        >>> # Consommer 1 token (attend si nécessaire)
        >>> policy.acquire()  # Bloque si rate limit atteint
        >>> make_request()
        >>> 
        >>> # Vérifier sans bloquer
        >>> if policy.try_acquire(timeout=5):
        ...     make_request()
        ... else:
        ...     print("Rate limit exceeded")
    """
    
    def __init__(
        self,
        requests_per_second: float = 10.0,
        burst: int = 50,
        wait_timeout: Optional[float] = 60.0
    ):
        """
        Initialise la politique de rate limiting.
        
        Args:
            requests_per_second: Débit max en requêtes/seconde (défaut: 10)
            burst: Nombre max de tokens accumulés (défaut: 50)
            wait_timeout: Timeout max pour acquire() en secondes (défaut: 60)
        
        Examples:
            >>> # 10 req/s avec burst de 20
            >>> policy = RateLimitPolicy(
            ...     requests_per_second=10,
            ...     burst=20
            ... )
            >>> 
            >>> # Strict: 1 req/s, pas de burst
            >>> strict = RateLimitPolicy(
            ...     requests_per_second=1,
            ...     burst=1
            ... )
        """
        self.requests_per_second = requests_per_second
        self.burst = burst
        self.wait_timeout = wait_timeout
        
        # Token bucket state
        self._tokens = float(burst)  # Démarrer avec bucket plein
        self._last_update = time.time()
        self._lock = threading.Lock()
    
    def acquire(self, tokens: int = 1) -> None:
        """
        Acquiert N tokens (bloque si nécessaire).
        
        Attend jusqu'à ce que tokens disponibles ou timeout.
        
        Args:
            tokens: Nombre de tokens à consommer (défaut: 1)
        
        Raises:
            RateLimitExceeded: Si timeout dépassé
        
        Examples:
            >>> policy = RateLimitPolicy(requests_per_second=10)
            >>> policy.acquire()  # Attend si nécessaire
            >>> make_request()
        """
        start_time = time.time()
        
        while True:
            if self.try_acquire(tokens=tokens, wait=False):
                return
            
            # Vérifier timeout
            if self.wait_timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= self.wait_timeout:
                    raise RateLimitExceeded(
                        f"Rate limit timeout after {elapsed:.1f}s "
                        f"(max {self.wait_timeout}s)"
                    )
            
            # Attendre un peu avant retry
            # Sleep = temps pour générer 1 token
            sleep_time = 1.0 / self.requests_per_second
            time.sleep(sleep_time)
    
    def try_acquire(self, tokens: int = 1, wait: bool = True) -> bool:
        """
        Tente d'acquérir N tokens sans bloquer longtemps.
        
        Args:
            tokens: Nombre de tokens à consommer (défaut: 1)
            wait: Si True, attend un peu (1 cycle). Si False, retour immédiat.
        
        Returns:
            True si tokens acquis, False sinon.
        
        Examples:
            >>> policy = RateLimitPolicy(requests_per_second=10)
            >>> 
            >>> # Non-bloquant
            >>> if policy.try_acquire(wait=False):
            ...     make_request()
            ... else:
            ...     print("Rate limited, skip")
            >>> 
            >>> # Attend 1 cycle max
            >>> if policy.try_acquire(wait=True):
            ...     make_request()
        """
        with self._lock:
            # Régénérer tokens
            self._refill()
            
            # Vérifier si tokens disponibles
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            
            # Pas assez de tokens
            if not wait:
                return False
        
        # Wait = True : attendre 1 cycle de régénération
        sleep_time = tokens / self.requests_per_second
        time.sleep(sleep_time)
        
        # Retry après wait
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False
    
    def _refill(self) -> None:
        """
        Régénère tokens selon temps écoulé.
        
        Appelée automatiquement par acquire() et try_acquire().
        Thread-safe (caller doit avoir lock).
        """
        now = time.time()
        elapsed = now - self._last_update
        
        # Calculer tokens générés
        tokens_to_add = elapsed * self.requests_per_second
        
        # Ajouter tokens (limité par burst)
        self._tokens = min(self._tokens + tokens_to_add, self.burst)
        
        # Mettre à jour timestamp
        self._last_update = now
    
    def reset(self) -> None:
        """
        Réinitialise le bucket (utile pour tests).
        
        Examples:
            >>> policy = RateLimitPolicy(requests_per_second=10)
            >>> # Consommer tous tokens
            >>> for _ in range(50): policy.try_acquire(wait=False)
            >>> # Reset
            >>> policy.reset()
            >>> policy.try_acquire(wait=False)  # True (bucket plein)
        """
        with self._lock:
            self._tokens = float(self.burst)
            self._last_update = time.time()
    
    def get_available_tokens(self) -> float:
        """
        Retourne nombre de tokens disponibles actuellement.
        
        Utile pour monitoring/debugging.
        
        Returns:
            Nombre de tokens disponibles (float).
        
        Examples:
            >>> policy = RateLimitPolicy(requests_per_second=10, burst=50)
            >>> policy.get_available_tokens()
            50.0
            >>> policy.acquire()
            >>> policy.get_available_tokens()
            49.0
        """
        with self._lock:
            self._refill()
            return self._tokens
    
    def validate(self) -> None:
        """
        Valide la configuration de rate limiting.
        
        Raises:
            ValueError: Si paramètres invalides.
        """
        if self.requests_per_second <= 0:
            raise ValueError(
                f"requests_per_second must be > 0, got: {self.requests_per_second}"
            )
        
        if self.burst < 1:
            raise ValueError(f"burst must be >= 1, got: {self.burst}")
        
        if self.wait_timeout is not None and self.wait_timeout <= 0:
            raise ValueError(f"wait_timeout must be > 0 or None, got: {self.wait_timeout}")


class RateLimitExceeded(Exception):
    """
    Exception levée quand rate limit timeout dépassé.
    
    Utilisée pour distinguer:
    - Timeout rate limit (wait trop long)
    - Autres erreurs
    """
    pass
