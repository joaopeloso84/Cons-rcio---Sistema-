from __future__ import annotations
from datetime import datetime
from decimal import Decimal
import json, hashlib

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from .models import Group, Quota, Contract, Installment, Assembly, Bid, Contemplation

def contract_is_eligible(db: Session, contract: Contract) -> tuple[bool, str]:
    if contract.status != "active":
        return False, "contrato_nao_ativo"
    if contract.quota.status != "active":
        return False, "cota_nao_ativa"
    overdue = db.scalar(
        select(func.count(Installment.id)).where(
            Installment.contract_id == contract.id,
            Installment.status == "overdue"
        )
    )
    if overdue and overdue > 0:
        return False, "inadimplente"
    return True, "ok"

def validate_bid(group: Group, bid_percent: Decimal, embedded_percent: Decimal) -> tuple[bool, str]:
    if bid_percent < Decimal(group.bid_min_percent) or bid_percent > Decimal(group.bid_max_percent):
        return False, "percentual_fora_do_intervalo"
    if embedded_percent < Decimal("0.00"):
        return False, "embutido_invalido"
    if embedded_percent > Decimal(group.embedded_max_percent):
        return False, "embutido_acima_do_limite"
    if embedded_percent > bid_percent:
        return False, "embutido_maior_que_lance"
    return True, "ok"

def calc_components_from_p1(p1: str):
    p1 = "".join([ch for ch in str(p1) if ch.isdigit()]).zfill(5)[-5:]
    A = int(p1[0:3])
    B = int(p1[1:4])
    C = int(p1[2:5])
    D = A + B + C
    return p1, A, B, C, D

def to_quota(seed: int, total: int) -> int:
    return ((seed - 1) % total) + 1

def next_eligible_quota(db: Session, group_id: int, start_quota: int, winners_set: set[int]) -> tuple[int, dict | None]:
    total = db.scalar(select(Group.total_quotas).where(Group.id == group_id))
    assert total
    for i in range(total):
        candidate = ((start_quota - 1 + i) % total) + 1
        if candidate in winners_set:
            continue
        q = db.scalar(select(Quota).where(Quota.group_id == group_id, Quota.number == candidate))
        if not q:
            continue
        if q.status != "active":
            continue
        if not q.contract:
            continue
        ok, reason = contract_is_eligible(db, q.contract)
        if not ok:
            continue
        if i > 0:
            return candidate, {"quota": start_quota, "moved_to": candidate, "reason": "inapta_ou_repetida"}
        return candidate, None
    raise RuntimeError("Sem cotas aptas suficientes")

def calculate_assembly(db: Session, assembly: Assembly):
    group = assembly.group
    total = group.total_quotas
    if not assembly.lottery_contest or not assembly.lottery_p1:
        raise ValueError("Informe concurso e 1º prêmio")

    p1, A, B, C, D = calc_components_from_p1(assembly.lottery_p1)
    assembly.lottery_p1 = p1
    assembly.seed_string = f"{assembly.lottery_contest}|{p1}"

    # clear previous
    db.query(Contemplation).filter(Contemplation.assembly_id == assembly.id).delete()

    winners_set = set()
    skips = []
    draw_winners_payload = []

    for pos, seed_val in enumerate([A, B, C, D], start=1):
        start_quota = to_quota(seed_val, total)
        qnum, skip = next_eligible_quota(db, group.id, start_quota, winners_set)
        winners_set.add(qnum)
        if skip:
            skips.append(skip)

        quota = db.scalar(select(Quota).where(Quota.group_id == group.id, Quota.number == qnum))
        draw_winners_payload.append({
            "position": pos,
            "quota_number": qnum,
            "contract_id": quota.contract.id,
            "contract_number": quota.contract.contract_number,
        })
        db.add(Contemplation(
            assembly_id=assembly.id,
            contract_id=quota.contract.id,
            kind="sorteio",
            position=pos,
            details_json=json.dumps({"quota_number": qnum, "seed_component": [A,B,C,D][pos-1]})
        ))

    # bids ranking (3 winners), exclude contracts already in draw
    bids = db.scalars(select(Bid).where(Bid.assembly_id == assembly.id)).all()
    eligible_bids = []
    used_contracts = set([dw["contract_id"] for dw in draw_winners_payload])

    for b in bids:
        ok, _ = contract_is_eligible(db, b.contract)
        if ok and b.contract_id not in used_contracts:
            eligible_bids.append(b)

    # sort by bid_percent desc, tie by created_at asc
    eligible_bids.sort(key=lambda b: (-float(b.bid_percent), b.created_at.timestamp()))

    bid_winners_payload = []
    for rank, b in enumerate(eligible_bids[:3], start=1):
        bid_winners_payload.append({
            "position": rank,
            "contract_id": b.contract_id,
            "contract_number": b.contract.contract_number,
            "bid_percent": float(b.bid_percent),
            "embedded_percent": float(b.embedded_percent),
        })
        db.add(Contemplation(
            assembly_id=assembly.id,
            contract_id=b.contract_id,
            kind="lance",
            position=rank,
            details_json=json.dumps({"bid_percent": float(b.bid_percent), "embedded_percent": float(b.embedded_percent)})
        ))

    assembly.status = "calculated"
    db.commit()

    return {
        "p1": p1,
        "A": A, "B": B, "C": C, "D": D,
        "draw_winners": draw_winners_payload,
        "bid_winners": bid_winners_payload,
        "skips": skips
    }
