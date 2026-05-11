"""
DIMOB Tax Compliance Router — generate DIMOB XML for Receita Federal.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from fastapi.responses import Response
from app.dependencies import get_current_user, get_user_client, get_org_id, log_action
from app.responses import success_response
from app.services.dimob_service import preview_dimob, generate_dimob_xml, validate_dimob_data

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dimob", tags=["DIMOB"])


@router.get("/preview")
async def preview(
    ano: int = Query(..., ge=2000, le=2100, description="Ano de referência"),
    auth = Depends(get_current_user)):
    """Preview DIMOB data for a given year before generating XML."""
    user, token = auth
    db = get_user_client(token)

    org_id = get_org_id(user)
    data = preview_dimob(org_id, ano, db)

    return success_response(data)


@router.get("/validate")
async def validate(
    ano: int = Query(..., ge=2000, le=2100, description="Ano de referência"),
    auth = Depends(get_current_user)):
    """Validate data completeness for DIMOB generation."""
    user, token = auth
    db = get_user_client(token)

    org_id = get_org_id(user)
    data = preview_dimob(org_id, ano, db)
    warnings = validate_dimob_data(data)

    return success_response({
        "ano": ano,
        "valido": len(warnings) == 0,
        "total_avisos": len(warnings),
        "avisos": warnings,
    })


@router.post("/generate")
async def generate(
    ano: int = Query(..., ge=2000, le=2100, description="Ano de referência"),
    auth = Depends(get_current_user)):
    """Generate DIMOB XML file for download."""
    user, token = auth
    db = get_user_client(token)

    org_id = get_org_id(user)

    try:
        xml_content = generate_dimob_xml(org_id, ano, db)
    except Exception as e:
        logger.error(f"DIMOB generation failed: {e}")
        raise HTTPException(status_code=500, detail="Erro ao gerar arquivo DIMOB")

    log_action(user.id, "gerar", "dimob", None, f"Gerou DIMOB para o ano {ano}")

    # Return as XML download
    filename = f"DIMOB_{ano}.xml"
    return Response(
        content=xml_content if isinstance(xml_content, bytes) else xml_content.encode("utf-8"),
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
