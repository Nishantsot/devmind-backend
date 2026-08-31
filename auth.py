import os

from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from jose import jwt, JWTError

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from fastapi import (
    Depends,
    HTTPException,
    status,
)

from fastapi.security import OAuth2PasswordBearer

from sqlalchemy.orm import Session

from database import get_db
from models import User


# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")

ALGORITHM = os.getenv(
    "ALGORITHM",
    "HS256"
)

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv(
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "60"
    )
)


if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is not set in .env"
    )


# =========================================================
# PASSWORD HASHING
# =========================================================

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:

    return password_hasher.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str
) -> bool:

    try:

        return password_hasher.verify(
            hashed_password,
            plain_password
        )

    except VerifyMismatchError:

        return False

    except Exception:

        return False


# =========================================================
# CREATE JWT TOKEN
# =========================================================

def create_access_token(data: dict):

    payload = data.copy()

    expire = (
        datetime.now(timezone.utc)
        + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    payload.update({
        "exp": expire
    })


    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


    return token


# =========================================================
# DECODE JWT TOKEN
# =========================================================

def decode_access_token(token: str):

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        return payload

    except JWTError:

        return None


# =========================================================
# OAUTH2
# =========================================================

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/login"
)


# =========================================================
# GET CURRENT LOGGED-IN USER
# =========================================================

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={
            "WWW-Authenticate": "Bearer"
        },
    )


    # Decode JWT
    payload = decode_access_token(token)


    if not payload:

        raise credentials_exception


    # Get user ID from JWT
    user_id = payload.get("sub")


    if not user_id:

        raise credentials_exception


    # Make sure ID is valid
    try:

        user_id = int(user_id)

    except (TypeError, ValueError):

        raise credentials_exception


    # Find user in Neon PostgreSQL
    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )


    if not user:

        raise credentials_exception


    return user