from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from app.core.security import decode_access_token, safe_get_subject

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user_id(token: str = Depends(oauth2_scheme)) -> str:
    """
    Lê Authorization: Bearer <token>
    Valida access token e retorna o user_id (sub).
    """
    try:
        claims = decode_access_token(token)
        if claims.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
        return safe_get_subject(claims)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido"
        ) from None
