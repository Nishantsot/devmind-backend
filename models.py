from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
)

from sqlalchemy.orm import relationship

from database import Base


# =========================================================
# USER TABLE
# =========================================================

class User(Base):

    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String(100),
        nullable=False
    )

    email = Column(
        String(150),
        unique=True,
        index=True,
        nullable=False
    )

    hashed_password = Column(
        String(255),
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )


    conversations = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan"
    )


# =========================================================
# CONVERSATION TABLE
# =========================================================

class Conversation(Base):

    __tablename__ = "conversations"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    title = Column(
        String(255),
        nullable=False
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )


    user = relationship(
        "User",
        back_populates="conversations"
    )


    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )


# =========================================================
# MESSAGE TABLE
# =========================================================

class Message(Base):

    __tablename__ = "messages"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    role = Column(
        String(20),
        nullable=False
    )

    content = Column(
        Text,
        nullable=False
    )

    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id"),
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )


    conversation = relationship(
        "Conversation",
        back_populates="messages"
    )