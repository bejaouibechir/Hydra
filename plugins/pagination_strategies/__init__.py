"""Pagination Strategies package - Stratégies de pagination pour Web API."""

from .pagination_strategy import PaginationStrategy, PaginationState
from .next_link_pagination import NextLinkPagination

__all__ = [
    "PaginationStrategy",
    "PaginationState",
    "NextLinkPagination",
]