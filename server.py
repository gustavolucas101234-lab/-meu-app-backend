from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="Imaginei Dashboard API")
api_router = APIRouter(prefix="/api")


# =========================
# Models
# =========================
class DocItem(BaseModel):
    desc: str = ""
    url: str = ""


class Payment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    date: str  # ISO date (yyyy-mm-dd) or dd/mm
    amount: float = 0
    method: str = ""
    note: str = ""


class Client(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    month: str
    nome: str
    insta: str = ""
    tel: str = ""
    fechou: str = ""
    alerta: str = ""
    alertaTipo: str = "info"  # info | warn | danger
    quem: str = ""
    prevNasc: str = ""
    urgente: str = "Não"
    envio: str = ""
    endereco: str = ""
    categoria: str = "Bebê (bordado)"
    pecas: str = ""
    bordado: str = ""
    obsTec: str = ""
    arteEnviada: str = "Não"
    etapa: str = "Aguardando arte"
    prazoFab: str = ""
    prazoCliente: str = ""
    fotoEnviada: str = "Não"
    saida: str = ""
    docs: Dict[str, DocItem] = Field(default_factory=lambda: {
        "vendaCA": DocItem(desc="Venda CA"),
        "nf": DocItem(desc=""),
        "relatorio": DocItem(desc="Relatório"),
        "prod": DocItem(desc="Prod."),
    })
    total: float = 0
    recebido: float = 0
    entrada: float = 0
    adicional: float = 0
    pagFinal: float = 0
    forma: str = ""
    statusFin: str = "Pendente"  # Pendente | Parcial | Quitado
    payments: List[Payment] = Field(default_factory=list)
    createdAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ClientCreate(BaseModel):
    month: str
    nome: str
    insta: str = ""
    tel: str = ""
    fechou: str = ""
    alerta: str = ""
    urgente: str = "Não"
    envio: str = ""
    total: float = 0
    entrada: float = 0
    forma: str = ""


class ClientUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nome: Optional[str] = None
    insta: Optional[str] = None
    tel: Optional[str] = None
    fechou: Optional[str] = None
    alerta: Optional[str] = None
    alertaTipo: Optional[str] = None
    quem: Optional[str] = None
    prevNasc: Optional[str] = None
    urgente: Optional[str] = None
    envio: Optional[str] = None
    endereco: Optional[str] = None
    categoria: Optional[str] = None
    pecas: Optional[str] = None
    bordado: Optional[str] = None
    obsTec: Optional[str] = None
    arteEnviada: Optional[str] = None
    etapa: Optional[str] = None
    prazoFab: Optional[str] = None
    prazoCliente: Optional[str] = None
    fotoEnviada: Optional[str] = None
    saida: Optional[str] = None
    docs: Optional[Dict[str, DocItem]] = None
    total: Optional[float] = None
    entrada: Optional[float] = None
    adicional: Optional[float] = None
    pagFinal: Optional[float] = None
    forma: Optional[str] = None
    statusFin: Optional[str] = None
    month: Optional[str] = None


class Month(BaseModel):
    name: str
    createdAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MonthCreate(BaseModel):
    name: str


# =========================
# Helpers
# =========================
def recalc_fin(c: dict):
    rec = (c.get("entrada") or 0) + (c.get("adicional") or 0) + (c.get("pagFinal") or 0)
    c["recebido"] = rec
    total = c.get("total") or 0
    if total > 0 and rec >= total:
        c["statusFin"] = "Quitado"
    elif rec > 0:
        c["statusFin"] = "Parcial"
    else:
        c["statusFin"] = "Pendente"
    return c


async def ensure_default_month():
    count = await db.months.count_documents({})
    if count == 0:
        now = datetime.now()
        months_pt = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                     "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        default_name = f"{months_pt[now.month - 1]} {now.year}"
        m = Month(name=default_name)
        await db.months.insert_one(m.model_dump())


# =========================
# Months endpoints
# =========================
@api_router.get("/months", response_model=List[Month])
async def list_months():
    await ensure_default_month()
    docs = await db.months.find({}, {"_id": 0}).sort("createdAt", 1).to_list(1000)
    return docs


@api_router.post("/months", response_model=Month)
async def create_month(payload: MonthCreate):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome do mês obrigatório")
    exists = await db.months.find_one({"name": name})
    if exists:
        raise HTTPException(status_code=400, detail="Esse mês já existe")
    m = Month(name=name)
    await db.months.insert_one(m.model_dump())
    return m


@api_router.delete("/months/{name}")
async def delete_month(name: str):
    total_months = await db.months.count_documents({})
    if total_months <= 1:
        raise HTTPException(status_code=400, detail="Você precisa ter pelo menos um mês")
    await db.clients.delete_many({"month": name})
    res = await db.months.delete_one({"name": name})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Mês não encontrado")
    return {"ok": True}


# =========================
# Clients endpoints
# =========================
@api_router.get("/clients", response_model=List[Client])
async def list_clients(month: Optional[str] = None):
    q = {"month": month} if month else {}
    docs = await db.clients.find(q, {"_id": 0}).sort("createdAt", 1).to_list(5000)
    return docs


@api_router.post("/clients", response_model=Client)
async def create_client(payload: ClientCreate):
    nome = payload.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome obrigatório")
    month_exists = await db.months.find_one({"name": payload.month})
    if not month_exists:
        # create month silently
        await db.months.insert_one(Month(name=payload.month).model_dump())

    fechou = payload.fechou.strip() or datetime.now().strftime("%d/%m")
    insta = payload.insta.strip() or ("@" + nome.split(" ")[0].lower())

    c = Client(
        month=payload.month,
        nome=nome,
        insta=insta,
        tel=payload.tel.strip(),
        fechou=fechou,
        alerta=payload.alerta.strip(),
        alertaTipo="danger" if payload.urgente == "Sim" else "info",
        urgente=payload.urgente,
        envio=payload.envio.strip(),
        total=payload.total,
        entrada=payload.entrada,
        forma=payload.forma.strip(),
    )
    c_dict = c.model_dump()
    recalc_fin(c_dict)
    await db.clients.insert_one(c_dict)
    saved = await db.clients.find_one({"id": c.id}, {"_id": 0})
    return saved


@api_router.put("/clients/{client_id}", response_model=Client)
async def update_client(client_id: str, payload: ClientUpdate):
    existing = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Cliente não encontrada")
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if "docs" in updates and updates["docs"] is not None:
        updates["docs"] = {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in updates["docs"].items()}
    existing.update(updates)
    # recompute finances if money fields touched
    if any(k in updates for k in ("entrada", "adicional", "pagFinal", "total")):
        recalc_fin(existing)
    await db.clients.update_one({"id": client_id}, {"$set": existing})
    return existing


@api_router.delete("/clients/{client_id}")
async def delete_client(client_id: str):
    res = await db.clients.delete_one({"id": client_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Cliente não encontrada")
    return {"ok": True}


# =========================
# Payments endpoints
# =========================
class PaymentCreate(BaseModel):
    date: str
    amount: float
    method: str = ""
    note: str = ""


@api_router.post("/clients/{client_id}/payments", response_model=Client)
async def add_payment(client_id: str, payload: PaymentCreate):
    existing = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Cliente não encontrada")
    p = Payment(date=payload.date, amount=payload.amount, method=payload.method, note=payload.note)
    existing.setdefault("payments", []).append(p.model_dump())
    # also add to "adicional" bucket so totals stay consistent
    existing["adicional"] = (existing.get("adicional") or 0) + payload.amount
    recalc_fin(existing)
    await db.clients.update_one({"id": client_id}, {"$set": existing})
    return existing


@api_router.delete("/clients/{client_id}/payments/{payment_id}", response_model=Client)
async def delete_payment(client_id: str, payment_id: str):
    existing = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Cliente não encontrada")
    payments = existing.get("payments", [])
    removed = next((p for p in payments if p.get("id") == payment_id), None)
    if not removed:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")
    existing["payments"] = [p for p in payments if p.get("id") != payment_id]
    existing["adicional"] = max(0, (existing.get("adicional") or 0) - (removed.get("amount") or 0))
    recalc_fin(existing)
    await db.clients.update_one({"id": client_id}, {"$set": existing})
    return existing


# =========================
# Stats endpoint
# =========================
@api_router.get("/stats")
async def get_stats():
    docs = await db.clients.find({}, {"_id": 0}).to_list(10000)
    months_data: Dict[str, Dict[str, float]] = {}
    stage_counts: Dict[str, int] = {}
    status_counts = {"Pendente": 0, "Parcial": 0, "Quitado": 0}
    for c in docs:
        m = c.get("month", "—")
        md = months_data.setdefault(m, {"total": 0, "recebido": 0, "areceber": 0, "clientes": 0})
        md["total"] += c.get("total") or 0
        md["recebido"] += c.get("recebido") or 0
        md["areceber"] += (c.get("total") or 0) - (c.get("recebido") or 0)
        md["clientes"] += 1
        stage = c.get("etapa") or "—"
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        sf = c.get("statusFin") or "Pendente"
        status_counts[sf] = status_counts.get(sf, 0) + 1

    by_month = [{"month": k, **v} for k, v in months_data.items()]
    by_stage = [{"name": k, "value": v} for k, v in stage_counts.items()]
    by_status = [{"name": k, "value": v} for k, v in status_counts.items()]
    return {"by_month": by_month, "by_stage": by_stage, "by_status": by_status, "total_clients": len(docs)}


@api_router.get("/")
async def root():
    return {"message": "Imaginei Dashboard API"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
