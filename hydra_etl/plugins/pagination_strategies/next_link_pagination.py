"""
Next Link Pagination - Pagination via header HTTP Link.

Implémentation MVP pour APIs utilisant RFC 5988 (Web Linking).
Standard utilisé par: GitHub, GitLab, etc.

Exemple header Link:
    Link: <https://api.example.com/items?page=2>; rel="next",
          <https://api.example.com/items?page=5>; rel="last"
"""

from typing import Dict, Any, Optional
import re
from urllib.parse import urlparse, parse_qs
from .pagination_strategy import PaginationStrategy, PaginationState


class NextLinkPagination(PaginationStrategy):
    """
    Pagination via header HTTP Link avec rel="next".
    
    Cas d'usage:
    - GitHub API: /repos/owner/repo/issues
    - GitLab API: /projects/:id/issues
    - Toute API respectant RFC 5988
    
    Configuration DSL:
        sources:
          github_api:
            type: web_api
            pagination:
              type: next_link
              page_size: 100  # optionnel
    
    Fonctionnalités:
    - Parse header Link automatiquement
    - Supporte URLs relatives et absolues
    - Protection anti-boucle infinie
    """
    
    def __init__(self, page_size: Optional[int] = None, max_pages: int = 1000):
        """
        Initialise la stratégie de pagination Link.
        
        Args:
            page_size: Nombre d'items par page (optionnel, dépend de l'API)
            max_pages: Limite de sécurité anti-boucle infinie (défaut: 1000)
        
        Examples:
            >>> strategy = NextLinkPagination(page_size=100)
        """
        self._page_size = page_size
        self._max_pages = max_pages
        self._pages_fetched = 0
    
    def get_initial_params(self) -> Dict[str, Any]:
        """
        Retourne paramètres pour première requête.
        
        Returns:
            Dict avec page_size si configuré, sinon vide.
        """
        self._pages_fetched = 0
        
        if self._page_size:
            # Noms de params courants pour page size
            # L'API choisira celui qu'elle comprend
            return {"per_page": self._page_size}
        
        return {}
    
    def get_next_page(
        self,
        response_data: Any,
        response_headers: Dict[str, str],
        current_url: str
    ) -> PaginationState:
        """
        Parse le header Link pour trouver rel="next".
        
        Args:
            response_data: Non utilisé pour cette stratégie
            response_headers: Doit contenir "Link" si pagination disponible
            current_url: URL actuelle (pour URLs relatives)
        
        Returns:
            PaginationState avec next_url si disponible.
        
        Examples:
            >>> headers = {
            ...     "Link": '<https://api.github.com/repos/org/repo/issues?page=2>; rel="next"'
            ... }
            >>> state = strategy.get_next_page({}, headers, "https://api.github.com/...")
            >>> state.has_more
            True
            >>> state.next_url
            "https://api.github.com/repos/org/repo/issues?page=2"
        """
        self._pages_fetched += 1
        
        # Protection anti-boucle infinie
        if self._pages_fetched >= self._max_pages:
            return PaginationState(
                has_more=False,
                next_params=None,
                next_url=None
            )
        
        # Chercher header Link
        link_header = response_headers.get("Link") or response_headers.get("link")
        
        if not link_header:
            # Pas de header Link = fin de pagination
            return PaginationState(has_more=False)
        
        # Parser header Link pour trouver rel="next"
        next_url = self._parse_link_header(link_header)
        
        if not next_url:
            return PaginationState(has_more=False)
        
        return PaginationState(
            has_more=True,
            next_url=next_url,
            next_params=None  # URL complète fournie
        )
    
    def validate(self) -> None:
        """
        Valide la configuration.
        
        Raises:
            ValueError: Si page_size invalide.
        """
        if self._page_size is not None:
            if not isinstance(self._page_size, int) or self._page_size <= 0:
                raise ValueError(f"page_size must be positive integer, got: {self._page_size}")
        
        if not isinstance(self._max_pages, int) or self._max_pages <= 0:
            raise ValueError(f"max_pages must be positive integer, got: {self._max_pages}")
    
    def _parse_link_header(self, link_header: str) -> Optional[str]:
        """
        Parse header Link RFC 5988 pour extraire URL avec rel="next".
        
        Format header Link:
            <url1>; rel="next", <url2>; rel="last"
        
        Args:
            link_header: Valeur du header Link
        
        Returns:
            URL de la page suivante, ou None si absent.
        
        Examples:
            >>> self._parse_link_header('<https://api.com?page=2>; rel="next"')
            "https://api.com?page=2"
            
            >>> self._parse_link_header('<https://api.com?page=2>; rel="last"')
            None
        """
        # Regex pour matcher: <URL>; rel="next"
        # Supporte aussi: rel='next' et rel=next
        pattern = r'<([^>]+)>\s*;\s*rel\s*=\s*["\']?next["\']?'
        
        match = re.search(pattern, link_header, re.IGNORECASE)
        
        if match:
            return match.group(1).strip()
        
        return None
