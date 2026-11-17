from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Product(Base):
    """A product page that is checked regularly."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str | None] = mapped_column(String(300))
    # CSS selector for shops without structured data, e.g. ".price-now"
    selector: Mapped[str | None] = mapped_column(String(300))
    default_currency: Mapped[str | None] = mapped_column(String(3))
    # Send an alert when the price falls to or below this value.
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    checks: Mapped[list[PriceCheck]] = relationship(back_populates="product", cascade="all, delete-orphan")

    __table_args__ = (CheckConstraint("target_price IS NULL OR target_price > 0", name="target_price_positive"),)


class PriceCheck(Base):
    """One visit of a product page: either a price or an error."""

    __tablename__ = "price_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    in_stock: Mapped[bool | None]
    method: Mapped[str | None] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(Text)

    product: Mapped[Product] = relationship(back_populates="checks")

    __table_args__ = (
        CheckConstraint("(price IS NULL) <> (error IS NULL)", name="price_xor_error"),
        CheckConstraint("price IS NULL OR price >= 0", name="price_not_negative"),
        Index("ix_price_checks_product_time", "product_id", "checked_at"),
    )
