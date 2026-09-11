"""
Cursor Pagination - Pagination via curseurs opaques.

Implémentation pour APIs utilisant cursor-based pagination.
Standard utilisé par: Facebook, Twitter, Stripe, MongoDB Atlas, etc.

Exemple réponse API:
    {
        "data": [...],
        "paging": {
            "next": "MTAxNTExOTQ1MjAwNzI5NDE",
            "previous": "NDMyNzQyODI3OTQw"
        }
    }
"""

from typing import Dict, Any, Optional
from hydra_etl.plugins.pagination_strategies.pagination_strategy import (
    PaginationStrategy,
    PaginationState
)


class CursorPagination(PaginationStrategy):
    """
    Pagination via curseurs opaques.
    
    Cas d'usage:
    - Facebook Graph API: /me/posts?after=cursor
    - Twitter API: /tweets?next_token=cursor
    - Stripe API: /charges?starting_after=cursor
    - MongoDB Atlas: cursor dans response body
    
    Configuration DSL:
        sources:
          stripe_api:
            type: web_api
            pagination:
              type: cursor
              cursor_field: paging.next     # JSONPath vers cursor
              cursor_param: starting_after  # Query param name
              page_size: 100
    
    Fonctionnalités:
    - Extraction JSONPath du cursor depuis response
    - Cursor dans query param ou body
    - Support nested cursor fields
    - Protection anti-boucle (max_pages)
    """
    
    def __init__(
        self,
        cursor_field: str = "paging.next",
        cursor_param: str = "cursor",
        page_size: Optional[int] = None,
        max_pages: int = 1000
    ):
        """
        Initialise la stratégie de pagination cursor.
        
        Args:
            cursor_field: JSONPath vers cursor dans response (ex: "paging.next")
            cursor_param: Nom du query param pour cursor (ex: "cursor", "after")
            page_size: Nombre d'items par page (optionnel)
            max_pages: Limite anti-boucle infinie (défaut: 1000)
        
        Examples:
            >>> # Facebook-style
            >>> strategy = CursorPagination(
            ...     cursor_field="paging.next",
            ...     cursor_param="after"
            ... )
            >>> 
            >>> # Stripe-style
            >>> strategy = CursorPagination(
            ...     cursor_field="has_more",
            ...     cursor_param="starting_after",
            ...     page_size=100
            ... )
        """
        self._cursor_field = cursor_field
        self._cursor_param = cursor_param
        self._page_size = page_size
        self._max_pages = max_pages
        self._pages_fetched = 0
    
    def get_initial_params(self) -> Dict[str, Any]:
        """
        Retourne paramètres pour première requête.
        
        Returns:
            Dict avec page_size si configuré.
        """
        self._pages_fetched = 0
        
        params = {}
        if self._page_size:
            # Noms courants pour page size
            params["limit"] = self._page_size
        
        return params
    
    def get_next_page(
        self,
        response_data: Any,
        response_headers: Dict[str, str],
        current_url: str
    ) -> PaginationState:
        """
        Extrait cursor depuis response pour page suivante.
        
        Args:
            response_data: Body response (dict si JSON)
            response_headers: Headers HTTP (non utilisés ici)
            current_url: URL actuelle
        
        Returns:
            PaginationState avec cursor dans next_params.
        
        Examples:
            >>> # Response: {"data": [...], "paging": {"next": "abc123"}}
            >>> state = strategy.get_next_page(
            ...     response_data={"data": [...], "paging": {"next": "abc123"}},
            ...     response_headers={},
            ...     current_url="https://api.example.com/items"
            ... )
            >>> state.has_more
            True
            >>> state.next_params
            {"cursor": "abc123"}
        """
        self._pages_fetched += 1
        
        # Protection anti-boucle
        if self._pages_fetched >= self._max_pages:
            return PaginationState(has_more=False)
        
        # Extraire cursor depuis response
        cursor = self._extract_cursor(response_data)
        
        if not cursor:
            return PaginationState(has_more=False)
        
        # Construire params pour next request
        next_params = {self._cursor_param: cursor}
        
        if self._page_size:
            next_params["limit"] = self._page_size
        
        return PaginationState(
            has_more=True,
            next_params=next_params,
            next_url=None  # Utiliser params, pas URL complète
        )
    
    def _extract_cursor(self, response_data: Any) -> Optional[str]:
        """
        Extrait cursor depuis response via JSONPath simple.
        
        Args:
            response_data: Response body (dict)
        
        Returns:
            Cursor string ou None si absent.
        
        Examples:
            >>> # Cursor simple
            >>> self._extract_cursor({"next_cursor": "abc"})
            "abc"
            >>> 
            >>> # Cursor nested
            >>> self._extract_cursor({"paging": {"next": "abc"}})
            "abc"
        """
        if not isinstance(response_data, dict):
            return None
        
        # Parser cursor_field (ex: "paging.next" → ["paging", "next"])
        fields = self._cursor_field.split(".")
        
        # Naviguer dans dict
        current = response_data
        for field in fields:
            if isinstance(current, dict) and field in current:
                current = current[field]
            else:
                return None
        
        # Vérifier que c'est un string non-vide
        if isinstance(current, str) and current:
            return current
        
        # Support boolean pour "has_more" (Stripe style)
        if isinstance(current, bool):
            if current:
                # has_more=true, extraire last item id comme cursor
                return self._extract_last_item_id(response_data)
            else:
                return None
        
        return None
    
    def _extract_last_item_id(self, response_data: dict) -> Optional[str]:
        """
        Extrait ID du dernier item pour pagination Stripe-style.
        
        Stripe utilise: has_more=true + starting_after=<last_id>
        
        Args:
            response_data: Response body
        
        Returns:
            ID dernier item ou None.
        """
        # Chercher array de data (noms courants)
        data_array = None
        for key in ["data", "items", "results", "objects"]:
            if key in response_data and isinstance(response_data[key], list):
                data_array = response_data[key]
                break
        
        if not data_array or len(data_array) == 0:
            return None
        
        # Dernier item
        last_item = data_array[-1]
        
        if not isinstance(last_item, dict):
            return None
        
        # Chercher ID (noms courants)
        for id_field in ["id", "_id", "ID", "uuid"]:
            if id_field in last_item:
                item_id = last_item[id_field]
                if isinstance(item_id, (str, int)):
                    return str(item_id)
        
        return None
    
    def validate(self) -> None:
        """
        Valide la configuration.
        
        Raises:
            ValueError: Si paramètres invalides.
        """
        if not self._cursor_field:
            raise ValueError("cursor_field cannot be empty")
        
        if not self._cursor_param:
            raise ValueError("cursor_param cannot be empty")
        
        if self._page_size is not None:
            if not isinstance(self._page_size, int) or self._page_size <= 0:
                raise ValueError(f"page_size must be positive integer, got: {self._page_size}")
        
        if not isinstance(self._max_pages, int) or self._max_pages <= 0:
            raise ValueError(f"max_pages must be positive integer, got: {self._max_pages}")
