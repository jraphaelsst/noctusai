"""
Review and rating schemas — therapist reviews, clinic reviews, responses, flags.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    """Create a review for a therapist."""

    therapist_id: str
    star_rating: int = Field(..., ge=1, le=5)
    review_text: Optional[str] = Field(default=None, max_length=2000)
    tags: Optional[list[str]] = None


class ReviewUpdate(BaseModel):
    """Update an existing review."""

    star_rating: Optional[int] = Field(default=None, ge=1, le=5)
    review_text: Optional[str] = Field(default=None, max_length=2000)
    tags: Optional[list[str]] = None


class ClinicReviewCreate(BaseModel):
    """Create a review for a clinic."""

    clinic_id: str
    star_rating: int = Field(..., ge=1, le=5)
    review_text: Optional[str] = Field(default=None, max_length=2000)
    tags: Optional[list[str]] = None


class ReviewResponseCreate(BaseModel):
    """Therapist/clinic reply to a review."""

    response_text: str = Field(..., min_length=1, max_length=2000)


class ReviewFlagRequest(BaseModel):
    """Flag a review for moderation."""

    reason: str = Field(..., min_length=5, max_length=500)
