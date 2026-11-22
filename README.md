# #InvestWatch — Na straży inwestorów!
**Wyzwanie UKNF • HackNation 2026**

Kompleksowy system monitoringu treści w sieci służący do automatycznej identyfikacji, agregacji oraz wielopoziomowej analizy materiałów promocyjnych i ofert instrumentów oraz usług finansowych na polskim rynku. System działa w 100% w środowisku on-premise, bez zależności od zewnętrznych, płatnych API.

Publiczne strony są wyszukiwane przez Google News RSS na podstawie 20 haseł w `scraper-backend/app/watchlist.py`. Dodatkowo skaner czyta publiczne kanały RSS Strefy Inwestorów, Bankier.pl, GPW i bloga Humanista na giełdzie oraz uzupełnia je sitemapą Strefy Inwestorów. Nowe adresy z tych źródeł trafiają do tej samej kolejki pobierania i analizy. Wyszukiwanie uruchamia się co minutę i ręcznie z dashboardu („Przeszukaj źródła”); ustaw `DISCOVERY_INTERVAL_SECONDS` w `.env`, aby zmienić częstotliwość. To bezpłatne, publiczne źródła, ale nie cały Internet ani prywatne posty z Instagrama/TikToka; poszczególne strony mogą ograniczać automatyczne pobieranie.

---

## 🚀 Quick Start (Uruchomienie jedną komendą)

```sh
cp .env.example .env
docker compose up --build
```

- **Dashboard analityka:** [http://localhost:8080](http://localhost:8080)
- **Scraper & Ingestion API docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **AI Engine API docs:** [http://localhost:8001/docs](http://localhost:8001/docs)

Zatrzymanie środowiska:
```sh
docker compose down
```
Dane PostgreSQL oraz zrzuty stron są utrwalane w wolumenie `postgres_data` oraz lokalnym magazynie obiektowym.

---

## 🏛️ Trzy Moduły Analityczne (Zgodność ze specyfikacją UKNF)

1. **Moduł 1: Monitoring ekosystemu zewnętrznego (Finfluencerzy i podmioty trzecie)**
   - Weryfikacja reklam licencjonowanych firm inwestycyjnych (z rejestru KNF: domy maklerskie, banki, podmioty notyfikowane) prowadzonych przez osoby prywatne, finfluencerów lub partnerów afiliacyjnych.
   - Detekcja kodów promocyjnych, linków partnerskich i nieoznaczonych współprac komercyjnych.

2. **Moduł 2: Weryfikacja zgodności i informacji o ryzyku (Compliance 18 Reguł)**
   - Automatyczny audyt materiałów pod kątem **18 reguł prawnych** (art. 44 rozporządzenia delegowanego 2017/565 oraz MiFID II art. 24).
   - Weryfikacja proporcjonalności obietnic zysków do ryzyka, zakaz bezprawnego powoływania się na aprobatę KNF (art. 44 ust. 8), analiza prezentacji wyników historycznych oraz prognoz.

3. **Moduł 3: Identyfikacja usług nieautoryzowanych (Shadow Advisory)**
   - Wyszukiwanie ofert podmiotów typu wealth management, family office, investment consulting i kanałów z sygnałami giełdowymi świadczących doradztwo inwestycyjne bez wymaganego zezwolenia KNF (art. 76 ustawy o obrocie instrumentami finansowymi).

---

## 🏗️ Architektura i Przepływ Danych

```
[Źródła WWW / Social Media / Próbki] 
       │
       ▼
[Scraper & Backend (FastAPI, User-Agent Rotation, Kolejka zadań, Deduplikacja SHA-256)]
       │
       ├──► [Magazyn Obiektowy: Surowe zrzuty HTML / Snapshoty]
       ├──► [PostgreSQL 16: Baza metadanych i statusów zgłoszeń]
       │
       ▼
[Silnik AI (Heurystyki prawne 18 reguł + KNF Registry + opcjonalna Ollama)]
       │
       ▼
[WebSockets & REST API]
       │
       ▼
[Dashboard Webowy (Chart.js, Kalibracja Threshold, Alerty w czasie rzeczywistym)]
```

---

## ⚙️ Wymagania sprzętowe

- Docker Engine / Docker Desktop z Compose v2
- 4 GB RAM dla trybu standardowego (lokalny silnik analityczny reguł i rejestru KNF);
- 8 GB+ RAM w przypadku włączenia lokalnego kontenera Ollama (np. model Gemma 2 / Llama 3).

---

## 🛡️ Bezpieczeństwo i Łańcuch Dostaw (Cybersec)

- **Izolacja konfiguracji:** Poufne dane i parametry połączeń są ściśle izolowane w pliku `.env` (wykluczonym z repozytorium kodu).
- **Skan podatności (Zero Vulnerabilities):**
  ```sh
  pip-audit -r scraper-backend/requirements.txt -r ai-engine/requirements.txt
  ```

---

## 🤖 Ustandaryzowany Proces Wytwarzania z Asystentami AI

Projekt został zrealizowany w oparciu o ustandaryzowany proces inżynierii oprogramowania wspomagany przez asystenta AI:
1. **Analiza wymagań regulacyjnych:** Automatyczna dekompozycja oficjalnych aktów prawnych (rozporządzenie 2017/565, ustawa o obrocie) na reguły scoringowe i wzorce dopasowań.
2. **Architektura mikrousług:** Wygenerowanie modularnych, lekkich serwisów Docker Compose ze ścisłą separacją odpowiedzialności (Ingestion vs Inference vs Presentation).
3. **Pętla walidacyjna i testy:** Iteracyjna walidacja reguł audytowych na syntetycznych i realnych próbkach materiałów promocyjnych (false-positive reduction).
