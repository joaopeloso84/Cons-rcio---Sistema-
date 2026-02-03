from __future__ import annotations

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timedelta
from decimal import Decimal
import os, json, hashlib, secrets

from .db import Base, engine, get_db
from .models import User, Customer, Group, Quota, Contract, Installment, Assembly, Bid, Contemplation
from .security import hash_password, verify_password, sign_session, unsign_session
from .pdf import make_contract_pdf, make_minutes_pdf
from .services import contract_is_eligible, validate_bid, calculate_assembly

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Consorcio Portal MVP")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

FILES_DIR = os.path.join(os.path.dirname(__file__), "files")
os.makedirs(FILES_DIR, exist_ok=True)

def current_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get("session")
    if not token:
        return None
    data = unsign_session(token)
    if not data:
        return None
    uid = data.get("uid")
    if not uid:
        return None
    return db.get(User, uid)

def require_login(request: Request, db: Session) -> User:
    user = current_user(request, db)
    if not user:
        raise RedirectResponse("/login", status_code=303)
    return user

def has_role(user: User, roles: tuple[str, ...]) -> bool:
    return user.role in roles

@app.get("/files/{path:path}")
def serve_file(path: str):
    fp = os.path.join(FILES_DIR, path)
    if not os.path.abspath(fp).startswith(os.path.abspath(FILES_DIR)):
        return HTMLResponse("invalid path", status_code=400)
    if not os.path.exists(fp):
        return HTMLResponse("not found", status_code=404)
    return FileResponse(fp)

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("home.html", {"request": request, "user": user})

@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "user": None})

@app.post("/login")
def login_post(request: Request, identifier: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == identifier))
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "user": None, "flash": "Usuário não encontrado"})
    if not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "user": None, "flash": "Senha inválida"})
    token = sign_session({"uid": user.id})
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("session", token, httponly=True, samesite="lax")
    return resp

@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("session")
    return resp

@app.get("/seed")
def seed(db: Session = Depends(get_db)):
    existing = db.scalar(select(User).where(User.role == "admin"))
    if existing:
        return {"ok": True, "message": "admin already exists"}
    admin = User(
        name="Admin",
        email="admin@local",
        password_hash=hash_password("admin123"),
        role="admin",
        is_active=True
    )
    db.add(admin)
    db.commit()
    return {"ok": True, "message": "created admin admin@local / admin123"}

@app.get("/verify/contract/{contract_number}", response_class=HTMLResponse)
def verify_contract(contract_number: str, code: str = "", db: Session = Depends(get_db)):
    ct = db.scalar(select(Contract).where(Contract.contract_number == contract_number))
    if not ct:
        return HTMLResponse("Contrato não encontrado", status_code=404)
    ok = (code.upper() == (ct.verify_hash or "").upper()) if code else False
    html = f"""<html><body style="font-family:Arial;max-width:760px;margin:24px auto">
    <h2>Verificação de Contrato</h2>
    <p><b>Contrato:</b> {ct.contract_number}</p>
    <p><b>Cliente:</b> {ct.customer.full_name} (CPF {ct.customer.cpf})</p>
    <p><b>Grupo/Cota:</b> {ct.quota.group.name} — Cota {ct.quota.number}</p>
    <p><b>Status:</b> {ct.status}</p>
    <hr>
    <p><b>Código informado:</b> {code or "(vazio)"}</p>
    <p style="font-size:18px"><b>Resultado:</b> {"VÁLIDO ✅" if ok else "NÃO VALIDADO ❌"}</p>
    <p style="color:#666">Use: <code>/verify/contract/{ct.contract_number}?code=SEU_CODIGO</code></p>
    </body></html>"""
    return HTMLResponse(html)

# -------------------- ADMIN --------------------
@app.get("/admin/groups", response_class=HTMLResponse)
def admin_groups(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not has_role(user, ("admin","ops","finance")):
        return HTMLResponse("Acesso negado", status_code=403)
    groups = db.scalars(select(Group).order_by(Group.id.desc())).all()
    return templates.TemplateResponse("admin_groups.html", {"request": request, "user": user, "groups": groups})

@app.get("/admin/groups/new", response_class=HTMLResponse)
def admin_group_new_get(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not has_role(user, ("admin","ops")):
        return HTMLResponse("Acesso negado", status_code=403)
    return templates.TemplateResponse("admin_group_new.html", {"request": request, "user": user})

@app.post("/admin/groups/new")
def admin_group_new_post(
    request: Request,
    name: str = Form(...),
    segment: str = Form(...),
    total_quotas: int = Form(...),
    credit_value: float = Form(...),
    bid_min_percent: float = Form(...),
    bid_max_percent: float = Form(...),
    embedded_max_percent: float = Form(...),
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    if not has_role(user, ("admin","ops")):
        return HTMLResponse("Acesso negado", status_code=403)

    g = Group(
        name=name,
        segment=segment,
        total_quotas=total_quotas,
        credit_value=credit_value,
        bid_min_percent=bid_min_percent,
        bid_max_percent=bid_max_percent,
        embedded_max_percent=embedded_max_percent,
    )
    db.add(g); db.commit(); db.refresh(g)

    db.add_all([Quota(group_id=g.id, number=i, status="available") for i in range(1, total_quotas+1)])
    db.commit()
    return RedirectResponse("/admin/groups", status_code=303)

@app.get("/admin/customers", response_class=HTMLResponse)
def admin_customers(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not has_role(user, ("admin","ops","finance")):
        return HTMLResponse("Acesso negado", status_code=403)
    customers = db.scalars(select(Customer).order_by(Customer.id.desc())).all()
    return templates.TemplateResponse("admin_customers.html", {"request": request, "user": user, "customers": customers})

@app.get("/admin/customers/new", response_class=HTMLResponse)
def admin_customer_new_get(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not has_role(user, ("admin","ops")):
        return HTMLResponse("Acesso negado", status_code=403)
    return templates.TemplateResponse("admin_customer_new.html", {"request": request, "user": user})

@app.post("/admin/customers/new")
def admin_customer_new_post(
    request: Request,
    full_name: str = Form(...),
    cpf: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    address: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    if not has_role(user, ("admin","ops")):
        return HTMLResponse("Acesso negado", status_code=403)
    c = Customer(full_name=full_name, cpf=cpf, phone=phone or None, email=email or None, address=address or None)
    db.add(c); db.commit()
    return RedirectResponse("/admin/customers", status_code=303)

@app.get("/admin/contracts", response_class=HTMLResponse)
def admin_contracts(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not has_role(user, ("admin","ops","finance")):
        return HTMLResponse("Acesso negado", status_code=403)
    contracts = db.scalars(select(Contract).order_by(Contract.id.desc())).all()
    return templates.TemplateResponse("admin_contracts.html", {"request": request, "user": user, "contracts": contracts})

@app.get("/admin/contracts/new", response_class=HTMLResponse)
def admin_contract_new_get(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not has_role(user, ("admin","ops")):
        return HTMLResponse("Acesso negado", status_code=403)
    customers = db.scalars(select(Customer).order_by(Customer.full_name.asc())).all()
    quotas = db.scalars(select(Quota).where(Quota.status=="available").order_by(Quota.group_id.asc(), Quota.number.asc()).limit(500)).all()
    return templates.TemplateResponse("admin_contract_new.html", {"request": request, "user": user, "customers": customers, "quotas": quotas})

@app.post("/admin/contracts/new")
def admin_contract_new_post(
    request: Request,
    customer_id: int = Form(...),
    quota_id: int = Form(...),
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    if not has_role(user, ("admin","ops")):
        return HTMLResponse("Acesso negado", status_code=403)

    customer = db.get(Customer, customer_id)
    quota = db.get(Quota, quota_id)
    if not customer or not quota or quota.status != "available":
        return RedirectResponse("/admin/contracts/new", status_code=303)

    quota.status = "active"
    contract_number = f"CTR-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
    snapshot = {
        "customer": {"full_name": customer.full_name, "cpf": customer.cpf},
        "group": {"name": quota.group.name, "segment": quota.group.segment, "credit_value": float(quota.group.credit_value)},
        "quota_number": quota.number,
        "created_at": datetime.utcnow().isoformat()
    }
    verify_code = hashlib.sha256((contract_number + json.dumps(snapshot, sort_keys=True)).encode("utf-8")).hexdigest()[:16].upper()

    pdf_rel = f"contracts/{contract_number}.pdf"
    pdf_path = os.path.join(FILES_DIR, pdf_rel)
    make_contract_pdf(
        pdf_path,
        contract_number,
        customer.full_name,
        customer.cpf,
        quota.group.name,
        quota.number,
        quota.group.segment,
        float(quota.group.credit_value),
        verify_code,
    )

    ct = Contract(
        contract_number=contract_number,
        customer_id=customer.id,
        quota_id=quota.id,
        status="active",
        pdf_path=pdf_rel,
        snapshot_json=json.dumps(snapshot),
        verify_hash=verify_code,
    )
    db.add(ct); db.commit(); db.refresh(ct)

    # Portal user: CPF as login (stored in User.email for simplicity)
    if not customer.portal_user:
        db.add(User(
            name=customer.full_name.split(" ")[0] if customer.full_name else "Cliente",
            email=customer.cpf,
            password_hash=hash_password("cliente123"),
            role="client",
            is_active=True,
            customer_id=customer.id
        ))
        db.commit()

    # Sample installments (3 meses)
    today = datetime.now()
    for i in range(3):
        due = (today.replace(day=5) + timedelta(days=32*i)).replace(day=5)
        db.add(Installment(contract_id=ct.id, competence=f"{due.year:04d}-{due.month:02d}", due_date=due, amount=500.00, status="open"))
    db.commit()

    return RedirectResponse("/admin/contracts", status_code=303)

@app.get("/admin/assemblies", response_class=HTMLResponse)
def admin_assemblies(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not has_role(user, ("admin","ops","finance")):
        return HTMLResponse("Acesso negado", status_code=403)
    assemblies = db.scalars(select(Assembly).order_by(Assembly.id.desc())).all()
    return templates.TemplateResponse("admin_assemblies.html", {"request": request, "user": user, "assemblies": assemblies})

@app.get("/admin/assemblies/new", response_class=HTMLResponse)
def admin_assembly_new_get(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not has_role(user, ("admin","ops")):
        return HTMLResponse("Acesso negado", status_code=403)
    groups = db.scalars(select(Group).order_by(Group.name.asc())).all()
    return templates.TemplateResponse("admin_assembly_new.html", {"request": request, "user": user, "groups": groups})

@app.post("/admin/assemblies/new")
def admin_assembly_new_post(
    request: Request,
    group_id: int = Form(...),
    title: str = Form(...),
    opens_at: str = Form(...),
    closes_at: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    if not has_role(user, ("admin","ops")):
        return HTMLResponse("Acesso negado", status_code=403)
    fmt = "%Y-%m-%d %H:%M"
    a = Assembly(
        group_id=group_id,
        title=title,
        status="open_bids",
        opens_at=datetime.strptime(opens_at, fmt),
        closes_at=datetime.strptime(closes_at, fmt),
    )
    db.add(a); db.commit()
    return RedirectResponse("/admin/assemblies", status_code=303)

@app.get("/admin/assemblies/{assembly_id}", response_class=HTMLResponse)
def admin_assembly_detail(request: Request, assembly_id: int, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not has_role(user, ("admin","ops","finance")):
        return HTMLResponse("Acesso negado", status_code=403)
    assembly = db.get(Assembly, assembly_id)
    if not assembly:
        return HTMLResponse("Não encontrado", status_code=404)

    bids = db.scalars(select(Bid).where(Bid.assembly_id==assembly.id).order_by(Bid.created_at.desc())).all()
    contemplations = db.scalars(select(Contemplation).where(Contemplation.assembly_id==assembly.id).order_by(Contemplation.kind.asc(), Contemplation.position.asc())).all()

    minutes_rel = f"minutes/ASM-{assembly.id}.pdf"
    minutes_path = minutes_rel if os.path.exists(os.path.join(FILES_DIR, minutes_rel)) else None

    return templates.TemplateResponse("admin_assembly_detail.html", {
        "request": request, "user": user, "assembly": assembly,
        "bids": bids, "contemplations": contemplations, "minutes_path": minutes_path
    })

@app.post("/admin/assemblies/{assembly_id}/lottery")
def admin_assembly_set_lottery(
    request: Request,
    assembly_id: int,
    contest: int = Form(...),
    p1: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    if not has_role(user, ("admin","ops")):
        return HTMLResponse("Acesso negado", status_code=403)
    assembly = db.get(Assembly, assembly_id)
    if not assembly:
        return HTMLResponse("Não encontrado", status_code=404)
    assembly.lottery_contest = contest
    assembly.lottery_p1 = p1
    db.commit()
    return RedirectResponse(f"/admin/assemblies/{assembly_id}", status_code=303)

@app.post("/admin/assemblies/{assembly_id}/calculate")
def admin_assembly_calculate(request: Request, assembly_id: int, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not has_role(user, ("admin","ops")):
        return HTMLResponse("Acesso negado", status_code=403)
    assembly = db.get(Assembly, assembly_id)
    if not assembly:
        return HTMLResponse("Não encontrado", status_code=404)

    payload = calculate_assembly(db, assembly)

    minutes_rel = f"minutes/ASM-{assembly.id}.pdf"
    minutes_path = os.path.join(FILES_DIR, minutes_rel)
    make_minutes_pdf(
        minutes_path,
        title=f"{assembly.title} - {assembly.group.name}",
        lottery_contest=int(assembly.lottery_contest),
        p1=payload["p1"],
        seed=payload["seed"],
        draw_winners=payload["draw_winners"],
        bid_winners=payload["bid_winners"],
        skips=payload["skips"],
    )

    assembly.status = "published"
    db.commit()
    return RedirectResponse(f"/admin/assemblies/{assembly_id}", status_code=303)

# -------------------- PORTAL CLIENTE --------------------
@app.get("/portal", response_class=HTMLResponse)
def portal_home(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if user.role != "client":
        return RedirectResponse("/", status_code=303)

    customer = user.customer
    contract = None
    installments = []
    assemblies = []
    if customer:
        contract = db.scalar(select(Contract).where(Contract.customer_id==customer.id).order_by(Contract.id.desc()))
        if contract:
            installments = db.scalars(select(Installment).where(Installment.contract_id==contract.id).order_by(Installment.due_date.asc())).all()
            assemblies = db.scalars(select(Assembly).where(Assembly.group_id==contract.quota.group_id).order_by(Assembly.id.desc())).all()

    return templates.TemplateResponse("portal_home.html", {
        "request": request, "user": user, "contract": contract,
        "installments": installments, "assemblies": assemblies
    })

@app.get("/portal/assemblies/{assembly_id}", response_class=HTMLResponse)
def portal_assembly(request: Request, assembly_id: int, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if user.role != "client":
        return RedirectResponse("/", status_code=303)

    assembly = db.get(Assembly, assembly_id)
    if not assembly:
        return HTMLResponse("Não encontrado", status_code=404)

    customer = user.customer
    contract = db.scalar(select(Contract).where(Contract.customer_id==customer.id).order_by(Contract.id.desc())) if customer else None

    eligibility = "INAPTO"
    if contract:
        ok, reason = contract_is_eligible(db, contract)
        eligibility = "APTO" if ok else f"INAPTO ({reason})"

    my_bid = db.scalar(select(Bid).where(Bid.assembly_id==assembly_id, Bid.contract_id==(contract.id if contract else -1)))
    contemplations = db.scalars(select(Contemplation).where(Contemplation.assembly_id==assembly_id).order_by(Contemplation.kind.asc(), Contemplation.position.asc())).all()

    minutes_rel = f"minutes/ASM-{assembly.id}.pdf"
    minutes_path = minutes_rel if os.path.exists(os.path.join(FILES_DIR, minutes_rel)) else None

    return templates.TemplateResponse("portal_assembly.html", {
        "request": request, "user": user, "assembly": assembly,
        "contract": contract, "eligibility": eligibility,
        "my_bid": my_bid, "contemplations": contemplations,
        "minutes_path": minutes_path
    })

@app.post("/portal/assemblies/{assembly_id}/bid")
def portal_save_bid(
    request: Request,
    assembly_id: int,
    type: str = Form(...),
    bid_percent: float = Form(...),
    embedded_percent: float = Form(0.0),
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    if user.role != "client":
        return RedirectResponse("/", status_code=303)

    assembly = db.get(Assembly, assembly_id)
    if not assembly:
        return HTMLResponse("Não encontrado", status_code=404)

    customer = user.customer
    contract = db.scalar(select(Contract).where(Contract.customer_id==customer.id).order_by(Contract.id.desc())) if customer else None
    if not contract:
        return RedirectResponse(f"/portal/assemblies/{assembly_id}", status_code=303)

    ok, _ = contract_is_eligible(db, contract)
    if not ok:
        return RedirectResponse(f"/portal/assemblies/{assembly_id}", status_code=303)

    now = datetime.now()
    if not (assembly.opens_at <= now <= assembly.closes_at):
        return RedirectResponse(f"/portal/assemblies/{assembly_id}", status_code=303)

    group = assembly.group
    valid, _msg = validate_bid(group, Decimal(str(bid_percent)), Decimal(str(embedded_percent)))
    if not valid:
        return RedirectResponse(f"/portal/assemblies/{assembly_id}", status_code=303)

    b = db.scalar(select(Bid).where(Bid.assembly_id==assembly_id, Bid.contract_id==contract.id))
    if not b:
        b = Bid(
            assembly_id=assembly_id,
            contract_id=contract.id,
            type=type,
            credit_value=float(group.credit_value),
            bid_percent=bid_percent,
            embedded_percent=embedded_percent,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(b)
    else:
        b.type = type
        b.bid_percent = bid_percent
        b.embedded_percent = embedded_percent
        b.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(f"/portal/assemblies/{assembly_id}", status_code=303)
