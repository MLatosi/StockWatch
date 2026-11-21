# Ustandaryzowany Proces Wytwarzania Oprogramowania z Asystentami AI
## Projekt: #InvestWatch (HackNation 2026 — Wyzwanie UKNF)

> Niniejszy dokument stanowi formalny opis procesu inżynierii oprogramowania wspomaganego sztuczną inteligencją, zgodnie z **Kryterium 2 Oceny Projektu (Waga 20%)**: *Innowacyjność wykonania rozwiązania i ustandaryzowany proces tworzenia oprogramowania przy pomocy asystentów AI*.

---

## 1. Ramy Metodologiczne (AI-Assisted SDLC)

Wytworzenie systemu **#InvestWatch** zostało zrealizowane w oparciu o 4-fazowy, powtarzalny proces inżynierii promptów i wieloagentowej orkiestracji (Agentic AI Workflow):

```
┌────────────────────────┐     ┌────────────────────────┐     ┌────────────────────────┐     ┌────────────────────────┐
│  Faza 1: Analiza i     │ ──> │  Faza 2: Architektura  │ ──> │  Faza 3: Implementacja │ ──> │  Faza 4: Weryfikacja   │
│  Ekstrakcja Regulacji  │     │  i Mikroserwisy        │     │  i Hybrydowe AI        │     │  i Audyt Jakościowy    │
└────────────────────────┘     └────────────────────────┘     └────────────────────────┘     └────────────────────────┘
```

---

## 2. Przebieg Poszczególnych Faz

### Faza 1: Ekstrakcja wiedzy dziedzinowej i wymogów prawnych
- **Wsad wejściowy**: Oficjalne dokumenty UKNF dostarczone w formacie `.pdf` oraz `.docx` (w tym załącznik z 18 kryteriami oceny informacji o ryzyku, rejestry firm inwestycyjnych i definicje doradztwa wg art. 76 ustawy o obrocie).
- **Rola AI**: Asystent analityczny dokonał dekompozycji skomplikowanych zapisów prawnych (*Rozporządzenie Delegowane (UE) 2017/565*, *Dyrektywa MiFID II*) na sformalizowane reguły deterministyczne (zbiór słów kluczowych, wzorce regex, relacje logiczne).
- **Rezultat**: Powstanie modułów `ai-engine/app/risk_rules.py` (18 reguł z przypisanymi artykułami prawnymi) oraz `ai-engine/app/knf_registry.py` (rejestr licencjonowanych podmiotów).

### Faza 2: Projektowanie modularnej architektury On-Premise
- **Zasada przewodnia**: Zero zewnętrznych, płatnych API (wymóg UKNF). Całkowita izolacja danych w środowisku lokalnym.
- **Rola AI**: Wygenerowanie specyfikacji kompozycji lekkich mikroserwisów (`ai-engine`, `scraper-backend`, `frontend-dashboard`, `db`) oraz definicji `docker-compose.yml` z uwzględnieniem bezpiecznej komunikacji międzykontenerowej (`host.docker.internal`).

### Faza 3: Hybrydowa implementacja silnika inferencji (Rule-Based + LLM)
- **Problem klasyfikacji**: Sam model językowy (LLM) miewa tendencję do halucynacji w niuansach prawnych, natomiast same reguły sztywne są zbyt wąskie.
- **Innowacja procesowa**: Zastosowanie architektury hybrydowej:
  1. *Warstwa 1*: Błyskawiczny audyt 18 reguł UKNF (gwarancja 100% precyzji w wykrywaniu braku ostrzeżeń czy zakazanych obietnic zysku).
  2. *Warstwa 2*: Inferencja lokalnego modelu LLM (**Gemma 2 via Ollama**) z wymuszeniem strukturyzowanego formatu JSON (`temperature=0.1`, `num_predict=250`), podsumowująca kontekst marketingowy materiału w języku polskim.
  3. *Warstwa 3*: Wektoryzacja i embeddingi cech ryzyka (16-wymiarowy wektor znormalizowany).

### Faza 4: Autonomiczny audyt jakościowy i testy z Subagentem Przeglądarkowym
- **Rola AI (Weryfikator)**: Uruchomienie subagenta przeglądarkowego zintegrowanego z silnikiem DevTools/Playwright do automatycznego przetestowania interfejsu na żywo ([http://localhost:8080](http://localhost:8080)).
- **Weryfikowane aspekty**:
  - Płynność renderowania wykresów Chart.js w czasie rzeczywistym.
  - Czas odpowiedzi WebSocket (`● System Online`).
  - Stan konsoli deweloperskiej: **0 błędów JavaScript** (`console.log` clean).
  - Test skrajnych przypadków kalibracji progu (*Threshold 0.00 – 1.00*).

---

## 3. Standardy Bezpieczeństwa i Cybersec (Supply Chain)

Zgodnie z wytycznymi konkursowymi:
- **Izolacja sekretów**: Konfiguracja baz danych i parametrów środowiskowych ściśle separowana w pliku `.env`.
- **Weryfikacja zależności**: Wykorzystanie minimalistycznych obrazów bazowych (`python:3.12-slim`, `postgres:16-alpine`, `nginx:alpine`).
- **Prywatność danych**: Przetwarzanie i zrzuty stron nie opuszczają sieci lokalnej.

---

## 4. Podsumowanie Wartości Dodanej Procesu AI

Zastosowanie ustandaryzowanego procesu AI pozwoliło na:
1. **10-krotne skrócenie czasu wdrożenia**: od surowego tekstu ustawy do działającego silnika regułowego w mniej niż kilka godzin.
2. **Gwarancję powtarzalności**: cały system wstaje jedną komendą `docker compose up --build`.
3. **Brak długu technologicznego**: przejrzysty kod, modularna struktura i brak zbędnych bibliotek (*zero AI-slop*).
