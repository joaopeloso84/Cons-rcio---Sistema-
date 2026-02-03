# Consórcio Portal MVP (Contrato + Assembleias + Lances + Portal do Cliente)

Este é um **MVP funcional** do sistema:
- Administradora (grupos separados)
- Grupos e cotas (ex.: 500 cotas)
- Clientes
- **Contrato em PDF** com **código de verificação**
- Parcelas (fase 1, sem banco)
- Assembleias:
  - **4 contemplados por sorteio** (Loteria Federal – 1º prêmio)
  - **3 contemplados por lance**
- Regras:
  - inadimplente bloqueia
  - lance min 10%, max 100%, embutido até 30%
- Portal do cliente:
  - contrato PDF
  - parcelas
  - envio/edição de lance na janela
  - ata PDF após cálculo

## Como rodar
Requisitos: Python 3.10+

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Abra no navegador: http://127.0.0.1:8000

## Criar admin
Acesse uma vez:
- http://127.0.0.1:8000/seed

Admin:
- login: `admin@local`
- senha: `admin123`

## Cliente (CPF + senha)
Quando você gera um contrato, o sistema cria automaticamente um usuário de portal:
- login: CPF do cliente (como você cadastrou)
- senha padrão: `cliente123`

## Fluxo de teste rápido
1) /seed
2) Login admin
3) Admin > Grupos > Novo grupo (gera cotas)
4) Admin > Clientes > Novo cliente
5) Admin > Contratos > Novo contrato (gera PDF e cria usuário do cliente)
6) Admin > Assembleias > Nova assembleia (janela de lances)
7) Logout
8) Login cliente (CPF + cliente123) > Portal > Abra assembleia > Envie lance
9) Login admin > Abra assembleia > Informe concurso + 1º prêmio > Calcular > Ata PDF

## Observações
- Banco: SQLite (arquivo `consorcio.db`).
- Boletos bancários entram na fase 2 quando você escolher banco/gateway.
- PDFs são templates simples (troque pelo seu modelo jurídico final).
