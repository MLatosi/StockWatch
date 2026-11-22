"""Integracja z lokalnym silnikiem LLM (Ollama).

Komunikuje się z instancją Ollama (np. modelem gemma2:2b lub llama3) w celu
semantycznej analizy ryzyka, detekcji ukrytych intencji promocyjnych i podsumowania naruszeń.
"""
import json
import logging
import os
import re
import httpx

logger = logging.getLogger("investwatch.ollama")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:2b")

# A model can suggest that a rule is contradicted only when its exact quote
# contains a concrete counterexample to that rule. Ambiguous context stays uncertain.
CONTRADICTION_CUES = {
    "2": ["#reklama", "#ad", "materiał reklamowy", "informacja handlowa", "ogłoszenie płatne", "materiał promocyjny", "#sponsorowane", "płatna współpraca", "współpraca płatna"],
    "3": ["inwestowanie wiąże się z ryzykiem", "ryzyko poniesienia strat", "możesz stracić", "utraty kapitału", "utraty części lub całości", "ryzyko utraty", "inwestycja może przynieść stratę"],
    "12a": ["ostatnie 5 lat", "pełne 5 lat", "okres 5 lat", "12 miesięcy", "okres referencyjny"],
    "12b": ["kurs walut", "kursu walutowego", "prowizje", "opłaty", "uwzględnia opłaty", "wpływ kosztów"],
    "14": ["nie stanowią wiarygodnego wskaźnika przyszłych wyników", "nie są gwarancją przyszłych zysków", "nie gwarantują powtórzenia w przyszłości"],
    "15": ["prognoza nie jest wiarygodnym wskaźnikiem", "prognozy obarczone są ryzykiem"],
    "16": ["zależy od indywidualnej sytuacji", "indywidualnej sytuacji podatnika", "może ulec zmianie"],
}

async def check_ollama_health() -> dict:
    """Sprawdza dostępność i listę modeli w instancji Ollama."""
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code == 200:
                models = [m.get("name") for m in resp.json().get("models", [])]
                return {
                    "available": True,
                    "url": OLLAMA_URL,
                    "target_model": OLLAMA_MODEL,
                    "installed_models": models,
                    "model_ready": any(OLLAMA_MODEL in m for m in models)
                }
    except Exception as e:
        return {
            "available": False,
            "url": OLLAMA_URL,
            "target_model": OLLAMA_MODEL,
            "error": str(e)
        }
    return {"available": False, "url": OLLAMA_URL}

async def query_ollama(text: str, rule_candidates: list[dict] | None = None) -> dict | None:
    """Prosi lokalny model o kontekstowy przegląd reguł już wskazanych przez silnik."""
    if not OLLAMA_URL:
        return None

    system_instruction = (
        "Pomagasz analitykowi sprawdzić kontekst materiału finansowego. Nie wydajesz werdyktu prawnego "
        "i nie dodajesz nowych naruszeń. Oceniasz wyłącznie przekazane kandydatury reguł. "
        "Każdy cytat musi być dosłownym fragmentem materiału. Zwróć wyłącznie poprawny JSON po polsku."
    )

    candidates = [
        {
            "id": str(item.get("id", "")),
            "title": item.get("title", ""),
            "detector_note": item.get("detail", ""),
            "source_quote": (item.get("evidence") or {}).get("quote", ""),
        }
        for item in (rule_candidates or [])
    ]
    prompt = f"""Sprawdź, czy kontekst poniższego materiału wspiera każdą z przekazanych kandydatur.
Nie dopisuj reguł, których nie ma na liście. Jeśli materiał zawiera zaprzeczenie, ironię lub
wyjaśnienie zmieniające sens, wskaż to w werdykcie. `supports` znaczy, że pełny kontekst i cytat
potwierdzają przesłankę. `contradicts` znaczy, że tekst wyraźnie jej zaprzecza albo zawiera
brakujące ostrzeżenie. Sama zgodność cytatu z tekstem nie jest sprzecznością.
Przykład: „gwarantowany zysk, bez ryzyka” wspiera sygnał obietnicy bez ryzyka; „nie gwarantujemy
zysku, inwestycja może przynieść stratę” mu przeczy. Gdy nie da się rozstrzygnąć, wybierz uncertain.
W additional_signals możesz wskazać najwyżej 4 inne dosłowne fragmenty warte uwagi analityka;
opisuj wyłącznie to, co wprost wynika z cytatu, bez twierdzeń o braku informacji w całym materiale
i bez nazywania tego naruszeniem prawa. Jeśli nie ma takich fragmentów, użyj [].

Zwróć JSON o strukturze:
{{
  "summary": "krótkie, neutralne podsumowanie po polsku",
  "rule_reviews": [{{"id":"identyfikator z listy", "verdict":"supports|contradicts|uncertain", "quote":"dosłowny cytat z materiału"}}],
  "additional_signals": [{{"label":"neutralny opis sygnału do sprawdzenia", "quote":"dosłowny cytat z materiału"}}]
}}

Kandydatury reguł:
{json.dumps(candidates, ensure_ascii=False)}

Materiał (cytaty muszą pochodzić dokładnie z tego tekstu):
{text[:3000]}
"""

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "system": system_instruction,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "num_predict": 350,
                        "temperature": 0.1
                    }
                }
            )
            if resp.status_code == 200:
                raw_json = resp.json().get("response", "{}")
                data = json.loads(raw_json)
                candidate_by_id = {item["id"]: item for item in candidates}
                reviews = []
                reviewed_ids = set()
                for item in data.get("rule_reviews", []):
                    rule_id = str(item.get("id", ""))
                    verdict = item.get("verdict")
                    quote = str(item.get("quote", "")).strip()
                    if rule_id not in candidate_by_id or rule_id in reviewed_ids or verdict not in {"supports", "contradicts", "uncertain"}:
                        continue
                    reviewed_ids.add(rule_id)
                    quote_verified = bool(quote and quote in text)
                    has_counterexample = any(cue in quote.lower() for cue in CONTRADICTION_CUES.get(rule_id, []))
                    if verdict == "contradicts" and not has_counterexample:
                        verdict = "uncertain"
                    reviews.append({
                        "id": rule_id,
                        "verdict": verdict if quote_verified else "uncertain",
                        "quote": quote if quote_verified else "",
                        "quote_verified": quote_verified,
                    })
                additional_signals = []
                for item in data.get("additional_signals", []):
                    quote = str(item.get("quote", "")).strip()
                    label = str(item.get("label", "")).strip()
                    if quote and quote in text and label and not re.search(r"\b(brak|nie ma|nie zawiera|bez informacji)\b", label.lower()):
                        additional_signals.append({"label": label[:180], "quote": quote[:320], "quote_verified": True})
                    if len(additional_signals) >= 4:
                        break
                return {
                    "available": True,
                    "model": OLLAMA_MODEL,
                    "summary": str(data.get("summary", ""))[:500],
                    "rule_reviews": reviews,
                    "additional_signals": additional_signals,
                    "candidate_count": len(candidates),
                    "score_changed": False,
                }
    except Exception as exc:
        logger.warning(f"Ollama inference error or timeout: {exc}")
        return {
            "available": False,
            "model": OLLAMA_MODEL,
            "error": str(exc)
        }

    return None
