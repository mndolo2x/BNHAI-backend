"""Conservative PDF text extraction and field parsing for invoice capture v1.

This parser deliberately does not infer member eligibility, signature validity,
clinical coding correctness, or BPOMAS tariff compatibility. Those require
verified external data or human confirmation.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import Any

from pypdf import PdfReader

MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 60

FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "invoice_number": (r"invoice\s*(?:number|no\.?|#)", r"receipt\s*(?:number|no\.?|#)"),
    "member_surname_initials": (r"member\s*(?:surname\s*(?:and|&)\s*initials|name|details)", r"subscriber\s*name"),
    "patient_first_name": (r"patient\s*(?:first\s*)?name", r"depend[ae]nt\s*name"),
    "benefit_option": (r"benefit\s*option", r"benefit\s*plan", r"option"),
    "membership_number": (r"membership\s*(?:number|no\.?|#)", r"member\s*(?:number|no\.?|#)", r"membership\s*id"),
    "practice_code": (r"practice\s*(?:code|number|no\.?|#)", r"provider\s*(?:code|number|no\.?|#)"),
    "practice_name": (r"practice\s*name", r"service\s*provider\s*name"),
    "provider_name": (r"health\s*professional", r"attending\s*practitioner", r"provider\s*name", r"doctor\s*name"),
    "service_date": (r"date\s*of\s*service", r"service\s*date", r"consultation\s*date", r"treatment\s*date"),
    "service_description": (r"nature\s*of\s*service", r"service\s*description", r"description", r"procedure\s*description", r"service\s*rendered"),
    "diagnosis_code": (r"icd\s*[- ]?10(?:\s*code)?", r"diagnosis\s*(?:code)?", r"diagnostic\s*code"),
    "tariff_code": (r"tariff\s*(?:code|item|number)?", r"item\s*code", r"procedure\s*code", r"cpt\s*code"),
    "quantity": (r"quantity", r"qty"),
    "amount": (r"total\s*amount", r"invoice\s*total", r"amount\s*due", r"amount", r"fee", r"total"),
}


def extract_pdf_text(content: bytes) -> tuple[str, int]:
    if len(content) > MAX_PDF_BYTES:
        raise ValueError(f"PDF exceeds the {MAX_PDF_BYTES // (1024 * 1024)} MB file limit.")
    if not content.startswith(b"%PDF-"):
        raise ValueError("The uploaded file is not a valid PDF document.")
    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported. Upload an authorised, unlocked copy.")
        pages = len(reader.pages)
        if pages < 1:
            raise ValueError("The PDF contains no pages.")
        if pages > MAX_PDF_PAGES:
            raise ValueError(f"PDF exceeds the {MAX_PDF_PAGES}-page limit.")
        text_parts = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(text_parts).strip(), pages
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The PDF could not be read. It may be damaged or use unsupported encryption.") from exc


def _find_label_value(text: str, label_patterns: tuple[str, ...]) -> str | None:
    labels = "|".join(f"(?:{pattern})" for pattern in label_patterns)
    pattern = re.compile(rf"^\s*(?:{labels})\s*[:#\-]\s*(.*?)\s*$", re.IGNORECASE)
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match:
            value = match.group(1).strip(" \t:;|-")
            if value:
                return value[:1000]
    # Fallback for PDFs that flatten labels and values into one line.
    inline = re.compile(rf"(?:{labels})\s*[:#\-]\s*([^\r\n|;]+)", re.IGNORECASE)
    match = inline.search(text)
    if match:
        value = match.group(1).strip(" \t:;|-")
        return value[:1000] if value else None
    return None


def _parse_date(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip()
    formats = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y")
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_amount(raw: str | None) -> float | None:
    if not raw:
        return None
    match = re.search(r"(?:BWP|P)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)", raw, re.IGNORECASE)
    if not match:
        return None
    try:
        return round(float(match.group(1).replace(",", "")), 2)
    except ValueError:
        return None


def _parse_quantity(raw: str | None) -> float | None:
    if not raw:
        return None
    match = re.search(r"\d+(?:\.\d+)?", raw)
    return float(match.group(0)) if match else None


def extract_claim_fields(text: str) -> dict[str, Any]:
    raw = {field: _find_label_value(text, labels) for field, labels in FIELD_LABELS.items()}
    patient_name = raw.get("patient_first_name")
    if patient_name:
        raw["patient_first_name"] = patient_name.split()[0]
    amount = _parse_amount(raw.get("amount"))
    quantity = _parse_quantity(raw.get("quantity"))
    service_date = _parse_date(raw.get("service_date"))
    return {
        "invoice_number": raw.get("invoice_number"),
        "member_surname_initials": raw.get("member_surname_initials"),
        "patient_first_name": raw.get("patient_first_name"),
        "benefit_option": raw.get("benefit_option"),
        "membership_number": raw.get("membership_number"),
        "practice_code": raw.get("practice_code"),
        "practice_name": raw.get("practice_name"),
        "provider_name": raw.get("provider_name"),
        "service_date": service_date,
        "service_description": raw.get("service_description"),
        "diagnosis_code": raw.get("diagnosis_code"),
        "tariff_code": raw.get("tariff_code"),
        "quantity": quantity,
        "amount": amount,
        "currency": "BWP",
        "member_signature_confirmed": None,
        "provider_signature_confirmed": None,
        "referral_document_confirmed": None,
    }


def validate_claim_fields(fields: dict[str, Any]) -> dict[str, Any]:
    required = (
        "member_surname_initials", "patient_first_name", "benefit_option", "membership_number",
        "practice_code", "practice_name", "service_date", "service_description", "diagnosis_code", "tariff_code", "amount",
    )
    missing = [name for name in required if fields.get(name) in (None, "")]
    errors: list[str] = []
    warnings = [
        "Membership eligibility and remaining benefits have not been checked against BPOMAS.",
        "ICD-10 and tariff compatibility has not been checked against a BPOMAS-approved tariff catalogue.",
        "A human reviewer must visually confirm signatures and any required supporting documents.",
    ]
    if fields.get("member_signature_confirmed") is False:
        errors.append("The reviewer marked the member/dependant acknowledgement signature as absent.")
    if fields.get("member_signature_confirmed") is not True:
        warnings.append("Member/dependant signature has not yet been confirmed by a human reviewer.")
    if fields.get("provider_signature_confirmed") is False:
        warnings.append("Provider signature was marked absent; confirm whether it is required for this invoice type.")
    if fields.get("referral_document_confirmed") is False:
        warnings.append("Referral documentation was marked absent; confirm whether it is required for this service.")
    if fields.get("service_date") and fields.get("service_date") > date.today().isoformat():
        errors.append("Service date is in the future; check the invoice.")
    if missing:
        errors.append("Required invoice information is missing: " + ", ".join(missing) + ".")
    can_approve = not errors and not missing and fields.get("member_signature_confirmed") is True
    return {
        "errors": errors,
        "warnings": warnings,
        "missing_fields": missing,
        "can_approve": can_approve,
        "validation_scope": "Basic completeness checks only; not a BPOMAS adjudication decision.",
    }
