"""
Standardized response utilities for the ERP API.
"""
from typing import Any, Optional, TypeVar, Generic
from pydantic import BaseModel
import math


T = TypeVar("T")


class PaginationMeta(BaseModel):
    """Pagination metadata."""
    page: int
    page_size: int
    total: int
    total_pages: int


class PaginatedResponse(BaseModel, Generic[T]):
    """Standardized paginated response."""
    data: list
    pagination: PaginationMeta


def success_response(data: Any, total: Optional[int] = None) -> dict:
    """
    Create a standardized success response.

    Args:
        data: The response data (single item or list)
        total: Optional total count for list responses

    Returns:
        Standardized response dict
    """
    response = {"data": data}
    if total is not None:
        response["total"] = total
    return response


def paginated_response(
    data: list,
    total: int,
    page: int,
    page_size: int,
) -> dict:
    """
    Create a standardized paginated response.

    Args:
        data: List of items for the current page
        total: Total number of items across all pages
        page: Current page number (1-indexed)
        page_size: Number of items per page

    Returns:
        Standardized paginated response dict
    """
    total_pages = math.ceil(total / page_size) if page_size > 0 else 0

    return {
        "data": data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
    }


def ok_response(message: str = "Operação realizada com sucesso") -> dict:
    """
    Create a simple success acknowledgment response.

    Args:
        message: Success message

    Returns:
        Simple success response dict
    """
    return {"ok": True, "message": message}


def deleted_response(resource: str, resource_id: str) -> dict:
    """
    Create a standardized deletion response.

    Args:
        resource: Name of the deleted resource type
        resource_id: ID of the deleted resource

    Returns:
        Deletion confirmation response dict
    """
    return {
        "ok": True,
        "message": f"{resource} excluído com sucesso",
        "deleted_id": resource_id,
    }


def calculate_pagination(page: int, page_size: int, max_page_size: int = 200) -> tuple[int, int, int]:
    """
    Calculate pagination parameters with validation.

    Args:
        page: Requested page number
        page_size: Requested page size
        max_page_size: Maximum allowed page size

    Returns:
        Tuple of (validated_page, validated_page_size, offset)
    """
    # Ensure page is at least 1
    validated_page = max(1, page)

    # Ensure page_size is within bounds
    validated_page_size = min(max(1, page_size), max_page_size)

    # Calculate offset for database query
    offset = (validated_page - 1) * validated_page_size

    return validated_page, validated_page_size, offset
