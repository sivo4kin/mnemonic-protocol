"""Auth routes — local single-user session stub."""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Response

from ..schemas import ApiResponse, AuthUser

router = APIRouter(prefix="/auth", tags=["auth"])

# Single local user for V1
_LOCAL_USER = AuthUser(user_id="local-user", display_name="Researcher")


@router.post("/session")
async def create_session(response: Response):
    response.set_cookie("mnemonic_session", _LOCAL_USER.user_id, httponly=True)
    return ApiResponse(data=_LOCAL_USER.model_dump())


@router.get("/me")
async def get_me():
    return ApiResponse(data=_LOCAL_USER.model_dump())


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("mnemonic_session")
    return ApiResponse(data={"message": "logged out"})
