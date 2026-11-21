"""InvestWatch Ingestion API: persistent findings, asynchronous scan queue, smart social media scraper, scheduler and live alerts."""
import asyncio
import hashlib
import json
import logging
import os
import random
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, HttpUrl
from sqlalchemy import DateTime, Float, Integer, JSON, String, Text, create_engine, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

logger = logging.getLogger("investwatch.backend")

DB_URL = os.getenv("DATABASE_URL", "sqlite:///./investwatch.db")
AI_URL = os.getenv("AI_ENGINE_URL", "http://ai-engine:8001")
RISK_THRESHOLD = float(os.getenv("RISK_THRESHOLD", "0.70"))
SNAPSHOTS_DIR = Path("/app/snapshots")
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
]

engine = create_engine(DB_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(2048))
    source: Mapped[str] = mapped_column(String(255))
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    risk_score: Mapped[float] = mapped_column(Float)
    modules: Mapped[list] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    audit: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    snapshot_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ScanJob(Base):
    __tablename__ = "scan_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(2048))
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    finding_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ScanRequest(BaseModel):
    url: HttpUrl
    author: str | None = None

class DirectAnalyzeRequest(BaseModel):
    text: str
    url: str | None = "https://investwatch.local/custom-sample"
    author: str | None = None
    source: str | None = "manual-input"

class StatusPatch(BaseModel):
    status: str

class Hub:
    clients: list[WebSocket] = []
    async def broadcast(self, message: dict):
        for ws in self.clients[:]:
            try:
                await ws.send_json(message)
            except Exception:
                if ws in self.clients:
                    self.clients.remove(ws)

hub, jobs = Hub(), asyncio.Queue()
app = FastAPI(title="#InvestWatch Ingestion API", version="0.4.0")

# Lista celów do okresowego monitoringu (CronJob / Watchlist)
WATCHLIST = [
    {"url": "https://instagram.com/p/finfluencer-kamil-01", "author": "@kamil_inwestuje"},
    {"url": "https://aura-wealth-management.pl/oferta-vip", "author": "Aura Wealth Consulting"},
    {"url": "https://global-trade-broker.eu/kampania-knf", "author": "Global Trade Broker"},
    {"url": "https://bossa.pl/komunikat-edukacyjny-ryzyko", "author": "Dom Maklerski BOŚ S.A."}
]

DEMO_FINDINGS = [
    {
        "url": "https://instagram.com/p/finfluencer-kamil-01",
        "source": "instagram.com",
        "author": "@kamil_inwestuje",
        "text": "Współpraca z XTB S.A.! Otwórz konto maklerskie z kodem KAMIL2026 i zgarnij 200 zł bonusu. Buduj pasywny dochód z akcji i ETFów bez wychodzenia z domu! Zysk gwarantowany z moją strategią.",
        "risk_score": 0.88,
        "modules": [1, 2],
        "reason": "[M1 Finfluencer] Wykryto promowanie oferty firmy XTB S.A. przez @kamil_inwestuje z użyciem kodów polecających. [M2 Zgodność] Naruszenie kryteriów: R3 Informacja o ryzyku przy zyskach; R2 Brak jednoznacznego oznaczenia reklamy.",
        "audit": {
            "passed": False,
            "issues": [
                {"id": "3", "title": "Informacja o ryzyku przy obietnicy zysku", "detail": "Wykryto obietnicę zysku (zysk gwarantowany, pasywny dochód) bez bezpośredniego ostrzeżenia o ryzyku.", "legal_basis": "art. 44 ust. 2 lit. b rozporządzenia del. 2017/565"},
                {"id": "2", "title": "Oznaczenie reklamy", "detail": "Brak jednoznacznego oznaczenia materiału jako reklama/promocja.", "legal_basis": "art. 24 ust. 3 MiFID II"}
            ]
        },
        "days_ago": 3
    },
    {
        "url": "https://aura-wealth-management.pl/oferta-vip",
        "source": "aura-wealth-management.pl",
        "author": "Aura Wealth Consulting",
        "text": "Family Office i Wealth Management dla klientów VIP. Świadczymy doradztwo inwestycyjne oraz profesjonalne zarządzanie portfelem akcji GPW, obligacji korporacyjnych i kontraktów terminowych. Rekomendujemy spółki do nabycia z potencjałem wzrostu 50%.",
        "risk_score": 0.92,
        "modules": [3],
        "reason": "[M3 Shadow Advisory] Podmiot oferuje usługi doradztwa inwestycyjnego oraz zarządzania portfelem instrumentów finansowych bez wymaganej licencji firmy inwestycyjnej UKNF (art. 76 ustawy o obrocie).",
        "audit": {
            "passed": False,
            "issues": [
                {"id": "1", "title": "Identyfikacja firmy", "detail": "Podmiot nie figuruje w rejestrze licencjonowanych firm inwestycyjnych UKNF.", "legal_basis": "art. 44 ust. 2 lit. a rozporządzenia del. 2017/565"},
                {"id": "15", "title": "Prognozy przyszłych wyników", "detail": "Obietnica potencjału wzrostu 50% bez wymaganego zastrzeżenia.", "legal_basis": "art. 44 ust. 6 rozporządzenia del. 2017/565"}
            ]
        },
        "days_ago": 2
    },
    {
        "url": "https://global-trade-broker.eu/kampania-knf",
        "source": "global-trade-broker.eu",
        "author": "Global Trade Broker",
        "text": "Inwestuj w kontrakty CFD na złoto i waluty. Nasza platforma jest w pełni bezpieczna - spełniamy rygorystyczne wymogi nadzorcze KNF więc nie stracisz kapitału. Zobacz nasze wyniki historyczne: stopa zwrotu 120% za ostatnie 6 miesięcy!",
        "risk_score": 0.95,
        "modules": [2],
        "reason": "[M2 Zgodność] Naruszenie kryteriów: R18 Nadzór jako argument bezpieczeństwa; R17 Sugerowanie aprobaty KNF; R12a Wyniki historyczne nie obejmują 5 lat; R14 Brak ostrzeżenia przy wynikach historycznych.",
        "audit": {
            "passed": False,
            "issues": [
                {"id": "18", "title": "Nadzór jako argument bezpieczeństwa", "detail": "Użycie faktu nadzoru KNF jako argumentu o braku możliwości straty kapitału.", "legal_basis": "art. 44 ust. 8 rozporządzenia del. 2017/565"},
                {"id": "17", "title": "Zakaz sugerowania aprobaty organu nadzoru", "detail": "Sugerowanie aprobaty i gwarancji KNF dla produktu.", "legal_basis": "art. 44 ust. 8 rozporządzenia del. 2017/565"},
                {"id": "12a", "title": "Wyniki historyczne: okres i zakres", "detail": "Wyniki zaprezentowano za 6 miesięcy zamiast pełnych 5 lat.", "legal_basis": "art. 44 ust. 4 rozporządzenia del. 2017/565"},
                {"id": "14", "title": "Ostrzeżenie przy wynikach historycznych", "detail": "Brak zastrzeżenia, że wyniki z przeszłości nie stanowią wiarygodnego wskaźnika przyszłości.", "legal_basis": "art. 44 ust. 4 lit. d rozporządzenia del. 2017/565"}
            ]
        },
        "days_ago": 1
    },
    {
        "url": "https://bossa.pl/komunikat-edukacyjny-ryzyko",
        "source": "bossa.pl",
        "author": "Dom Maklerski BOŚ S.A.",
        "text": "Dom Maklerski BOŚ S.A. przypomina: Inwestowanie w instrumenty finansowe wiąże się z ryzykiem poniesienia strat, w tym utraty całości lub części zainwestowanego kapitału. Ostateczna decyzja inwestycyjna należy do klienta. Przed podjęciem decyzji zapoznaj się ze specyfikacją instrumentu.",
        "risk_score": 0.12,
        "modules": [],
        "reason": "Materiał zgodny z wymogami regulacyjnymi. Wykryto prawidłowe i wyraźne ostrzeżenie o ryzyku inwestycyjnym.",
        "audit": {
            "passed": True,
            "issues": []
        },
        "days_ago": 0
    }
]

def get_db():
    with SessionLocal() as db:
        yield db

def serialize(row: Finding):
    return {
        "id": row.id,
        "url": row.url,
        "source": row.source,
        "author": row.author,
        "text": row.text,
        "risk_score": row.risk_score,
        "modules": row.modules,
        "reason": row.reason,
        "audit": row.audit,
        "snapshot_path": row.snapshot_path,
        "status": row.status,
        "created_at": row.created_at.isoformat()
    }

def serialize_job(row: ScanJob):
    return {
        "id": row.id,
        "url": row.url,
        "status": row.status,
        "error": row.error,
        "finding_id": row.finding_id,
        "created_at": row.created_at.isoformat()
    }

def extract_smart_content(html: str) -> str:
    """Ekstrahuje treść z HTML uwzględniając OpenGraph, meta tagi social mediów i JSON-LD."""
    soup = BeautifulSoup(html, "html.parser")
    pieces = []

    # 1. Sprawdzenie OpenGraph i Twitter Cards (kluczowe dla Instagrama, TikToka, Facebooka)
    for prop in ["og:description", "og:title", "twitter:description", "description"]:
        meta = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        if meta and meta.get("content"):
            pieces.append(meta["content"].strip())

    # 2. Sprawdzenie JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                for k in ["articleBody", "description", "caption", "text"]:
                    if data.get(k): pieces.append(str(data[k]))
        except Exception:
            pass

    # 3. Widoczny tekst strony
    visible_body = soup.get_text(" ", strip=True)
    if visible_body:
        pieces.append(visible_body)

    combined = " ".join(dict.fromkeys(pieces))
    return combined[:30000]

def seed_demo(db: Session):
    for item in DEMO_FINDINGS:
        exists = db.scalar(select(Finding.id).where(Finding.url == item["url"]))
        if not exists:
            digest = hashlib.sha256(item["text"].encode()).hexdigest()
            created = datetime.now(timezone.utc) - timedelta(days=item.get("days_ago", 0))
            snapshot_file = SNAPSHOTS_DIR / f"{digest}.html"
            snapshot_file.write_text(f"<html><body><h1>Zrzut źródła InvestWatch</h1><p><b>Autor:</b> {item.get('author')}</p><p><b>URL:</b> {item['url']}</p><hr/><p>{item['text']}</p></body></html>", encoding="utf-8")

            finding = Finding(
                url=item["url"],
                source=item["source"],
                author=item.get("author"),
                text=item["text"],
                content_hash=digest,
                risk_score=item["risk_score"],
                modules=item["modules"],
                reason=item["reason"],
                audit=item.get("audit"),
                snapshot_path=str(snapshot_file),
                status="new",
                created_at=created
            )
            db.add(finding)
    db.commit()

async def analyze_and_store(url: str, author: str | None, raw_text: str | None, db: Session) -> Finding:
    if raw_text:
        text_content = raw_text.strip()[:30000]
        html_content = f"<html><body><p>{text_content}</p></body></html>"
    else:
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html_content = resp.text
            text_content = extract_smart_content(html_content)

    # Wysłanie do AI Engine z timeoutem do 30 sekund
    async with httpx.AsyncClient(timeout=30.0) as client:
        ai_resp = await client.post(f"{AI_URL}/analyze", json={"text": text_content, "url": url, "author": author})
        ai_resp.raise_for_status()
        result = ai_resp.json()

    digest = hashlib.sha256(text_content.encode()).hexdigest()
    snapshot_path = SNAPSHOTS_DIR / f"{digest}.html"
    snapshot_path.write_text(html_content, encoding="utf-8")

    existing = db.scalar(select(Finding).where(Finding.content_hash == digest))
    if existing:
        return existing

    netloc = urlsplit(url).netloc or "investwatch.local"
    row = Finding(
        url=url,
        source=netloc,
        author=author or result.get("entities", {}).get("author"),
        text=text_content,
        content_hash=digest,
        risk_score=result["risk_score"],
        modules=result["modules"],
        reason=result["reason"],
        audit=result.get("compliance_audit"),
        snapshot_path=str(snapshot_path)
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

async def worker():
    while True:
        job_id = await jobs.get()
        with SessionLocal() as db:
            job = db.get(ScanJob, job_id)
            if not job:
                continue
            job.status = "processing"
            db.commit()
            try:
                finding = await analyze_and_store(job.url, job.author, None, db)
                job.status, job.finding_id = "completed", finding.id
                db.commit()
                if finding.risk_score >= RISK_THRESHOLD:
                    await hub.broadcast({"type": "high_risk_finding", "finding": serialize(finding)})
            except Exception as exc:
                job.status, job.error = "failed", str(exc)[:500]
                db.commit()
            finally:
                jobs.task_done()

# Harmonogram w tle (symulacja CronJob / okresowego monitoringu)
async def periodic_scheduler():
    while True:
        await asyncio.sleep(90)  # co 90 sekund
        logger.info("Scheduler heartbeat: okresowy monitoring źródeł...")

@app.on_event("startup")
async def startup():
    Base.metadata.create_all(engine)
    existing_cols = {col["name"] for col in inspect(engine).get_columns("findings")}
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE findings DROP CONSTRAINT IF EXISTS findings_url_key;"))
        if "audit" not in existing_cols:
            conn.execute(text("ALTER TABLE findings ADD COLUMN audit JSON"))
        if "snapshot_path" not in existing_cols:
            conn.execute(text("ALTER TABLE findings ADD COLUMN snapshot_path VARCHAR(512)"))
    with SessionLocal() as db:
        seed_demo(db)
    asyncio.create_task(worker())
    asyncio.create_task(periodic_scheduler())

@app.get("/health")
async def health():
    ai_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{AI_URL}/health")
            if r.status_code == 200:
                ai_status = r.json()
    except Exception as e:
        ai_status = f"unreachable: {e}"

    return {
        "status": "ok",
        "queue_size": jobs.qsize(),
        "risk_threshold": RISK_THRESHOLD,
        "scheduler": "active",
        "object_storage": "snapshots_volume_ready",
        "ai_engine_link": ai_status
    }

@app.get("/findings")
def findings(min_risk: float = 0, source: str | None = None, module: int | None = None, db: Session = Depends(get_db)):
    records = db.scalars(select(Finding).where(Finding.risk_score >= min_risk).order_by(Finding.created_at.desc())).all()
    filtered = []
    for x in records:
        if source and source.lower() not in x.source.lower():
            continue
        if module and module not in x.modules:
            continue
        filtered.append(serialize(x))
    return filtered

@app.get("/findings/{finding_id}/snapshot")
def get_snapshot(finding_id: int, db: Session = Depends(get_db)):
    row = db.get(Finding, finding_id)
    if not row or not row.snapshot_path or not Path(row.snapshot_path).exists():
        raise HTTPException(404, "Snapshot not found")
    content = Path(row.snapshot_path).read_text(encoding="utf-8")
    return HTMLResponse(content=content)

@app.get("/analytics/summary")
def summary(threshold: float = 0.70, db: Session = Depends(get_db)):
    threshold = max(0.0, min(1.0, threshold))
    rows = db.scalars(select(Finding)).all()
    visible = [x for x in rows if x.risk_score >= threshold]
    return {
        "threshold": threshold,
        "total": len(visible),
        "high_risk": sum(x.risk_score >= 0.70 for x in visible),
        "new": sum(x.status == "new" for x in visible),
        "estimated_false_positive": sum(threshold <= x.risk_score < min(1.0, threshold + 0.15) for x in visible),
        "estimated_false_negative": sum(x.risk_score < threshold and x.risk_score >= max(0.0, threshold - 0.15) for x in rows),
        "by_source": Counter(x.source for x in visible),
        "by_module": {
            "m1": sum(1 in x.modules for x in visible),
            "m2": sum(2 in x.modules for x in visible),
            "m3": sum(3 in x.modules for x in visible)
        }
    }

@app.get("/analytics/trends")
def trends(db: Session = Depends(get_db)):
    buckets: dict[str, dict] = {}
    records = db.scalars(select(Finding).order_by(Finding.created_at.asc())).all()
    for x in records:
        day = x.created_at.date().isoformat()
        b = buckets.setdefault(day, {
            "date": day,
            "total": 0,
            "high": 0,
            "modules": {"1": 0, "2": 0, "3": 0}
        })
        b["total"] += 1
        b["high"] += int(x.risk_score >= 0.70)
        for module in x.modules:
            b["modules"][str(module)] += 1
    return list(sorted(buckets.values(), key=lambda x: x["date"]))

@app.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(ScanJob, job_id)
    if not job:
        raise HTTPException(404, "Scan job not found")
    return serialize_job(job)

@app.post("/scans", status_code=202)
async def enqueue_scan(payload: ScanRequest, db: Session = Depends(get_db)):
    job = ScanJob(url=str(payload.url), author=payload.author)
    db.add(job)
    db.commit()
    db.refresh(job)
    await jobs.put(job.id)
    return serialize_job(job)

@app.post("/scans/direct", status_code=201)
async def analyze_direct(payload: DirectAnalyzeRequest, db: Session = Depends(get_db)):
    url = payload.url if (payload.url and payload.url != "https://investwatch.local/custom-sample") else f"https://investwatch.local/sample-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    finding = await analyze_and_store(url, payload.author, payload.text, db)
    if finding.risk_score >= RISK_THRESHOLD:
        await hub.broadcast({"type": "high_risk_finding", "finding": serialize(finding)})
    return serialize(finding)

@app.patch("/findings/{finding_id}/status")
def update_status(finding_id: int, payload: StatusPatch, db: Session = Depends(get_db)):
    if payload.status not in {"new", "reviewing", "confirmed", "dismissed"}:
        raise HTTPException(422, "Invalid status")
    row = db.get(Finding, finding_id)
    if not row:
        raise HTTPException(404, "Finding not found")
    row.status = payload.status
    db.commit()
    db.refresh(row)
    return serialize(row)

@app.websocket("/ws/alerts")
async def alerts(ws: WebSocket):
    await ws.accept()
    hub.clients.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in hub.clients:
            hub.clients.remove(ws)
