"""
Standardized response utilities for the Personal Finance API.
"""
from typing import Any, Optional
import math


def success_response(data: Any, total: Optional[int] = None) -> dict:
    response = {"data": data}
    if total is not None:
        response["total"] = total
    return response


def paginated_response(data: list, total: int, page: int, page_size: int) -> dict:
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


def ok_response(message: str = "Operacao realizada com sucesso") -> dict:
    return {"ok": True, "message": message}


def deleted_response(resource: str, resource_id: str) -> dict:
    return {"ok": True, "message": f"{resource} excluido com sucesso", "deleted_id": resource_id}


def calculate_pagination(page: int, page_size: int, max_page_size: int = 200) -> tuple[int, int, int]:
    validated_page = max(1, page)
    validated_page_size = min(max(1, page_size), max_page_size)
    offset = (validated_page - 1) * validated_page_size
    return validated_page, validated_page_size, offset
