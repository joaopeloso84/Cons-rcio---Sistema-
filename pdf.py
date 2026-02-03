import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

def br_money(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def make_contract_pdf(out_path: str, contract_number: str, customer_name: str, cpf: str,
                      group_name: str, quota_number: int, segment: str, credit_value: float,
                      verify_code: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    c = canvas.Canvas(out_path, pagesize=A4)
    w, h = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(20*mm, h-20*mm, "CONTRATO DE ADESÃO - CONSÓRCIO (MVP)")

    c.setFont("Helvetica", 11)
    y = h-35*mm
    lines = [
        f"Nº do contrato: {contract_number}",
        f"Cliente: {customer_name}",
        f"CPF: {cpf}",
        f"Grupo: {group_name} ({segment})",
        f"Cota: {quota_number}",
        f"Crédito de referência: R$ {br_money(credit_value)}",
        "",
        "Cláusulas (resumo):",
        "1) Este PDF é um modelo de MVP. Substitua pelo seu modelo jurídico real.",
        "2) O cliente tem acesso ao contrato e aos resultados de assembleias no portal.",
        "3) Inadimplência bloqueia participação em sorteio e lance.",
        "",
        f"Código de verificação: {verify_code}",
        "Use a tela de verificação do sistema para validar autenticidade."
    ]
    for line in lines:
        c.drawString(20*mm, y, line)
        y -= 6*mm

    c.showPage()
    c.save()

def make_minutes_pdf(out_path: str, title: str, group_name: str, segment: str, total_quotas: int,
                     lottery_contest: int, p1: str, rule_text: str, seed_components: dict,
                     draw_winners: list[dict], bid_winners: list[dict], skips: list[dict],
                     verify_code: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    c = canvas.Canvas(out_path, pagesize=A4)
    w, h = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(20*mm, h-20*mm, "ATA DE ASSEMBLEIA (MVP)")

    c.setFont("Helvetica", 11)
    y = h-35*mm
    c.drawString(20*mm, y, f"Assembleia: {title}")
    y -= 6*mm
    c.drawString(20*mm, y, f"Grupo: {group_name} ({segment}) | Total de cotas: {total_quotas}")
    y -= 6*mm
    c.drawString(20*mm, y, f"Loteria Federal - Concurso: {lottery_contest} | 1º prêmio: {p1}")
    y -= 10*mm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(20*mm, y, "Regra do sorteio (padrão para 500 cotas):")
    y -= 7*mm
    c.setFont("Helvetica", 10)
    for part in rule_text.split("\n"):
        c.drawString(20*mm, y, part[:120])
        y -= 5*mm

    y -= 5*mm
    c.setFont("Helvetica", 11)
    c.drawString(20*mm, y, f"Componentes: A={seed_components['A']} B={seed_components['B']} C={seed_components['C']} D={seed_components['D']}")
    y -= 10*mm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(20*mm, y, "Contemplações por Sorteio (4):")
    y -= 7*mm
    c.setFont("Helvetica", 11)
    for wnr in draw_winners:
        c.drawString(25*mm, y, f"{wnr['position']}. Cota {wnr['quota_number']} - Contrato {wnr['contract_number']}")
        y -= 6*mm

    y -= 6*mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20*mm, y, "Contemplações por Lance (3):")
    y -= 7*mm
    c.setFont("Helvetica", 11)
    for wnr in bid_winners:
        c.drawString(25*mm, y, f"{wnr['position']}. Contrato {wnr['contract_number']} - {wnr['bid_percent']}% (embutido {wnr['embedded_percent']}%)")
        y -= 6*mm

    if skips:
        y -= 10*mm
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20*mm, y, "Substituições (cota inapta/repetida):")
        y -= 7*mm
        c.setFont("Helvetica", 11)
        for s in skips[:12]:
            c.drawString(25*mm, y, f"Cota {s['quota']} -> {s['moved_to']} ({s['reason']})")
            y -= 6*mm

    y -= 10*mm
    c.setFont("Helvetica", 11)
    c.drawString(20*mm, y, f"Código de verificação da ata: {verify_code}")
    y -= 6*mm
    c.setFont("Helvetica", 10)
    c.drawString(20*mm, y, "Esta ata é um modelo MVP. Ajuste o texto conforme seu regulamento/jurídico.")
    c.showPage()
    c.save()
