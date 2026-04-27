"""
Circuit Breaker Policy - Fail-fast sur API down.

Implémente le pattern Circuit Breaker pour éviter cascade failures:
- 3 états: CLOSED, OPEN, HALF_OPEN
- Fail-fast quand API down (évite timeouts inutiles)
- Auto-récupération (half-open → closed)
- Thread-safe

Pattern: Circuit Breaker (Martin Fowler).
"""

import time
import threading
from enum import Enum
from typing import Optional, Callable, Any


class CircuitState(Enum):
    """États possibles du circuit breaker."""
    CLOSED = "closed"        # Normal: requêtes passent
    OPEN = "open"            # API down: requêtes bloquées
    HALF_OPEN = "half_open"  # Test: 1 requête test autorisée


class CircuitBreakerPolicy:
    """
    Politique de circuit breaker pour fail-fast.
    
    États:
    - CLOSED: Normal, toutes requêtes passent
    - OPEN: API down, requêtes bloquées (fail-fast)
    - HALF_OPEN: Test récupération (1 requête autorisée)
    
    Transitions:
    - CLOSED → OPEN: après N échecs consécutifs
    - OPEN → HALF_OPEN: après timeout
    - HALF_OPEN → CLOSED: si requête test réussit
    - HALF_OPEN → OPEN: si requête test échoue
    
    Configuration DSL:
        sources:
          api:
            type: web_api
            circuit_breaker:
              failure_threshold: 5      # Échecs avant OPEN
              timeout: 60               # Secondes avant HALF_OPEN
              half_open_requests: 3     # Tests avant CLOSED
    
    Exemples:
        >>> breaker = CircuitBreakerPolicy(
        ...     failure_threshold=5,
        ...     timeout=60
        ... )
        >>> 
        >>> # Exécuter requête avec protection
        >>> try:
        ...     result = breaker.call(lambda: requests.get("..."))
        ... except CircuitOpenError:
        ...     print("API down, fail-fast")
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        half_open_requests: int = 3,
        success_threshold: int = 2
    ):
        """
        Initialise le circuit breaker.
        
        Args:
            failure_threshold: Nombre d'échecs avant OPEN (défaut: 5)
            timeout: Secondes avant passer OPEN → HALF_OPEN (défaut: 60)
            half_open_requests: Max requêtes test en HALF_OPEN (défaut: 3)
            success_threshold: Succès consécutifs pour HALF_OPEN → CLOSED (défaut: 2)
        
        Examples:
            >>> # Configuration standard
            >>> breaker = CircuitBreakerPolicy(
            ...     failure_threshold=5,
            ...     timeout=60
            ... )
            >>> 
            >>> # Configuration agressive (fail-fast rapide)
            >>> aggressive = CircuitBreakerPolicy(
            ...     failure_threshold=3,
            ...     timeout=30
            ... )
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.half_open_requests = half_open_requests
        self.success_threshold = success_threshold
        
        # État interne
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_attempts = 0
        self._lock = threading.Lock()
    
    def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Exécute fonction avec protection circuit breaker.
        
        Args:
            func: Fonction à exécuter (ex: lambda: requests.get(...))
            *args, **kwargs: Arguments pour func
        
        Returns:
            Résultat de func si succès.
        
        Raises:
            CircuitOpenError: Si circuit OPEN (API down)
            Exception: Si func échoue (propagée)
        
        Examples:
            >>> breaker = CircuitBreakerPolicy()
            >>> 
            >>> # Wrapper autour de requête
            >>> def make_request():
            ...     response = requests.get("https://api.example.com")
            ...     response.raise_for_status()
            ...     return response.json()
            >>> 
            >>> try:
            ...     data = breaker.call(make_request)
            ... except CircuitOpenError:
            ...     # API down, fail-fast
            ...     data = get_cached_data()
        """
        # Vérifier état circuit
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Vérifier si timeout écoulé
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_attempts = 0
                else:
                    raise CircuitOpenError(
                        f"Circuit breaker OPEN (API down). "
                        f"Retry in {self._time_until_reset():.0f}s"
                    )
            
            if self._state == CircuitState.HALF_OPEN:
                # Limiter nombre de tests
                if self._half_open_attempts >= self.half_open_requests:
                    raise CircuitOpenError(
                        "Circuit breaker HALF_OPEN: max test attempts reached"
                    )
                self._half_open_attempts += 1
        
        # Exécuter fonction
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self) -> None:
        """Appelé quand requête réussit."""
        with self._lock:
            self._failure_count = 0
            
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                
                # Assez de succès → fermer circuit
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._success_count = 0
                    self._half_open_attempts = 0
    
    def _on_failure(self) -> None:
        """Appelé quand requête échoue."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                # Échec en test → réouvrir circuit
                self._state = CircuitState.OPEN
                self._success_count = 0
            
            elif self._state == CircuitState.CLOSED:
                # Trop d'échecs → ouvrir circuit
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
    
    def _should_attempt_reset(self) -> bool:
        """Vérifie si timeout écoulé pour tenter reset."""
        if self._last_failure_time is None:
            return False
        
        elapsed = time.time() - self._last_failure_time
        return elapsed >= self.timeout
    
    def _time_until_reset(self) -> float:
        """Temps restant avant tentative reset (secondes)."""
        if self._last_failure_time is None:
            return 0.0
        
        elapsed = time.time() - self._last_failure_time
        remaining = self.timeout - elapsed
        return max(0.0, remaining)
    
    def get_state(self) -> CircuitState:
        """
        Retourne l'état actuel du circuit.
        
        Returns:
            CircuitState (CLOSED, OPEN, HALF_OPEN).
        
        Examples:
            >>> breaker = CircuitBreakerPolicy()
            >>> breaker.get_state()
            <CircuitState.CLOSED: 'closed'>
        """
        with self._lock:
            return self._state
    
    def reset(self) -> None:
        """
        Force le circuit en état CLOSED.
        
        Utile pour tests ou reset manuel après maintenance.
        
        Examples:
            >>> breaker = CircuitBreakerPolicy()
            >>> # ... circuit devient OPEN après échecs
            >>> breaker.reset()  # Force CLOSED
            >>> breaker.get_state()
            <CircuitState.CLOSED: 'closed'>
        """
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            self._half_open_attempts = 0
    
    def get_metrics(self) -> dict:
        """
        Retourne métriques du circuit breaker.
        
        Utile pour monitoring/debugging.
        
        Returns:
            Dict avec state, failure_count, etc.
        
        Examples:
            >>> breaker = CircuitBreakerPolicy()
            >>> breaker.get_metrics()
            {
                'state': 'closed',
                'failure_count': 0,
                'time_until_reset': 0.0
            }
        """
        with self._lock:
            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "time_until_reset": self._time_until_reset(),
                "half_open_attempts": self._half_open_attempts,
            }
    
    def validate(self) -> None:
        """
        Valide la configuration du circuit breaker.
        
        Raises:
            ValueError: Si paramètres invalides.
        """
        if self.failure_threshold < 1:
            raise ValueError(
                f"failure_threshold must be >= 1, got: {self.failure_threshold}"
            )
        
        if self.timeout <= 0:
            raise ValueError(f"timeout must be > 0, got: {self.timeout}")
        
        if self.half_open_requests < 1:
            raise ValueError(
                f"half_open_requests must be >= 1, got: {self.half_open_requests}"
            )
        
        if self.success_threshold < 1:
            raise ValueError(
                f"success_threshold must be >= 1, got: {self.success_threshold}"
            )


class CircuitOpenError(Exception):
    """
    Exception levée quand circuit breaker est OPEN.
    
    Signale que l'API est down et que les requêtes sont bloquées
    pour éviter cascade failures.
    """
    pass
