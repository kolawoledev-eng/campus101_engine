from __future__ import annotations

from typing import Any, Dict, Optional

import json

from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import get_settings
from app.features.auth.schemas import (
    ActivationCheckoutRequest,
    ActivationConfirmRequest,
    DeleteAccountRequest,
    LoginRequest,
    RegisterRequest,
)
from app.features.auth.service import AuthService

router = APIRouter(prefix="/api", tags=["auth"])


def _read_bearer(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    return parts[1].strip()


def _safe_user(user: Dict[str, Any], access: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = {
        "id": user.get("id"),
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "phone": user.get("phone"),
        "email": user.get("email"),
    }
    if access:
        payload["activation_status"] = access.get("activation_status")
        payload["activation_ends_at"] = access.get("activation_ends_at")
    return payload


@router.post("/auth/register")
async def register(payload: RegisterRequest) -> Dict[str, Any]:
    try:
        svc = AuthService()
        result = svc.register(
            first_name=payload.first_name,
            last_name=payload.last_name,
            phone=payload.phone,
            email=payload.email,
            password=payload.password,
        )
        return {
            "status": "success",
            "user": _safe_user(result["user"], result["access"]),
            "token": result["token"],
            "access": {
                "is_activated": result["access"]["is_activated"],
                "free_question_limit": result["access"]["free_question_limit"],
                "free_study_notes_limit": result["access"]["free_study_notes_limit"],
                "free_novel_chapter_limit": result["access"]["free_novel_chapter_limit"],
            },
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/auth/login")
async def login(payload: LoginRequest) -> Dict[str, Any]:
    try:
        svc = AuthService()
        result = svc.login(identifier=payload.identifier, password=payload.password)
        return {
            "status": "success",
            "user": _safe_user(result["user"], result["access"]),
            "token": result["token"],
            "access": {
                "is_activated": result["access"]["is_activated"],
                "free_question_limit": result["access"]["free_question_limit"],
                "free_study_notes_limit": result["access"]["free_study_notes_limit"],
                "free_novel_chapter_limit": result["access"]["free_novel_chapter_limit"],
            },
        }
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/auth/logout")
async def logout(authorization: Optional[str] = Header(default=None)) -> Dict[str, str]:
    try:
        token = _read_bearer(authorization)
        AuthService().logout(token)
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/auth/me")
async def me(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    token = _read_bearer(authorization)
    svc = AuthService()
    user = svc.user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    access = svc.access_state(user["id"])
    return {"status": "success", "user": _safe_user(user, access)}


@router.get("/auth/access")
async def access(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    token = _read_bearer(authorization)
    svc = AuthService()
    user = svc.user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    payload = svc.access_state(user["id"])
    return {
        "status": "success",
        "is_activated": payload["is_activated"],
        "free_question_limit": payload["free_question_limit"],
        "free_study_notes_limit": payload["free_study_notes_limit"],
        "free_novel_chapter_limit": payload["free_novel_chapter_limit"],
        "blocked_message": "Activate for unlimited access",
    }


@router.get("/activation/plans")
async def activation_plans() -> Dict[str, Any]:
    return {"status": "success", "plans": AuthService().list_plans()}


@router.get("/activation/status")
async def activation_status(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    token = _read_bearer(authorization)
    svc = AuthService()
    user = svc.user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return {"status": "success", "activation": svc.activation_status(user["id"])}


@router.post("/activation/checkout")
async def activation_checkout(
    payload: ActivationCheckoutRequest,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    token = _read_bearer(authorization)
    svc = AuthService()
    user = svc.user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    try:
        result = svc.create_flutterwave_checkout(user=user, plan_code=payload.plan_code.strip())
        return {"status": "success", **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/activation/confirm")
async def activation_confirm(
    payload: ActivationConfirmRequest,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Confirm payment by ``tx_ref`` (Flutterwave verify-by-reference).

    Lets the app activate the account when webhooks are delayed or unavailable.
    """
    token = _read_bearer(authorization)
    svc = AuthService()
    user = svc.user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    try:
        result = svc.try_confirm_activation_with_tx_ref(
            user_id=user["id"],
            tx_ref=payload.tx_ref,
        )
        return {"status": "success", **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/activation/webhook/flutterwave")
async def flutterwave_webhook(
    request: Request,
    verif_hash: Optional[str] = Header(default=None, alias="verif-hash"),
) -> Dict[str, str]:
    settings = get_settings()
    expected_hash = (settings.flutterwave_secret_hash or "").strip()
    if not expected_hash:
        raise HTTPException(status_code=503, detail="Webhook hash is not configured")
    if (verif_hash or "").strip() != expected_hash:
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    raw = await request.body()
    try:
        event = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid webhook payload: {exc}") from exc
    data = event.get("data") or {}
    tx_ref = str(data.get("tx_ref") or "").strip()
    transaction_id = data.get("id")
    if not tx_ref or not transaction_id:
        raise HTTPException(status_code=400, detail="Missing tx_ref or transaction id")
    try:
        AuthService().verify_flutterwave_and_activate(tx_ref=tx_ref, transaction_id=int(transaction_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "ok"}


@router.delete("/auth/account")
async def delete_account(
    payload: DeleteAccountRequest,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, str]:
    token = _read_bearer(authorization)
    svc = AuthService()
    user = svc.user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    try:
        svc.delete_account(user["id"], payload.password)
        return {"status": "success"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

