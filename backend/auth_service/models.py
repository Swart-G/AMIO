import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    Index,
    Text,
)
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    is_active = Column(Boolean, default=False)
    verification_code = Column(String, nullable=True)

    refresh_tokens = relationship("RefreshToken", back_populates="user")
    favorite_products = relationship(
        "FavoriteProduct",
        back_populates="user",
        cascade="all, delete-orphan",
    )

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    expires_at = Column(DateTime)
    revoked = Column(Boolean, default=False)

    user = relationship("User", back_populates="refresh_tokens")


class FavoriteProduct(Base):
    __tablename__ = "favorite_products"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "marketplace",
            "product_url_canonical",
            name="uq_favorite_user_marketplace_url",
        ),
        Index("ix_favorite_products_user_id_created_at", "user_id", "created_at"),
        Index("ix_favorite_products_next_refresh_at", "next_refresh_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    marketplace = Column(String, nullable=False, index=True)
    product_url_original = Column(Text, nullable=False)
    product_url_canonical = Column(Text, nullable=False)
    product_name = Column(Text, nullable=True)
    img_url = Column(Text, nullable=True)

    last_price_amount_rub = Column(Integer, nullable=True)
    last_price_text = Column(String, nullable=True)
    last_success_price_at = Column(DateTime, nullable=True)
    last_refresh_attempt_at = Column(DateTime, nullable=True)
    last_refresh_status = Column(String, nullable=False, default="pending")
    last_refresh_error = Column(Text, nullable=True)
    next_refresh_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )

    user = relationship("User", back_populates="favorite_products")
    price_history = relationship(
        "FavoritePriceHistory",
        back_populates="favorite",
        cascade="all, delete-orphan",
    )


class FavoritePriceHistory(Base):
    __tablename__ = "favorite_price_history"
    __table_args__ = (
        UniqueConstraint("favorite_id", "bucket_hour_utc", name="uq_favorite_price_history_bucket"),
        Index("ix_favorite_price_history_favorite_id_bucket", "favorite_id", "bucket_hour_utc"),
    )

    id = Column(Integer, primary_key=True, index=True)
    favorite_id = Column(Integer, ForeignKey("favorite_products.id", ondelete="CASCADE"), nullable=False)
    bucket_hour_utc = Column(DateTime, nullable=False)
    price_amount_rub = Column(Integer, nullable=True)
    price_text = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending")
    captured_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    favorite = relationship("FavoriteProduct", back_populates="price_history")
