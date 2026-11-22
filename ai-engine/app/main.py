"""InvestWatch AI Engine: wielomodułowa analiza ryzyka i audyt regulacyjny UKNF.

Obsługuje 3 moduły analityczne HackNation 2026:
- Moduł 1: Finfluencerzy i podmioty trzecie (promocja podmiotów licencjonowanych przez osoby trzecie)
- Moduł 2: Weryfikacja zgodności i informacji o ryzyku (18 reguł MiFID II / rozporządzenie 2017/565)
- Moduł 3: Shadow Advisory (nieautoryzowane doradztwo inwestycyjne / zarządzanie portfelem bez licencji KNF)
- Silnik inferencji: Ollama (gemma2:2b) z natychmiastowym hybrydowym audytem reguł deterministycznych.
"""
import hashlib
import math
import os
import re
from fastapi import FastAPI
from pydantic import BaseModel, HttpUrl

from .knf_registry import find_knf_entities
from .risk_rules import RISK_CRITERIA_META, evaluate_all_rules, contains_any
from .ollama_client import check_ollama_health, query_ollama

app = FastAPI(title="InvestWatch AI Engine", version="0.4.0")

class AnalysisRequest(BaseModel):
    text: str
    url: HttpUrl | str
    author: str | None = None

COMPANY_FALLBACK_RE = re.compile(
    r"\b(?:[A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźż-]+\s){0,2}(?:Bank|Capital|Invest|Investments|Broker|Finance|Trading|Securities|Partners|Asset Management|Family Office|Wealth)\b"
)

ADVISORY_TERMS = [
    "doradztwo inwestycyjne", "zarządzanie portfelem", "rekomendacje giełdowe",
    "rekomendacja inwestycyjna", "indywidualna rekomendacja", "family office",
    "wealth management", "zarządzanie majątkiem", "sygnały giełdowe", "portfel inwestycyjny",
    "doradca majątkowy", "dobór spółek do portfela", "zarządzanie aktywami"
]

INSTRUMENT_TERMS = [
    "akcje", "obligacje", "fundusze", "etf", "kontrakty cfd", "cfd", "opcje",
    "kontrakty terminowe", "forex", "papiery wartościowe", "instrumenty finansowe",
    "kryptowaluty", "krypto-kontrakty", "certyfikaty inwestycyjne"
]

ACTION_TERMS = [
    "kupuj", "sprzedaj", "nabyć", "zbyć", "otwórz pozycję", "zamknij pozycję",
    "zainwestuj z nami", "powierz kapitał", "zarządzamy twoim kapitałem", "rekomendujemy zakup"
]

PROMO_TERMS = [
    "kod promocyjny", "kod rabatowy", "reflid", "afiliacja", "link w bio", "współpraca",
    "partner", "polecam brokera", "załóż konto z kodem", "bonus za rejestrację",
    "#ad", "#reklama", "#wspolpraca", "#sponsorowane"
]

def generate_risk_embedding(text_lower: str, compliance_issues: list[dict], modules: list[int]) -> list[float]:
    """Generuje 16-wymiarową reprezentację wektorową (embedding cech ryzyka).

    Wymóg specyfikacji UKNF: 'Reprezentacja wektorowa w postaci tokenów i embeddingów'.
    """
    vector = [0.0] * 16
    vector[0] = float(len(compliance_issues)) / 18.0
    vector[1] = 1.0 if 1 in modules else 0.0
    vector[2] = 1.0 if 2 in modules else 0.0
    vector[3] = 1.0 if 3 in modules else 0.0
    vector[4] = 1.0 if "gwarantowany zysk" in text_lower or "bez ryzyka" in text_lower else 0.0
    vector[5] = 1.0 if "knf" in text_lower else 0.0
    vector[6] = 1.0 if "kod" in text_lower or "#ad" in text_lower else 0.0
    vector[7] = 1.0 if "cfd" in text_lower or "forex" in text_lower else 0.0
    vector[8] = 1.0 if "akcje" in text_lower or "obligacje" in text_lower else 0.0
    vector[9] = 1.0 if "doradztwo" in text_lower or "zarządzanie" in text_lower else 0.0
    vector[10] = 1.0 if "wyniki historyczne" in text_lower else 0.0
    vector[11] = 1.0 if "ryzyko" in text_lower or "strata" in text_lower else 0.0
    # Wymiary 12-15: unormowane statystyki długości i różnorodności
    tokens = re.findall(r"\w+", text_lower)
    token_count = len(tokens)
    vector[12] = min(1.0, token_count / 200.0)
    vector[13] = len(set(tokens)) / max(1, token_count)
    vector[14] = min(1.0, sum(c.isupper() for c in text_lower) / max(1, len(text_lower)))
    vector[15] = round(math.sin(token_count), 4)
    return [round(v, 4) for v in vector]

@app.get("/health")
async def health():
    ollama_info = await check_ollama_health()
    return {
        "status": "ok",
        "service": "ai-engine",
        "modules_supported": [1, 2, 3],
        "rules_version": "18-criteria-knf-mifid2",
        "ollama_integration": ollama_info
    }

@app.post("/analyze")
async def analyze(payload: AnalysisRequest):
    text = payload.text.strip()
    low = text.lower()

    # 1. Identyfikacja podmiotów i powiązań z rejestrem KNF
    knf_firms = find_knf_entities(text)
    fallback_companies = list(dict.fromkeys(COMPANY_FALLBACK_RE.findall(text)))

    # 2. Ekstrakcja sygnałów domenowych
    detected_advisory = contains_any(low, *ADVISORY_TERMS)
    detected_instruments = contains_any(low, *INSTRUMENT_TERMS)
    detected_actions = contains_any(low, *ACTION_TERMS)
    detected_promo = contains_any(low, *PROMO_TERMS)

    # 3. Wykonanie audytu 18 reguł dla Modułu 2
    compliance_issues = evaluate_all_rules(text, knf_firms or fallback_companies, payload.author)

    modules = []
    reason_parts = []

    # --- MODUŁ 1: Monitoring ekosystemu zewnętrznego (Finfluencerzy / osoby trzecie) ---
    is_third_party_promo = bool(
        detected_promo or
        (payload.author and payload.author.startswith("@")) or
        ("kod" in low and (knf_firms or fallback_companies))
    )
    if is_third_party_promo and (knf_firms or fallback_companies):
        modules.append(1)
        target_name = knf_firms[0]["name"] if knf_firms else fallback_companies[0]
        promoter = payload.author or "podmiot trzeci"
        reason_parts.append(f"[M1 Finfluencer] Wykryto promowanie oferty firmy {target_name} przez {promoter} z użyciem mechanizmów polecających/afiliacyjnych.")

    # --- MODUŁ 2: Weryfikacja zgodności i informacji o ryzyku (18 reguł) ---
    if compliance_issues:
        modules.append(2)
        top_issues_str = "; ".join(f"R{i['id']}: {i['title']}" for i in compliance_issues[:3])
        if len(compliance_issues) > 3:
            top_issues_str += f" i {len(compliance_issues) - 3} innych"
        reason_parts.append(f"[M2 Zgodność] Naruszenie kryteriów informowania o ryzyku ({top_issues_str}).")

    # --- MODUŁ 3: Shadow Advisory (nieautoryzowane doradztwo inwestycyjne) ---
    is_shadow_advisory = bool(
        detected_advisory and
        (detected_instruments or detected_actions) and
        not knf_firms
    )
    if is_shadow_advisory:
        modules.append(3)
        reason_parts.append("[M3 Shadow Advisory] Podmiot oferuje usługi doradztwa inwestycyjnego lub zarządzania portfelem bez wymaganej licencji firmy inwestycyjnej UKNF (art. 76 ustawy o obrocie).")

    # 4. Model lokalny sprawdza kontekst kandydatur wskazanych przez reguły.
    # Jego opinia jest widoczna dla analityka, ale sama nie zmienia wyniku ryzyka.
    ollama_result = await query_ollama(text, compliance_issues)

    # 5. Obliczenie wskaźnika ryzyka (risk_score: 0.00 - 1.00)
    score = 0.05
    if 1 in modules:
        score += 0.28
    if 2 in modules:
        score += 0.22 + min(0.35, len(compliance_issues) * 0.06)
    if 3 in modules:
        score += 0.48

    # Ostateczne skalowanie w zależności od krytycznych naruszeń
    critical_triggers = contains_any(low, "gwarantowany zysk", "bez ryzyka", "zatwierdzony przez knf", "100% zysku", "aprobata knf")
    if critical_triggers:
        score = max(score, 0.88)

    # Obniżenie ryzyka jeśli treść ma poprawne, widoczne ostrzeżenia i zero naruszeń
    if not compliance_issues and 3 not in modules and not critical_triggers:
        score = min(score, 0.18)

    score = min(1.0, max(0.05, round(score, 2)))

    # Wektoryzacja tekstu i embeddingi
    tokens = re.findall(r"\w+", low)
    token_count = len(tokens)
    unique_tokens = len(set(tokens))
    lexical_diversity = round(unique_tokens / max(1, token_count), 3)
    risk_embedding = generate_risk_embedding(low, compliance_issues, modules)

    final_reason = " ".join(reason_parts) if reason_parts else "Materiał zgodny z wymogami regulacyjnymi. Brak wykrytych naruszeń."

    return {
        "risk_score": score,
        "modules": sorted(set(modules)),
        "reason": final_reason,
        "entities": {
            "knf_supervised_detected": [f["name"] for f in knf_firms],
            "unsupervised_candidates": [c for c in fallback_companies if c not in [f["name"] for f in knf_firms]],
            "author": payload.author
        },
        "signals": {
            "advisory_terms": detected_advisory,
            "instruments": detected_instruments,
            "actions": detected_actions,
            "promo_signals": detected_promo
        },
        "compliance_audit": {
            "issues": compliance_issues,
            "passed": len(compliance_issues) == 0,
            "total_rules_evaluated": len(RISK_CRITERIA_META),
            "analysis_scope": "tekst",
            "limitations": [
                "W tej wersji ocena dotyczy tekstu. Rozmiar i kontrast ostrzeżenia, jego położenie oraz widoczność na ekranie nie są mierzone przez przeglądarkę."
            ],
            "model_review": ollama_result,
            "score_method": "reguły i sygnały deterministyczne; model nie zmienia wyniku",
        },
        "ollama_evaluation": ollama_result,
        "vector_meta": {
            "token_count": token_count,
            "unique_tokens": unique_tokens,
            "lexical_diversity": lexical_diversity,
            "risk_embedding": risk_embedding,
            "fingerprint": hashlib.sha256(text.encode()).hexdigest()[:16]
        }
    }
