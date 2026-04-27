"""Pagination Strategies package - Stratégies de pagination pour Web API."""
from .pagination_strategy import PaginationStrategy, PaginationState
from .next_link_pagination import NextLinkPagination
from .cursor_pagination import CursorPagination        
from .offset_pagination import OffsetPagination        

__all__ = [
    "PaginationStrategy",
    "PaginationState",
    "NextLinkPagination",
    "CursorPagination",     
    "OffsetPagination",     
]