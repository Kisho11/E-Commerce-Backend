from html import escape
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.config import settings
from app.core.dependencies import get_current_admin
from app.database import get_db
from app.models.quotation import QuotationRequest
from app.schemas.quotation import (
    QuotationRequestCreate,
    QuotationRequestListResponse,
    QuotationRequestResponse,
)
from app.utils.email import send_quotation_request_notification_email

router = APIRouter(prefix="/quotations", tags=["Quotations"])


def _excel_safe(value) -> str:
    text_value = str(value or "")
    if text_value.startswith(("=", "+", "-", "@")):
        text_value = f"'{text_value}"
    return escape(text_value)


def _format_requirements(requirements: list[str] | None) -> str:
    return ", ".join(requirements or [])


@router.post("", response_model=QuotationRequestResponse, status_code=201)
def create_quotation_request(
    payload: QuotationRequestCreate,
    db: Session = Depends(get_db),
):
    request = QuotationRequest(
        full_name=payload.full_name,
        email=str(payload.email).lower(),
        phone=payload.phone,
        requirements=payload.requirements,
        message=payload.message,
        wants_catalogue=payload.wants_catalogue,
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    try:
        send_quotation_request_notification_email(
            to_email=settings.QUOTATION_NOTIFICATION_EMAIL,
            full_name=request.full_name,
            customer_email=request.email,
            phone=request.phone,
            requirements=request.requirements or [],
            message=request.message,
            request_id=request.id,
        )
    except Exception as error:
        print(f"[QUOTATION EMAIL ERROR] {type(error).__name__}: {error}")

    return request


@router.get("/admin/requests", response_model=QuotationRequestListResponse)
def list_quotation_requests(
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    total = db.query(QuotationRequest).count()
    items = (
        db.query(QuotationRequest)
        .order_by(QuotationRequest.created_at.desc(), QuotationRequest.id.desc())
        .all()
    )
    return {"items": items, "total": total}


@router.get("/admin/requests/export")
def export_quotation_requests(
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    rows = (
        db.query(QuotationRequest)
        .order_by(QuotationRequest.created_at.desc(), QuotationRequest.id.desc())
        .all()
    )
    table_rows = "\n".join(
        f"""
        <tr>
          <td>{request.id}</td>
          <td>{_excel_safe(request.created_at.isoformat() if request.created_at else "")}</td>
          <td>{_excel_safe(request.full_name)}</td>
          <td>{_excel_safe(request.email)}</td>
          <td>{_excel_safe(request.phone)}</td>
          <td>{_excel_safe(_format_requirements(request.requirements))}</td>
          <td>{_excel_safe(request.message)}</td>
        </tr>
        """
        for request in rows
    )
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
</head>
<body>
  <table>
    <thead>
      <tr>
        <th>ID</th>
        <th>Submitted At</th>
        <th>Name</th>
        <th>Email</th>
        <th>Phone</th>
        <th>Requirements</th>
        <th>Message</th>
      </tr>
    </thead>
    <tbody>
      {table_rows}
    </tbody>
  </table>
</body>
</html>"""
    headers = {
        "Content-Disposition": 'attachment; filename="quotation-requests.xls"',
    }
    return StreamingResponse(
        iter([html.encode("utf-8")]),
        media_type="application/vnd.ms-excel; charset=utf-8",
        headers=headers,
    )
