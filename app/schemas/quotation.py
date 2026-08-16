from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator


class QuotationRequestCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    phone: str = Field(..., min_length=5, max_length=40)
    requirements: list[str] = Field(default_factory=list, max_length=20)
    message: str = Field(..., min_length=3, max_length=4000)
    wants_catalogue: bool = False

    @field_validator("full_name", "phone", "message")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field is required")
        return cleaned

    @field_validator("requirements")
    @classmethod
    def strip_requirements(cls, values: list[str]) -> list[str]:
        seen = set()
        cleaned_values = []
        for value in values:
            cleaned = str(value or "").strip()
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                cleaned_values.append(cleaned)
        return cleaned_values


class QuotationRequestResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    phone: str
    requirements: list[str] = []
    message: str
    wants_catalogue: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class QuotationRequestListResponse(BaseModel):
    items: list[QuotationRequestResponse]
    total: int
