"""
Offset Pagination - Pagination via offset/limit.

Standard simple utilisé par beaucoup d'APIs REST.

Exemple requêtes:
    GET /items?offset=0&limit=50
    GET /items?offset=50&limit=50
    GET /items?offset=100&limit=50
"""

from typing import Dict, Any, Optional
from plugins.pagination_strategies.pagination_strategy import (
    PaginationStrategy,
    PaginationState
)


class OffsetPagination(PaginationStrategy):
    """
    Pagination offset/limit standard.
    
    Cas d'usage:
    - APIs REST simples
    - PostgreSQL OFFSET/LIMIT
    - APIs internes
    
    Configuration DSL:
        sources:
          api:
            type: web_api
            pagination:
              type: offset
              limit: 100
              offset_param: offset
              limit_param: limit
    """
    
    def __init__(
        self,
        limit: int = 100,
        offset_param: str = "offset",
        limit_param: str = "limit",
        max_pages: int = 1000
    ):
        """
        Initialise pagination offset.
        
        Args:
            limit: Items par page
            offset_param: Nom param offset
            limit_param: Nom param limit
            max_pages: Protection anti-boucle
        """
        self._limit = limit
        self._offset_param = offset_param
        self._limit_param = limit_param
        self._max_pages = max_pages
        self._current_offset = 0
        self._pages_fetched = 0
    
    def get_initial_params(self) -> Dict[str, Any]:
        """Params première requête."""
        self._current_offset = 0
        self._pages_fetched = 0
        
        return {
            self._offset_param: 0,
            self._limit_param: self._limit
        }
    
    def get_next_page(
        self,
        response_data: Any,
        response_headers: Dict[str, str],
        current_url: str
    ) -> PaginationState:
        """Calcule offset suivant."""
        self._pages_fetched += 1
        
        if self._pages_fetched >= self._max_pages:
            return PaginationState(has_more=False)
        
        # Compter items reçus
        items_count = self._count_items(response_data)
        
        # Si moins d'items que limit = dernière page
        if items_count < self._limit:
            return PaginationState(has_more=False)
        
        # Calculer next offset
        self._current_offset += self._limit
        
        return PaginationState(
            has_more=True,
            next_params={
                self._offset_param: self._current_offset,
                self._limit_param: self._limit
            }
        )
    
    def _count_items(self, response_data: Any) -> int:
        """Compte items dans response."""
        if isinstance(response_data, list):
            return len(response_data)
        
        if isinstance(response_data, dict):
            for key in ["data", "items", "results"]:
                if key in response_data and isinstance(response_data[key], list):
                    return len(response_data[key])
        
        return 0
    
    def validate(self) -> None:
        """Valide config."""
        if self._limit <= 0:
            raise ValueError(f"limit must be > 0, got: {self._limit}")
        if self._max_pages <= 0:
            raise ValueError(f"max_pages must be > 0, got: {self._max_pages}")
