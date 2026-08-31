from pydantic import (
    BaseModel,
    EmailStr,
)


# =========================================================
# REGISTER
# =========================================================

class UserRegister(BaseModel):

    name: str

    email: EmailStr

    password: str


# =========================================================
# LOGIN
# =========================================================

class UserLogin(BaseModel):

    email: EmailStr

    password: str


# =========================================================
# TOKEN
# =========================================================

class TokenResponse(BaseModel):

    access_token: str

    token_type: str


# =========================================================
# USER RESPONSE
# =========================================================

class UserResponse(BaseModel):

    id: int

    name: str

    email: EmailStr


    class Config:

        from_attributes = True


# =========================================================
# CONVERSATION
# =========================================================

class ConversationCreate(
    BaseModel
):

    title: str


class ConversationResponse(
    BaseModel
):

    id: int

    title: str


    class Config:

        from_attributes = True


# =========================================================
# MESSAGE
# =========================================================

class MessageResponse(
    BaseModel
):

    id: int

    role: str

    content: str


    class Config:

        from_attributes = True