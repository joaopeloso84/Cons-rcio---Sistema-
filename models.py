from sqlalchemy import String, Integer, DateTime, Boolean, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .db import Base

class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(180))
    cpf: Mapped[str] = mapped_column(String(14), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    portal_user = relationship("User", back_populates="customer", uselist=False)
    contracts = relationship("Contract", back_populates="customer")

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    # admin usa email; cliente usa cpf_login
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    cpf_login: Mapped[str | None] = mapped_column(String(14), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(40), default="admin")  # admin, ops, finance, client
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    customer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("customers.id"), nullable=True)
    customer = relationship("Customer", back_populates="portal_user")

class Group(Base):
    __tablename__ = "groups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    segment: Mapped[str] = mapped_column(String(30))  # AUTO, IMOVEL, SERVICOS
    total_quotas: Mapped[int] = mapped_column(Integer, default=500)
    credit_value: Mapped[float] = mapped_column(Numeric(12,2), default=0)
    bid_min_percent: Mapped[float] = mapped_column(Numeric(6,2), default=10)
    bid_max_percent: Mapped[float] = mapped_column(Numeric(6,2), default=100)
    embedded_max_percent: Mapped[float] = mapped_column(Numeric(6,2), default=30)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    quotas = relationship("Quota", back_populates="group")
    assemblies = relationship("Assembly", back_populates="group")

class Quota(Base):
    __tablename__ = "quotas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id"))
    number: Mapped[int] = mapped_column(Integer)  # 1..total_quotas
    status: Mapped[str] = mapped_column(String(30), default="available")  # available, active, cancelled, contemplated

    group = relationship("Group", back_populates="quotas")
    contract = relationship("Contract", back_populates="quota", uselist=False)

    __table_args__ = (UniqueConstraint("group_id", "number", name="uq_group_quota_number"),)

class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"))
    quota_id: Mapped[int] = mapped_column(Integer, ForeignKey("quotas.id"))
    status: Mapped[str] = mapped_column(String(30), default="active")  # draft, active, closed, cancelled
    pdf_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    verify_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer", back_populates="contracts")
    quota = relationship("Quota", back_populates="contract")
    installments = relationship("Installment", back_populates="contract")

class Installment(Base):
    __tablename__ = "installments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[int] = mapped_column(Integer, ForeignKey("contracts.id"))
    competence: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    due_date: Mapped[datetime] = mapped_column(DateTime)
    amount: Mapped[float] = mapped_column(Numeric(12,2))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open, paid, overdue
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    contract = relationship("Contract", back_populates="installments")

class Assembly(Base):
    __tablename__ = "assemblies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id"))
    title: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="open_bids")  # open_bids, closed_bids, calculated, published
    opens_at: Mapped[datetime] = mapped_column(DateTime)
    closes_at: Mapped[datetime] = mapped_column(DateTime)

    lottery_contest: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lottery_p1: Mapped[str | None] = mapped_column(String(10), nullable=True)
    seed_string: Mapped[str | None] = mapped_column(String(120), nullable=True)

    minutes_pdf_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    group = relationship("Group", back_populates="assemblies")
    bids = relationship("Bid", back_populates="assembly")
    contemplations = relationship("Contemplation", back_populates="assembly")

class Bid(Base):
    __tablename__ = "bids"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assembly_id: Mapped[int] = mapped_column(Integer, ForeignKey("assemblies.id"))
    contract_id: Mapped[int] = mapped_column(Integer, ForeignKey("contracts.id"))
    type: Mapped[str] = mapped_column(String(20), default="percentual")  # percentual, embutido, misto
    credit_value: Mapped[float] = mapped_column(Numeric(12,2))
    bid_percent: Mapped[float] = mapped_column(Numeric(6,2))
    embedded_percent: Mapped[float] = mapped_column(Numeric(6,2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    assembly = relationship("Assembly", back_populates="bids")
    contract = relationship("Contract")

    __table_args__ = (UniqueConstraint("assembly_id", "contract_id", name="uq_bid_once_per_contract"),)

class Contemplation(Base):
    __tablename__ = "contemplations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assembly_id: Mapped[int] = mapped_column(Integer, ForeignKey("assemblies.id"))
    contract_id: Mapped[int] = mapped_column(Integer, ForeignKey("contracts.id"))
    kind: Mapped[str] = mapped_column(String(20))  # sorteio, lance
    position: Mapped[int] = mapped_column(Integer)  # 1..4 or 1..3
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    assembly = relationship("Assembly", back_populates="contemplations")
    contract = relationship("Contract")
