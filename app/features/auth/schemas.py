from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=120)
    last_name: str = Field(..., min_length=1, max_length=120)
    phone: str = Field(..., min_length=7, max_length=30)
    email: Optional[EmailStr] = None
    password: str = Field(..., min_length=8, max_length=200)

    @field_validator("first_name", "last_name", "phone", mode="before")
    @classmethod
    def strip_required(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class LoginRequest(BaseModel):
    identifier: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=200)

    @field_validator("identifier", mode="before")
    @classmethod
    def strip_identifier(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class DeleteAccountRequest(BaseModel):
    password: str = Field(..., min_length=8, max_length=200)


class ActivationCheckoutRequest(BaseModel):
    plan_code: str = Field(..., min_length=3, max_length=40)


class ActivationConfirmRequest(BaseModel):
    tx_ref: str = Field(..., min_length=6, max_length=200)

    @field_validator("tx_ref", mode="before")
    @classmethod
    def strip_tx_ref(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

