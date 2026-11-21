"""Integracja z lokalnym silnikiem LLM (Ollama).

Komunikuje się z instancją Ollama (np. modelem gemma2:2b lub llama3) w celu
semantycznej analizy ryzyka, detekcji ukrytych intencji promocyjnych i podsumowania naruszeń.
"""
import json
import logging
import os
import httpx

logger = logging.getLogger("investwatch.ollama")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:2b")

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

async def query_ollama(text: str) -> dict | None:
    """Odpytuje model LLM o ocenę materiału pod kątem naruszeń UKNF/MiFID II."""
    if not OLLAMA_URL:
        return None

    system_instruction = (
        "Jesteś audytorem nadzoru finansowego UKNF. Twoim zadaniem jest ocena materiału "
        "pod kątem nielegalnego doradztwa inwestycyjnego, agresywnych obietnic zysku i braku ostrzeżeń o ryzyku. "
        "Zwracaj wyłącznie poprawny obiekt JSON po polsku."
    )

    prompt = f"""Przeanalizuj poniższy materiał i zwróć obiekt JSON o strukturze:
{{
  "risk_level": "high" lub "medium" lub "low",
  "violations": ["lista wykrytych naruszeń"],
  "summary": "zwięzłe uzasadnienie do 35 słów"
}}

Materiał:
{text[:1800]}
"""

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "system": system_instruction,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "num_predict": 250,
                        "temperature": 0.1
                    }
                }
            )
            if resp.status_code == 200:
                raw_json = resp.json().get("response", "{}")
                data = json.loads(raw_json)
                return {
                    "available": True,
                    "model": OLLAMA_MODEL,
                    "risk_level": data.get("risk_level", "medium"),
                    "violations": data.get("violations", []),
                    "summary": data.get("summary", "")
                }
    except Exception as exc:
        logger.warning(f"Ollama inference error or timeout: {exc}")
        return {
            "available": False,
            "model": OLLAMA_MODEL,
            "error": str(exc)
        }

    return None
