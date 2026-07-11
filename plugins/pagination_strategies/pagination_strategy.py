"""
Pagination Strategy Interface - Contrat pour gestion de pagination API.

Les APIs web utilisent différents mécanismes de pagination:
- Link-based: header Link avec rel="next"
- Cursor-based: {"next_cursor": "abc123", "data": [...]}
- Offset-based: ?offset=100&limit=50
- Page-based: ?page=2&per_page=50

Cette interface abstrait ces différences pour permettre l'extensibilité.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class PaginationState:
    """
    État de pagination entre requêtes.
    
    Permet au connecteur de savoir:
    - S'il reste des pages à fetcher
    - Comment construire la prochaine requête
    """
    has_more: bool
    next_params: Optional[Dict[str, Any]] = None  # Query params pour next request
    next_url: Optional[str] = None  # URL complète pour next request


class PaginationStrategy(ABC):
    """
    Interface abstraite pour stratégies de pagination.
    
    Pattern Strategy: chaque API a sa propre logique de pagination,
    le connecteur délègue à cette interface.
    
    Implémentations prévues:
    - Sprint 1: NextLinkPagination (header Link)
    - Sprint 2: CursorPagination (next_cursor dans body)
    - Sprint 3: OffsetPagination, PageNumberPagination
    """
    
    @abstractmethod
    def get_initial_params(self) -> Dict[str, Any]:
        """
        Retourne les paramètres pour la première requête.
        
        Returns:
            Dict de query params (ex: {"limit": 100})
        
        Examples:
            >>> strategy = OffsetPagination(limit=50)
            >>> strategy.get_initial_params()
            {"offset": 0, "limit": 50}
        """
        pass
    
    @abstractmethod
    def get_next_page(
        self,
        response_data: Any,
        response_headers: Dict[str, str],
        current_url: str
    ) -> PaginationState:
        """
        Détermine s'il reste des pages et comment les fetcher.
        
        Appelée après chaque requête réussie pour savoir si continuer.
        
        Args:
            response_data: Body de la réponse (dict si JSON)
            response_headers: Headers HTTP de la réponse
            current_url: URL de la requête actuelle (pour résolution relative)
        
        Returns:
            PaginationState indiquant si continuer et comment.
        
        Examples:
            >>> # API retourne: {"data": [...], "next_cursor": "abc"}
            >>> state = strategy.get_next_page(
            ...     response_data={"data": [...], "next_cursor": "abc"},
            ...     response_headers={},
            ...     current_url="https://api.example.com/items"
            ... )
            >>> state.has_more
            True
            >>> state.next_params
            {"cursor": "abc"}
        """
        pass
    
    def validate(self) -> None:
        """
        Valide la configuration de pagination.
        
        Optionnel. Permet de fail-fast si config invalide.
        
        Raises:
            ValueError: Si configuration invalide.
        """
        pass
