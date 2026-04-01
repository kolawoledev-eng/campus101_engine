from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from urllib import request as urlrequest

from app.core.config import get_settings
from app.features.auth.repository import AuthRepository


class AuthService:
    def __init__(self, repo: Optional[AuthRepository] = None) -> None:
        self.repo = repo or AuthRepository()

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
        return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"

    @staticmethod
    def _verify_password(password: str, stored: str) -> bool:
        parts = (stored or "").split("$")
        if len(parts) != 3 or parts[0] != "pbkdf2_sha256":
            return False
        try:
            salt = bytes.fromhex(parts[1])
            expected = bytes.fromhex(parts[2])
        except ValueError:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
        return hmac.compare_digest(actual, expected)

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _make_session(self, user_id: str) -> str:
        raw_token = secrets.token_urlsafe(48)
        token_hash = self._token_hash(raw_token)
        self.repo.create_session(
            {
                "user_id": user_id,
                "session_token_hash": token_hash,
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            }
        )
        return raw_token

    def _resolve_access(self, user_id: str) -> Dict[str, Any]:
        active = self.repo.get_active_activation(user_id)
        return {
            "is_activated": bool(active),
            "free_question_limit": 5,
            "free_study_notes_limit": 2,
            "free_novel_chapter_limit": 2,
            "activation_status": "active" if active else "inactive",
            "activation_ends_at": (active or {}).get("ends_at"),
        }

    def register(
        self,
        *,
        first_name: str,
        last_name: str,
        phone: str,
        email: Optional[str],
        password: str,
    ) -> Dict[str, Any]:
        if self.repo.get_user_by_phone(phone):
            raise ValueError("Phone already exists")
        if email and self.repo.get_user_by_email(email):
            raise ValueError("Email already exists")
        full_name = f"{first_name.strip()} {last_name.strip()}".strip()
        user = self.repo.create_user(
            {
                "first_name": first_name.strip(),
                "last_name": last_name.strip(),
                "full_name": full_name or None,
                "phone": phone.strip(),
                "email": (email or "").strip().lower() or None,
                "password_hash": self._hash_password(password),
                "phone_verified": False,
                "email_verified": False,
                "is_deleted": False,
            }
        )
        token = self._make_session(user["id"])
        access = self._resolve_access(user["id"])
        return {"user": user, "token": token, "access": access}

    def login(self, *, identifier: str, password: str) -> Dict[str, Any]:
        ident = identifier.strip()
        user = self.repo.get_user_by_email(ident) if "@" in ident else self.repo.get_user_by_phone(ident)
        if not user:
            raise ValueError("Invalid credentials")
        if not self._verify_password(password, user.get("password_hash") or ""):
            raise ValueError("Invalid credentials")
        token = self._make_session(user["id"])
        self.repo.update_user_last_login(user["id"])
        access = self._resolve_access(user["id"])
        return {"user": user, "token": token, "access": access}

    def user_from_token(self, bearer_token: str) -> Optional[Dict[str, Any]]:
        token_hash = self._token_hash(bearer_token)
        session = self.repo.get_session_by_hash(token_hash)
        if not session:
            return None
        expires_at = session.get("expires_at")
        if expires_at:
            try:
                exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                if exp <= datetime.now(timezone.utc):
                    return None
            except ValueError:
                return None
        return self.repo.get_user_by_id(session["user_id"])

    def logout(self, bearer_token: str) -> None:
        self.repo.revoke_session(self._token_hash(bearer_token))

    def delete_account(self, user_id: str, password: str) -> None:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        if not self._verify_password(password, user.get("password_hash") or ""):
            raise ValueError("Invalid credentials")
        self.repo.mark_user_deleted(user_id)
        self.repo.revoke_all_sessions_for_user(user_id)

    def activation_status(self, user_id: str) -> Dict[str, Any]:
        active = self.repo.get_active_activation(user_id)
        if not active:
            return {
                "is_activated": False,
                "status": "inactive",
                "plan_code": None,
                "plan_name": None,
                "starts_at": None,
                "ends_at": None,
            }
        plan = active.get("activation_plans") or {}
        return {
            "is_activated": True,
            "status": "active",
            "plan_code": plan.get("code"),
            "plan_name": plan.get("name"),
            "starts_at": active.get("starts_at"),
            "ends_at": active.get("ends_at"),
        }

    def access_state(self, user_id: str) -> Dict[str, Any]:
        return self._resolve_access(user_id)

    def list_plans(self) -> list[Dict[str, Any]]:
        return self.repo.list_activation_plans()

    def create_flutterwave_checkout(self, *, user: Dict[str, Any], plan_code: str) -> Dict[str, Any]:
        settings = get_settings()
        if not settings.flutterwave_secret_key:
            raise ValueError("Flutterwave is not configured on server")
        if not settings.flutterwave_redirect_url:
            raise ValueError("Missing FLUTTERWAVE_REDIRECT_URL")
        plan = self.repo.get_activation_plan_by_code(plan_code)
        if not plan or not plan.get("is_active"):
            raise ValueError("Invalid or inactive plan")

        tx_ref = f"act_{secrets.token_urlsafe(12)}"
        amount = int(plan["price_kobo"]) / 100
        customer_name = f"{user.get('first_name') or ''} {user.get('last_name') or ''}".strip() or "Campus101 User"
        customer_email = (user.get("email") or "").strip() or f"{user['id']}@campus101.local"
        payload = {
            "tx_ref": tx_ref,
            "amount": amount,
            "currency": "NGN",
            "redirect_url": settings.flutterwave_redirect_url,
            "customer": {
                "email": customer_email,
                "phonenumber": user.get("phone") or "",
                "name": customer_name,
            },
            "meta": {
                "user_id": user["id"],
                "plan_code": plan["code"],
            },
            "customizations": {
                "title": "Campus101 Activation",
                "description": f"{plan['name']} activation",
            },
        }
        req = urlrequest.Request(
            "https://api.flutterwave.com/v3/payments",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {settings.flutterwave_secret_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=30) as res:
                body = json.loads(res.read().decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Flutterwave checkout creation failed: {exc}") from exc

        if body.get("status") != "success":
            raise ValueError(f"Flutterwave error: {body.get('message') or 'unknown'}")
        link = ((body.get("data") or {}).get("link") or "").strip()
        if not link:
            raise ValueError("Flutterwave did not return checkout link")

        self.repo.create_pending_activation(
            user_id=user["id"],
            plan_id=int(plan["id"]),
            tx_ref=tx_ref,
        )
        return {"checkout_url": link, "tx_ref": tx_ref}

    def verify_flutterwave_and_activate(self, *, tx_ref: str, transaction_id: int) -> Dict[str, Any]:
        activation = self.repo.get_activation_by_reference(tx_ref)
        if not activation:
            raise ValueError("Unknown payment reference")
        if activation.get("status") == "active":
            return {"status": "already_active"}

        settings = get_settings()
        if not settings.flutterwave_secret_key:
            raise ValueError("Flutterwave is not configured on server")
        req = urlrequest.Request(
            f"https://api.flutterwave.com/v3/transactions/{transaction_id}/verify",
            headers={
                "Authorization": f"Bearer {settings.flutterwave_secret_key}",
            },
            method="GET",
        )
        try:
            with urlrequest.urlopen(req, timeout=30) as res:
                body = json.loads(res.read().decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Flutterwave verify failed: {exc}") from exc

        if body.get("status") != "success":
            raise ValueError("Flutterwave verification not successful")
        data = body.get("data") or {}
        if str(data.get("tx_ref") or "") != tx_ref:
            raise ValueError("Payment reference mismatch")
        if str(data.get("currency") or "").upper() != "NGN":
            raise ValueError("Invalid payment currency")
        if str(data.get("status") or "").lower() != "successful":
            raise ValueError("Payment not successful")

        plan = self.repo.get_activation_plan_by_id(int(activation["plan_id"]))
        if not plan:
            raise ValueError("Activation plan not found")
        expected_amount = int(plan["price_kobo"]) / 100
        paid_amount = float(data.get("amount") or 0)
        if abs(paid_amount - expected_amount) > 0.01:
            raise ValueError("Payment amount mismatch")
        now = datetime.now(timezone.utc)
        latest_active = self.repo.get_latest_active_activation(activation["user_id"])
        base_start = now
        if latest_active:
            ends_at = latest_active.get("ends_at")
            if ends_at:
                try:
                    end_dt = datetime.fromisoformat(str(ends_at).replace("Z", "+00:00"))
                    if end_dt > now:
                        base_start = end_dt
                except ValueError:
                    pass
            self.repo.expire_active_activations(activation["user_id"])

        starts_at = base_start
        ends_at = starts_at + timedelta(days=int(plan.get("duration_days") or 30))
        self.repo.mark_activation_active(
            activation_id=activation["id"],
            starts_at_iso=starts_at.isoformat(),
            ends_at_iso=ends_at.isoformat(),
        )
        return {"status": "activated", "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()}

