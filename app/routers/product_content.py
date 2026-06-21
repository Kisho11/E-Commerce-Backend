import json
from typing import Any, Dict, List, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.core.dependencies import get_current_manager


router = APIRouter(prefix="/ai/product-content", tags=["AI Product Content"])

CONTENT_FIELDS = (
    "mainNote",
    "description",
    "keyFeatures",
    "whatsIncluded",
    "importantNotes",
    "additionalInformation",
)


class ProductContentGenerationRequest(BaseModel):
    product: Dict[str, Any]
    target_fields: List[
        Literal[
            "mainNote",
            "description",
            "keyFeatures",
            "whatsIncluded",
            "importantNotes",
            "additionalInformation",
        ]
    ] = Field(min_length=1, max_length=len(CONTENT_FIELDS))
    instructions: str = Field(default="", max_length=1000)


class ProductContentGenerationResponse(BaseModel):
    content: Dict[str, str]


def extract_output_text(response_data: Dict[str, Any]) -> str:
    if isinstance(response_data.get("output_text"), str):
        return response_data["output_text"]

    for output in response_data.get("output", []):
        for content in output.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]

    return ""


@router.post("/generate", response_model=ProductContentGenerationResponse)
async def generate_product_content(
    request: ProductContentGenerationRequest,
    _manager=Depends(get_current_manager),
):
    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="AI content generation is not configured")

    product_name = str(request.product.get("name") or "").strip()
    if not product_name:
        raise HTTPException(status_code=400, detail="Enter a product name before generating content")

    requested_fields = list(dict.fromkeys(request.target_fields))
    system_prompt = """You write accurate, professional UK-English ecommerce product content for retail fixtures.
Use only facts supplied in the product data or existing content. Never invent dimensions, materials, warranty terms,
stock claims, certifications, delivery promises, or included items. Omit any unsupported claim.
Return a JSON object with exactly the requested field names. Values must be concise HTML using only p, ul, ol, li,
strong, and br tags. Use bullet lists for keyFeatures, whatsIncluded, and importantNotes. Do not use Markdown."""
    user_prompt = json.dumps(
        {
            "requested_fields": requested_fields,
            "admin_instructions": request.instructions.strip(),
            "product": request.product,
        },
        ensure_ascii=False,
    )

    payload = {
        "model": settings.OPENAI_MODEL,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
        "text": {"format": {"type": "json_object"}},
    }

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json=payload,
            )
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="AI content service could not be reached") from error

    if not response.is_success:
        raise HTTPException(status_code=502, detail="AI content generation failed. Check the server API key and model configuration.")

    try:
        generated = json.loads(extract_output_text(response.json()))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=502, detail="AI content generation returned an invalid response") from error

    if not isinstance(generated, dict):
        raise HTTPException(status_code=502, detail="AI content generation returned an invalid response")

    content = {
        field: str(generated.get(field) or "").strip()
        for field in requested_fields
    }
    if not any(content.values()):
        raise HTTPException(status_code=502, detail="AI content generation returned no content")

    return {"content": content}
