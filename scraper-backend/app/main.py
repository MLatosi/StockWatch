"""InvestWatch Ingestion API: persistent findings, asynchronous scan queue, smart social media scraper, scheduler and live alerts."""
import asyncio
import hashlib
import json
import logging
import os
import random
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, HttpUrl
from sqlalchemy import DateTime, Float, Integer, JSON, String, Text, create_engine, func, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from app.watchlist import WATCHLIST as SEARCH_TERMS
from app.public_sources import PUBLIC_RSS_FEEDS, PUBLIC_SITEMAPS, parse_feed, parse_sitemap

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
active_scan = {"job_id": None, "url": None, "author": None, "stage": "idle", "started_at": None}
discovery_status = {"stage": "waiting", "last_started_at": None, "last_finished_at": None, "last_found": 0, "last_error": None, "source_results": {}, "source_errors": [], "next_run_at": time.time() + 20}
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
        if active_scan["job_id"] is not None:
            active_scan["stage"] = "fetching_page"
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html_content = resp.text
            text_content = extract_smart_content(html_content)

    # Wysłanie do AI Engine z timeoutem do 30 sekund
    if active_scan["job_id"] is not None:
        active_scan["stage"] = "analyzing_content"
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
                jobs.task_done()
                continue
            job.status = "processing"
            db.commit()
            active_scan.update({"job_id": job.id, "url": job.url, "author": job.author, "stage": "fetching_page", "started_at": datetime.now(timezone.utc).isoformat()})
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
                active_scan.update({"job_id": None, "url": None, "author": None, "stage": "idle", "started_at": None})
                jobs.task_done()

AUTONOMOUS_FEED = [
    {
        "url": "https://instagram.com/p/C_trader_bartek_vip",
        "source": "instagram.com",
        "author": "@trader_bartek",
        "text": "Zarabiaj na ropie i złocie z brokerem XTB S.A.! Otwórz konto z kodem BARTEK_VIP i zgarnij darmowe akcje. Moja strategia ma 95% skuteczności, zysk gwarantowany bez względu na sytuację rynkową. Zero ryzyka, start od 100 zł! #inwestowanie #pieniadze #zarabianie"
    },
    {
        "url": "https://tiktok.com/@krypto_krolowa/video/7391829104",
        "source": "tiktok.com",
        "author": "@krypto_krolowa",
        "text": "Jak zarobiłam 45 000 zł w 2 tygodnie? Dom Maklerski Noble Securities oferuje mega warunki. Wbijajcie w link w bio, odbierzcie bonus powitalny i kopiujcie moje pozycje tradingowe. Bez ryzyka straty! #wspolpraca"
    },
    {
        "url": "https://t.me/silesia_wealth_vip_signals",
        "source": "t.me",
        "author": "Silesia Wealth Club",
        "text": "Świadczymy licencjonowane doradztwo inwestycyjne i zarządzanie portfelem akcji spółek technologicznych z GPW oraz NewConnect. Rekomendujemy zakup wybranych walorów z potencjałem wzrostu 120% w 3 miesiące. Dołącz do grona zyskownych inwestorów."
    },
    {
        "url": "https://crypto-forex-algotrade.pl/rejestracja-vip",
        "source": "crypto-forex-algotrade.pl",
        "author": "AlgoTrade Systems",
        "text": "Rewolucyjny algorytm tradingowy pod stałym nadzorem KNF. Zapewniamy 100% ochrony kapitału i zerowe ryzyko utraty środków. Wyniki historyczne z ostatnich 6 miesięcy: stopa zwrotu +240%! Zarejestruj się już teraz."
    },
    {
        "url": "https://capital-partners-familyoffice.pl/oferta",
        "source": "capital-partners-familyoffice.pl",
        "author": "Capital Partners Family Office",
        "text": "Kompleksowe zarządzanie majątkiem, zarządzanie portfelem instrumentów finansowych oraz indywidualne rekomendacje inwestycyjne dla przedsiębiorców. Powierz kapitał naszym doradcom majątkowym."
    }
]

async def discover_public_pages(db: Session, limit: int = 10):
    """Discover candidates from Google News plus public investment RSS and sitemaps."""
    headers = {"User-Agent": "InvestWatch/0.6 (public feed reader; contact: local prototype)"}
    found: list[dict] = []
    seen: set[str] = set()
    errors: list[dict[str, str]] = []
    sources: dict[str, dict[str, int]] = {}
    finance_context = (
        "giełd", "akcj", "obligac", "maklersk", "broker", "trading", "inwestor", "kapitał",
        "etf", "forex", "cfd", "kryptowalut", "fundusz", "doradztw inwestycyjn",
        "portfel inwestycyjn", "instrument finansow", "zysk", "stopa zwrotu", "gpw", "wig",
        "dywidend", "emisj", "rekomendac", "knf", "inwestyc",
    )

    async def enqueue(url: str, title: str, source_name: str) -> bool:
        url = url.strip()
        if len(found) >= limit or not url.startswith("https://") or url in seen:
            return False
        seen.add(url)
        source_author = f"{source_name}: {title}"[:250]
        if db.scalar(select(Finding.id).where(Finding.url == url)):
            return False
        existing_job = db.scalar(select(ScanJob.id).where(
            ScanJob.url == url,
            ScanJob.status.in_(["queued", "processing", "completed", "failed"]),
        ))
        if existing_job:
            return False
        if source_name == "Google News RSS":
            same_title_job = db.scalar(select(ScanJob.id).where(ScanJob.author == source_author))
            same_title_finding = db.scalar(select(Finding.id).where(Finding.author == source_author))
            if same_title_job or same_title_finding:
                return False
        job = ScanJob(url=url, author=source_author)
        db.add(job)
        db.flush()
        await jobs.put(job.id)
        found.append({"url": url, "title": title, "source": source_name, "job_id": job.id})
        sources.setdefault(source_name, {"items": 0, "relevant": 0, "queued": 0})["queued"] += 1
        return True

    groups = [SEARCH_TERMS[i:i + 4] for i in range(0, len(SEARCH_TERMS), 4)]
    google_name = "Google News RSS"
    sources[google_name] = {"items": 0, "relevant": 0, "queued": 0}
    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=headers) as client:
        # Zostawiamy limit dla wyszukiwarki, żeby newsy nie wypchnęły blogów i źródeł bezpośrednich.
        google_limit = min(5, limit)
        async def load_google_group(group):
            query = " OR ".join(item["term"] for item in group)
            try:
                response = await client.get("https://news.google.com/rss/search", params={"q": query, "hl": "pl", "gl": "PL", "ceid": "PL:pl"})
                response.raise_for_status()
                return parse_feed(response.content, str(response.url)), None
            except (httpx.HTTPError, ET.ParseError) as exc:
                return [], str(exc)[:220]

        google_results = await asyncio.gather(*(load_google_group(group) for group in groups))
        for entries, error in google_results:
            if error:
                errors.append({"source": google_name, "error": error})
                continue
            sources[google_name]["items"] += len(entries)
            for entry in entries:
                searchable = (entry["title"] + " " + entry["description"]).lower()
                if not any(signal in searchable for signal in finance_context):
                    continue
                sources[google_name]["relevant"] += 1
                if len(found) >= google_limit:
                    break
                await enqueue(entry["url"], entry["title"], google_name)

        # Bezpośrednie kanały wydawców/blogów. Są tematycznie dobrane, więc nie
        # odrzucamy tekstu tylko dlatego, że RSS zawiera krótki opis zamiast artykułu.
        async def load_public_feed(feed):
            try:
                response = await client.get(feed["url"])
                response.raise_for_status()
                return parse_feed(response.content, str(response.url)), None
            except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
                return [], str(exc)[:220]

        public_feed_results = await asyncio.gather(*(load_public_feed(feed) for feed in PUBLIC_RSS_FEEDS))
        for feed, (entries, error) in zip(PUBLIC_RSS_FEEDS, public_feed_results):
            source_name = feed["name"]
            counter = sources.setdefault(source_name, {"items": 0, "relevant": 0, "queued": 0})
            if error:
                errors.append({"source": source_name, "error": error})
                logger.info("RSS source %s unavailable: %s", source_name, error)
                continue
            counter["items"] = len(entries)
            # Kilka najnowszych pozycji na źródło wystarczy; stare wpisy i tak
            # zostają pominięte przez deduplikację URL-i.
            queued_from_feed = 0
            for entry in entries[:5]:
                if len(found) >= limit:
                    break
                searchable = (entry["title"] + " " + entry["description"]).lower()
                if not any(signal in searchable for signal in finance_context):
                    continue
                counter["relevant"] += 1
                if await enqueue(entry["url"], entry["title"], source_name):
                    queued_from_feed += 1
                    if queued_from_feed >= 1:
                        break

        # Sitemap uzupełnia RSS o publiczne adresy. Czytamy tylko ograniczoną
        # liczbę map i adresów, żeby nie zalewać kolejki starszymi artykułami.
        async def load_sitemap(sitemap):
            try:
                response = await client.get(sitemap["url"])
                response.raise_for_status()
                pages, nested = parse_sitemap(response.content, str(response.url))
                for nested_url in nested[:2]:
                    nested_response = await client.get(nested_url)
                    nested_response.raise_for_status()
                    nested_pages, _ = parse_sitemap(nested_response.content, str(nested_response.url))
                    pages.extend(nested_pages)
                return pages, None
            except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
                return [], str(exc)[:220]

        sitemap_results = await asyncio.gather(*(load_sitemap(sitemap) for sitemap in PUBLIC_SITEMAPS))
        for sitemap, (pages, error) in zip(PUBLIC_SITEMAPS, sitemap_results):
            source_name = sitemap["name"]
            counter = sources.setdefault(source_name, {"items": 0, "relevant": 0, "queued": 0})
            if error:
                errors.append({"source": source_name, "error": error})
                logger.info("Sitemap source %s unavailable: %s", source_name, error)
                continue
            counter["items"] = len(pages)
            for page_url in pages[-5:]:
                if len(found) >= limit:
                    break
                counter["relevant"] += 1
                if await enqueue(page_url, "Publiczny adres znaleziony w sitemap", source_name):
                    break

    db.commit()
    return {
        "items": found,
        "feed_items": sum(s["items"] for name, s in sources.items() if name == google_name),
        "relevant_items": sources[google_name]["relevant"],
        "query_count": len(groups),
        "sources": sources,
        "errors": errors,
    }

async def periodic_scheduler():
    await asyncio.sleep(20)
    while True:
        discovery_status.update({"stage": "searching", "last_started_at": datetime.now(timezone.utc).isoformat(), "last_error": None})
        try:
            with SessionLocal() as db:
                result = await discover_public_pages(db)
                discovery_status["last_found"] = len(result["items"])
                discovery_status["feed_items"] = result["feed_items"]
                discovery_status["relevant_items"] = result["relevant_items"]
                discovery_status["source_results"] = result["sources"]
                discovery_status["source_errors"] = result["errors"]
                if result["feed_items"]:
                    logger.info("Google News returned %s entries; all public sources queued %s new pages", result["feed_items"], len(result["items"]))
        except Exception as exc:
            discovery_status["last_error"] = str(exc)[:300]
            logger.warning("Public RSS discovery failed: %s", exc)
        interval = int(os.getenv("DISCOVERY_INTERVAL_SECONDS", "60"))
        discovery_status.update({"stage": "waiting", "last_finished_at": datetime.now(timezone.utc).isoformat(), "next_run_at": time.time() + interval})
        await asyncio.sleep(interval)

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
        pending_jobs = db.scalars(select(ScanJob.id).where(ScanJob.status == "queued").order_by(ScanJob.created_at)).all()
        for job_id in pending_jobs:
            await jobs.put(job_id)
        if pending_jobs:
            logger.info("Recovered %s pending scan jobs from database", len(pending_jobs))
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
        "discovery_interval_seconds": int(os.getenv("DISCOVERY_INTERVAL_SECONDS", "60")),
        "object_storage": "snapshots_volume_ready",
        "ai_engine_link": ai_status
    }

@app.get("/watchlist")
def watchlist():
    return {
        "terms": SEARCH_TERMS,
        "count": len(SEARCH_TERMS),
        "sources": ["Google News RSS", *[feed["name"] for feed in PUBLIC_RSS_FEEDS], *[item["name"] for item in PUBLIC_SITEMAPS]],
    }

@app.get("/crawler/status")
def crawler_status(db: Session = Depends(get_db)):
    recent_failures = db.scalars(
        select(ScanJob).where(ScanJob.status == "failed").order_by(ScanJob.created_at.desc()).limit(5)
    ).all()
    return {
        "analyzed_pages": db.scalar(select(func.count(Finding.id))) or 0,
        "completed_scans": db.scalar(select(func.count(ScanJob.id)).where(ScanJob.status == "completed")) or 0,
        "failed_scans": db.scalar(select(func.count(ScanJob.id)).where(ScanJob.status == "failed")) or 0,
        "recent_failures": [
            {"id": job.id, "url": job.url, "error": job.error, "created_at": job.created_at.isoformat()}
            for job in recent_failures
        ],
        "queued_scans": db.scalar(select(func.count(ScanJob.id)).where(ScanJob.status == "queued")) or 0,
        "is_working": active_scan["job_id"] is not None,
        "current": active_scan.copy(),
        "discovery": discovery_status.copy(),
        "watchlist_count": len(SEARCH_TERMS),
        "discovery_interval_seconds": int(os.getenv("DISCOVERY_INTERVAL_SECONDS", "60")),
    }

@app.post("/discover")
async def discover_now(db: Session = Depends(get_db)):
    discovery_status.update({"stage": "searching", "last_started_at": datetime.now(timezone.utc).isoformat(), "last_error": None})
    try:
        result = await discover_public_pages(db)
        discovery_status.update({
            "last_found": len(result["items"]), "feed_items": result["feed_items"],
            "relevant_items": result["relevant_items"], "source_results": result["sources"],
            "source_errors": result["errors"], "last_finished_at": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "source": "Google News, public RSS and sitemaps", "queued": len(result["items"]),
            "feed_items": result["feed_items"], "relevant_items": result["relevant_items"],
            "query_count": result["query_count"], "sources": result["sources"],
            "errors": result["errors"], "items": result["items"],
        }
    except httpx.HTTPError as exc:
        discovery_status["last_error"] = str(exc)[:300]
        raise HTTPException(502, f"Public search source unavailable: {exc}")
    finally:
        discovery_status["stage"] = "waiting"

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
    if not row:
        raise HTTPException(404, "Finding not found")
    
    # Jeśli plik istnieje na dysku, zwróć go
    if row.snapshot_path and Path(row.snapshot_path).exists():
        content = Path(row.snapshot_path).read_text(encoding="utf-8")
        return HTMLResponse(content=content)
    
    # Fallback / samonaprawienie: wygeneruj snapshot z zarchiwizowanego rekordu w bazie
    digest = row.content_hash or hashlib.sha256((row.text or "").encode()).hexdigest()
    snapshot_file = SNAPSHOTS_DIR / f"{digest}.html"
    
    html_content = f"""<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <title>Zrzut archiwalny #{row.id} — #InvestWatch</title>
  <style>
    body {{ font-family: system-ui, -apple-system, sans-serif; background: #0b1523; color: #e2e8f0; margin: 0; padding: 24px; }}
    .header {{ background: #132238; border: 1px solid #1e3550; border-radius: 8px; padding: 16px 20px; margin-bottom: 20px; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 999px; font-weight: bold; font-size: 13px; background: rgba(255,82,99,0.2); color: #ff5263; border: 1px solid rgba(255,82,99,0.4); }}
    .content {{ background: #101c2e; border: 1px solid #1e3550; border-radius: 8px; padding: 20px; white-space: pre-wrap; font-size: 15px; line-height: 1.6; }}
    .meta {{ color: #8fa5be; font-size: 13px; margin-top: 6px; }}
  </style>
</head>
<body>
  <div class="header">
    <div style="display:flex; justify-content:space-between; align-items:center;">
      <h2 style="margin:0; color:#38bdf8;">#InvestWatch — Zrzut Archiwalny Incydentu #{row.id}</h2>
      <span class="badge">Risk Score: {row.risk_score:.2f}</span>
    </div>
    <div class="meta"><b>Źródło:</b> <a href="{row.url}" target="_blank" style="color:#38bdf8;">{row.url}</a> | <b>Autor:</b> {row.author or 'Nieznany'} | <b>Data rejestracji:</b> {row.created_at.isoformat()}</div>
  </div>
  <h3>Zarejestrowana treść materiału / posta:</h3>
  <div class="content">{row.text}</div>
</body>
</html>"""
    try:
        snapshot_file.write_text(html_content, encoding="utf-8")
        row.snapshot_path = str(snapshot_file)
        db.commit()
    except Exception as e:
        logger.warning(f"Could not persist fallback snapshot: {e}")
    
    return HTMLResponse(content=html_content)

@app.get("/analytics/summary")
def summary(threshold: float = 0.70, db: Session = Depends(get_db)):
    threshold = max(0.0, min(1.0, threshold))
    rows = db.scalars(select(Finding)).all()
    visible = [x for x in rows if x.risk_score >= threshold]
    reviewed = [x for x in rows if x.status in {"confirmed", "dismissed"}]
    true_positive = sum(x.status == "confirmed" and x.risk_score >= threshold for x in reviewed)
    false_positive = sum(x.status == "dismissed" and x.risk_score >= threshold for x in reviewed)
    false_negative = sum(x.status == "confirmed" and x.risk_score < threshold for x in reviewed)
    true_negative = sum(x.status == "dismissed" and x.risk_score < threshold for x in reviewed)
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    return {
        "threshold": threshold,
        "total": len(visible),
        "high_risk": sum(x.risk_score >= 0.70 for x in visible),
        "new": sum(x.status == "new" for x in visible),
        "reviewed_metrics": {
            "reviewed_count": len(reviewed),
            "false_positive": false_positive,
            "false_negative": false_negative,
            "true_positive": true_positive,
            "true_negative": true_negative,
            "precision": round(100 * true_positive / precision_denominator, 1) if precision_denominator else None,
            "recall": round(100 * true_positive / recall_denominator, 1) if recall_denominator else None,
        },
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
