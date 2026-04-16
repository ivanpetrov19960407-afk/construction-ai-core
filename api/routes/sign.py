"""Endpoints подписи и проверки ЭП через КриптоПро REST API."""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import create_engine, text

from config.settings import settings

router = APIRouter()


class SignDocumentRequest(BaseModel):
    """Запрос подписи документа."""

    doc_id: str
    doc_type: str
    user_id: str


_ALLOWED_DOC_TYPES = {"aosr", "ks2", "ks3"}


def _fetch_exec_doc_for_sign(doc_id: str, doc_type: str) -> dict | None:
    """Прочитать метаданные документа для подписи."""
    engine = create_engine(settings.database_url, future=True)
    query = text(
        """
        SELECT id, pdf_url, status
        FROM executive_docs
        WHERE id = :doc_id AND doc_type = :doc_type
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(query, {"doc_id": doc_id, "doc_type": doc_type}).mappings().first()
    return dict(row) if row else None


def _fetch_user_cert_thumbprint(user_id: str) -> str | None:
    """Получить thumbprint сертификата пользователя."""
    engine = create_engine(settings.database_url, future=True)
    query = text(
        """
        SELECT cert_thumbprint
        FROM users
        WHERE id = :user_id
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(query, {"user_id": user_id}).mappings().first()
    if row is None:
        return None
    return str(row.get("cert_thumbprint") or "").strip() or None


def _mark_document_signed(doc_id: str, user_id: str, sig_url: str) -> None:
    """Обновить статус подписания документа."""
    engine = create_engine(settings.database_url, future=True)
    query = text(
        """
        UPDATE executive_docs
        SET status = 'signed',
            signed_at = CURRENT_TIMESTAMP,
            signed_by = :user_id,
            sig_url = :sig_url
        WHERE id = :doc_id
        """
    )
    with engine.begin() as conn:
        conn.execute(query, {"doc_id": doc_id, "user_id": user_id, "sig_url": sig_url})


def _fetch_exec_doc_for_verify(doc_id: str) -> dict | None:
    """Прочитать метаданные документа для верификации подписи."""
    engine = create_engine(settings.database_url, future=True)
    query = text(
        """
        SELECT id, pdf_url, sig_url, signed_at
        FROM executive_docs
        WHERE id = :doc_id
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(query, {"doc_id": doc_id}).mappings().first()
    return dict(row) if row else None


async def _download_binary(url: str) -> bytes:
    """Скачать бинарный файл по URL."""
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(url)
        response.raise_for_status()
    return response.content


def _build_related_object_names(pdf_url: str) -> tuple[str, str]:
    """Собрать имена файлов для signed PDF и detached SIG рядом с оригиналом."""
    parsed = urlparse(pdf_url)
    object_path = parsed.path.lstrip("/")
    if not object_path:
        raise HTTPException(status_code=500, detail="Invalid pdf_url: cannot derive object path")

    stem = object_path[:-4] if object_path.lower().endswith(".pdf") else object_path
    return f"{stem}_signed.pdf", f"{stem}.sig"


def _upload_related_signed_files(
    signed_pdf: bytes, signature: bytes, pdf_url: str
) -> tuple[str, str]:
    """Загрузить signed PDF и detached подпись рядом с исходным документом.

    Возвращает object keys (не presigned URL), чтобы их можно было
    безопасно хранить в БД как стабильные ссылки.
    """
    import boto3

    signed_key, sig_key = _build_related_object_names(pdf_url)
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
        region_name=settings.s3_region,
        use_ssl=settings.s3_use_ssl,
    )
    client.put_object(
        Bucket=settings.s3_bucket_albums,
        Key=signed_key,
        Body=signed_pdf,
        ContentType="application/pdf",
    )
    client.put_object(
        Bucket=settings.s3_bucket_albums,
        Key=sig_key,
        Body=signature,
        ContentType="application/pkcs7-signature",
    )
    return signed_key, sig_key


def _presign_object_key(object_key: str, expires_in: int = 3600) -> str:
    """Сгенерировать presigned URL для object key."""
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
        region_name=settings.s3_region,
        use_ssl=settings.s3_use_ssl,
    )
    return str(
        client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket_albums, "Key": object_key},
            ExpiresIn=expires_in,
        )
    )


def _resolve_download_url(locator: str) -> str:
    """Преобразовать locator в URL скачивания (поддержка key и URL)."""
    if locator.startswith("http://") or locator.startswith("https://"):
        return locator
    return _presign_object_key(locator)


@router.post("/sign/document")
async def sign_document(payload: SignDocumentRequest, request: Request):
    """Подписать PDF документа через КриптоПро REST API."""
    _ = request
    if payload.doc_type not in _ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=422, detail="doc_type must be one of: aosr, ks2, ks3")

    doc = await asyncio.to_thread(
        _fetch_exec_doc_for_sign,
        payload.doc_id,
        payload.doc_type,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    pdf_url = str(doc.get("pdf_url") or "")
    if not pdf_url:
        raise HTTPException(status_code=400, detail="Document has no pdf_url")

    cert_thumbprint = await asyncio.to_thread(
        _fetch_user_cert_thumbprint,
        payload.user_id,
    )
    cert_thumbprint = cert_thumbprint or settings.cryptopro_cert_thumbprint
    if not cert_thumbprint:
        raise HTTPException(status_code=400, detail="cert_thumbprint is not configured")

    pdf_bytes = await _download_binary(pdf_url)
    data_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    sign_payload = {"data_b64": data_b64, "cert_thumbprint": cert_thumbprint}
    headers = {"Authorization": f"Bearer {settings.cryptopro_api_key}"}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.cryptopro_rest_url.rstrip('/')}/api/v1/sign",
            json=sign_payload,
            headers=headers,
        )
        response.raise_for_status()
        sign_result = response.json()

    signed_data_b64 = str(sign_result.get("signed_data_b64") or data_b64)
    signature_b64 = str(sign_result.get("signature_b64") or sign_result.get("sig_b64") or "")
    if not signature_b64:
        raise HTTPException(status_code=502, detail="CryptoPro response has no signature")

    signed_pdf = base64.b64decode(signed_data_b64)
    signature = base64.b64decode(signature_b64)

    signed_key, sig_key = await asyncio.to_thread(
        _upload_related_signed_files,
        signed_pdf,
        signature,
        pdf_url,
    )
    await asyncio.to_thread(
        _mark_document_signed,
        payload.doc_id,
        payload.user_id,
        sig_key,
    )

    signed_url = await asyncio.to_thread(_presign_object_key, signed_key)
    sig_url = await asyncio.to_thread(_presign_object_key, sig_key)

    return {"signed_url": signed_url, "sig_url": sig_url, "status": "signed"}


@router.get("/sign/verify/{doc_id}")
async def verify_signature(doc_id: str, request: Request):
    """Проверить подпись документа через КриптоПро REST API."""
    _ = request
    doc = await asyncio.to_thread(_fetch_exec_doc_for_verify, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    pdf_locator = str(doc.get("pdf_url") or "")
    sig_locator = str(doc.get("sig_url") or "")
    if not pdf_locator or not sig_locator:
        raise HTTPException(status_code=400, detail="Document has no signature artifacts")

    pdf_url = await asyncio.to_thread(_resolve_download_url, pdf_locator)
    sig_url = await asyncio.to_thread(_resolve_download_url, sig_locator)

    pdf_bytes = await _download_binary(pdf_url)
    sig_bytes = await _download_binary(sig_url)

    verify_payload = {
        "data_b64": base64.b64encode(pdf_bytes).decode("utf-8"),
        "signature_b64": base64.b64encode(sig_bytes).decode("utf-8"),
    }
    headers = {"Authorization": f"Bearer {settings.cryptopro_api_key}"}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.cryptopro_rest_url.rstrip('/')}/api/v1/verify",
            json=verify_payload,
            headers=headers,
        )
        response.raise_for_status()
        verify_result = response.json()

    signer = str(verify_result.get("signer") or "")
    signed_at = (
        verify_result.get("signed_at") or doc.get("signed_at") or datetime.utcnow().isoformat()
    )
    return {
        "valid": bool(verify_result.get("valid", False)),
        "signer": signer,
        "signed_at": signed_at,
    }
