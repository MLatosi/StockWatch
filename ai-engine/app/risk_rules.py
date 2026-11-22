"""Moduł tekstowej weryfikacji kryteriów UKNF / MiFID II.

Źródło: ZASÓB DLA UCZESTNIKÓW - InvestWatch - kryteria oceny informacji o ryzyku.docx
Podstawa prawna: Rozporządzenie delegowane Komisji (UE) 2017/565 (art. 44) oraz MiFID II (art. 24).
"""
import re

RISK_CRITERIA_META = {
    1: ("Identyfikacja firmy", "art. 44 ust. 2 lit. a rozporządzenia del. 2017/565"),
    2: ("Oznaczenie reklamy", "art. 24 ust. 3 MiFID II"),
    3: ("Informacja o ryzyku przy obietnicy zysku", "art. 44 ust. 2 lit. b rozporządzenia del. 2017/565"),
    4: ("Rozmiar czcionki ryzyka", "art. 44 ust. 2 lit. c rozporządzenia del. 2017/565"),
    5: ("Ekspozycja i kontrast ryzyka", "art. 44 ust. 2 lit. c i e rozporządzenia del. 2017/565"),
    6: ("Zakrywanie / ukrywanie ryzyka", "art. 44 ust. 2 lit. e rozporządzenia del. 2017/565"),
    7: ("Dostępność za 1 kliknięciem", "art. 44 ust. 2 lit. b i e rozporządzenia del. 2017/565"),
    8: ("Responsywność i format", "art. 44 ust. 2 lit. g rozporządzenia del. 2017/565"),
    9: ("Zrozumiałość dla grupy docelowej", "art. 44 ust. 2 lit. d rozporządzenia del. 2017/565"),
    10: ("Spójność językowa", "art. 44 ust. 2 lit. f rozporządzenia del. 2017/565"),
    11: ("Porównania produktów / usług", "art. 44 ust. 3 rozporządzenia del. 2017/565"),
    "12a": ("Wyniki historyczne: okres i zakres", "art. 44 ust. 4 rozporządzenia del. 2017/565"),
    "12b": ("Wyniki historyczne: warunki i waluta", "art. 44 ust. 4 rozporządzenia del. 2017/565"),
    13: ("Dominacja wyników historycznych", "art. 44 ust. 4 lit. a rozporządzenia del. 2017/565"),
    14: ("Ostrzeżenie przy wynikach historycznych", "art. 44 ust. 4 lit. d rozporządzenia del. 2017/565"),
    15: ("Prognozy przyszłych wyników", "art. 44 ust. 6 rozporządzenia del. 2017/565"),
    16: ("Informacja podatkowa", "art. 44 ust. 7 rozporządzenia del. 2017/565"),
    17: ("Zakaz sugerowania aprobaty organu nadzoru", "art. 44 ust. 8 rozporządzenia del. 2017/565"),
    18: ("Nadzór jako argument bezpieczeństwa", "art. 44 ust. 8 rozporządzenia del. 2017/565"),
}

def contains_any(text_lower: str, *phrases) -> list[str]:
    return [p for p in phrases if p in text_lower]

def evaluate_all_rules(text: str, knf_companies_found: list[dict], author: str | None = None) -> list[dict]:
    """Ocenia dostępny tekst według zdefiniowanych kryteriów UKNF."""
    low = text.lower()
    issues = []

    def add_violation(rule_key, detail: str):
        title, legal_basis = RISK_CRITERIA_META[rule_key]
        matched = [phrase for phrase in evidence_cues.get(str(rule_key), []) if phrase in low]
        cue = matched[0] if matched else ""
        if cue:
            cue_at = low.find(cue)
            starts = [low.rfind(mark, 0, cue_at) for mark in (".", "!", "?", "\n")]
            start = max(starts) + 1
            ends = [pos for mark in (".", "!", "?", "\n") if (pos := low.find(mark, cue_at + len(cue))) >= 0]
            end = min(ends) if ends else len(text)
            quote = text[start:end].strip()
        else:
            quote = text[:240].strip()
        issues.append({
            "id": str(rule_key),
            "title": title,
            "detail": detail,
            "legal_basis": legal_basis,
            "evidence": {
                "quote": quote[:320],
                "matched_terms": matched[:5],
                "method": "Dopasowanie reguły do pobranego tekstu",
            },
        })

    # Sygnały kluczowe
    profit_terms = contains_any(low, "gwarantowany zysk", "bez ryzyka", "pewny zysk", "zarób szybko",
                                "100% zysku", "wysoka stopa zwrotu", "wysoki zysk", "pasywny dochód",
                                "zarabiaj miesięcznie", "pomnóż oszczędności", "stopa zwrotu")
    risk_terms = contains_any(low, "ryzyko", "ryzykiem", "strata", "stratą", "możesz stracić",
                              "utraty części lub całości", "utraty kapitału", "ostrzeżenie o ryzyku",
                              "kontrakty cfd są złożonymi instrumentami", "inwestowanie wiąże się z")
    promo_signals = contains_any(low, "kod promocyjny", "reflid", "afiliacja", "współpraca", "partner",
                                 "polecam", "reklama", "promocja", "#ad", "#reklama", "#wspolpraca",
                                 "#sponsorowane", "skorzystaj z linku", "załóż konto z kodem")

    evidence_cues = {
        "1": promo_signals + profit_terms, "2": promo_signals + profit_terms, "3": profit_terms,
        "4": ["drobnym drukiem", "mała czcionka", "font-size: 8px", "font-size: 9px", "font-size: 10px", "text-xs"],
        "5": ["opacity: 0", "display: none", "color: #fff; background: #fff", "niewidoczn", "słaby kontrast", "szary tekst na szarym tle"],
        "6": risk_terms + ["stopka", "sekcja legal", "przypis na dole", "w regulaminie na stronie", "nota prawna"],
        "7": ["kliknij aby rozwinąć ryzyko", "ryzyko dostępne po kliknięciu", "zobacz ostrzeżenie w osobnym linku", "więcej informacji pod linkiem", "rozwinięcie wymagane"],
        "8": ["overflow: hidden", "ucięty tekst", "obcięty komunikat", "niewidoczne na telefonie"],
        "9": ["delta-neutral", "gamma scalping", "var 99%", "hedging krzyżowy", "struktura contango", "backwardation"],
        "10": ["cfds are complex instruments and come with a high risk", "capital at risk", "past performance is no guarantee", "your capital may be at risk", "inwestuj", "zysk", "zarabiaj", "akcje", "giełda"],
        "11": ["najlepszy broker", "jesteśmy lepsi niż", "nr 1 w polsce", "bezkonkurencyjny", "najtańszy dom maklerski"],
        "12a": ["wyniki historyczne", "stopa zwrotu za ostatnie", "zysk w ubiegłym roku", "zarobiliśmy w 202", "wykres stóp zwrotu"],
        "12b": ["wyniki historyczne", "stopa zwrotu za ostatnie", "zysk w ubiegłym roku", "zarobiliśmy w 202", "wykres stóp zwrotu"],
        "13": ["rekordowy zysk 300%", "wyniki historyczne:", "historyczna stopa zwrotu"],
        "14": ["wyniki historyczne", "stopa zwrotu za ostatnie", "zysk w ubiegłym roku", "zarobiliśmy w 202", "wykres stóp zwrotu"],
        "15": ["prognozujemy wzrost", "wzrośnie o minimum", "przewidujemy zysk", "będzie rosnąć", "prognoza stóp zwrotu"],
        "16": ["brak podatku", "optymalizacja podatkowa", "korzyści podatkowe", "podatek belki", "zwolnienie z opodatkowania"],
        "17": ["zatwierdzony przez knf", "aprobata knf", "rekomendowany przez knf", "posiada akredytację knf"],
        "18": ["w pełni bezpiecz", "gwarancja bezpieczeństwa dzięki knf", "pod nadzorem knf co gwarantuje zysk", "spełniamy rygorystyczne wymogi knf więc nie stracisz"],
    }

    # Reguła 1: Identyfikacja firmy (art. 44 ust. 2 lit. a)
    # Sprawdza, czy materiał zawiera oficjalną nazwę firmy inwestycyjnej
    if (promo_signals or profit_terms) and not knf_companies_found:
        add_violation(1, "W materiale promocyjnym nie zidentyfikowano oficjalnej nazwy licencjonowanej firmy inwestycyjnej.")

    # Reguła 2: Oznaczenie reklamy (art. 24 ust. 3 MiFID II)
    # Weryfikuje, czy materiał o charakterze promocyjnym jest jednoznacznie oznaczony
    is_promo_content = bool(profit_terms or promo_signals)
    has_explicit_ad_tag = bool(contains_any(low, "#reklama", "#ad", "materiał reklamowy", "informacja handlowa",
                                            "ogłoszenie płatne", "materiał promocyjny", "#współpraca płatna",
                                            "#sponsorowane", "płatna współpraca"))
    if is_promo_content and not has_explicit_ad_tag:
        add_violation(2, "Materiał zawiera treść promocyjną, lecz brak jednoznacznego oznaczenia (np. #reklama, materiał promocyjny).")

    # Reguła 3: Informacja o ryzyku przy obietnicy zysku (art. 44 ust. 2 lit. b)
    if profit_terms and not risk_terms:
        add_violation(3, f"Wykryto obietnicę zysku ({', '.join(profit_terms[:2])}) bez towarzyszącej bezpośredniej informacji o ryzyku inwestycyjnym.")

    # Reguła 4: Rozmiar czcionki ryzyka (art. 44 ust. 2 lit. c)
    # Weryfikacja czy w tekście pojawiają się wskaźniki małego druku / przypisu
    if contains_any(low, "drobnym drukiem", "mała czcionka", "font-size: 8px", "font-size: 9px", "font-size: 10px", "text-xs"):
        add_violation(4, "Informacja o ryzyku sformatowana nieproporcjonalnie mniejszą czcionką niż obietnice korzyści.")

    # Reguła 5: Ekspozycja i kontrast ryzyka (art. 44 ust. 2 lit. c i e)
    if contains_any(low, "opacity: 0", "display: none", "color: #fff; background: #fff", "niewidoczn", "słaby kontrast", "szary tekst na szarym tle"):
        add_violation(5, "Naruszenie widoczności informacji o ryzyku (zbyt niski kontrast lub przesłonięcie elementami graficznymi).")

    # Reguła 6: Zakrywanie / ukrywanie ryzyka (art. 44 ust. 2 lit. e)
    if risk_terms and contains_any(low, "stopka", "sekcja legal", "przypis na dole", "w regulaminie na stronie", "*szczegóły w regulaminie", "nota prawna"):
        add_violation(6, "Informacja o ryzyku ukryta w przypisie, sekcji 'Legal' lub w miejscu o znikomej uwadze odbiorcy.")

    # Reguła 7: Dostępność za 1 kliknięciem (art. 44 ust. 2 lit. b i e)
    if contains_any(low, "kliknij aby rozwinąć ryzyko", "ryzyko dostępne po kliknięciu", "zobacz ostrzeżenie w osobnym linku", "więcej informacji pod linkiem", "rozwinięcie wymagane"):
        add_violation(7, "Zapoznanie się z ryzykiem wymaga dodatkowej akcji użytkownika (kliknięcia linku / rozwinięcia warstwy).")

    # Reguła 8: Responsywność (różne urządzenia) (art. 44 ust. 2 lit. g)
    if contains_any(low, "overflow: hidden", "ucięty tekst", "obcięty komunikat", "niewidoczne na telefonie"):
        add_violation(8, "Komunikat o ryzyku ulega ucięciu lub zniekształceniu na urządzeniach mobilnych.")

    # Reguła 9: Zrozumiałość dla grupy docelowej (art. 44 ust. 2 lit. d)
    # Analiza trudnego żargonu bez wyjaśnień lub nadmiernej długości zdań
    jargon_without_explanation = contains_any(low, "delta-neutral", "gamma scalping", "vaR 99%", "hedging krzyżowy", "struktura contango", "backwardation")
    if jargon_without_explanation:
        add_violation(9, f"Użycie wysoce specjalistycznego żargonu ({', '.join(jargon_without_explanation)}) bez objaśnienia dla inwestora indywidualnego.")

    # Reguła 10: Spójność językowa (art. 44 ust. 2 lit. f)
    has_english_disclaimer = bool(contains_any(low, "cfds are complex instruments and come with a high risk",
                                               "capital at risk", "past performance is no guarantee",
                                               "your capital may be at risk"))
    has_polish_body = bool(contains_any(low, "inwestuj", "zysk", "zarabiaj", "akcje", "konto maklerskie", "giełda"))
    if has_polish_body and has_english_disclaimer and not risk_terms:
        add_violation(10, "Główny przekaz sformułowano w języku polskim, podczas gdy ostrzeżenie o ryzyku podano wyłącznie w języku obcym.")

    # Reguła 11: Porównania produktów / usług (art. 44 ust. 3)
    if contains_any(low, "najlepszy broker", "jesteśmy lepsi niż", "nr 1 w polsce", "bezkonkurencyjny", "najtańszy dom maklerski") and not contains_any(low, "źródło:", "badanie z dnia", "metodologia", "ranking z dnia"):
        add_violation(11, "Porównanie produktów lub usług ma charakter kategoryczny bez wskazania obiektywnego źródła, daty lub założeń.")

    # Reguła 12a: Wyniki historyczne - okres i zakres (art. 44 ust. 4)
    has_history = bool(contains_any(low, "wyniki historyczne", "stopa zwrotu za ostatnie", "zysk w ubiegłym roku", "zarobiliśmy w 202", "wykres stóp zwrotu"))
    if has_history and not contains_any(low, "ostatnie 5 lat", "pełne 5 lat", "okres 5 lat", "12 miesięcy", "okres referencyjny"):
        add_violation("12a", "Prezentowane wyniki historyczne nie obejmują wymaganego okresu 5 lat w ujęciu 12-miesięcznym lub brak okresu referencyjnego.")

    # Reguła 12b: Wyniki historyczne - warunki i waluta (art. 44 ust. 4)
    if has_history and not contains_any(low, "kurs walut", "kursu walutowego", "prowizje", "opłaty", "uwzględnia opłaty", "wpływ kosztów"):
        add_violation("12b", "Przy wynikach historycznych pominięto informację o wpływie opłat, prowizji lub zmian kursów walutowych na ostateczny wynik.")

    # Reguła 13: Dominacja wyników historycznych (art. 44 ust. 4 lit. a)
    if contains_any(low, "rekordowy zysk 300%", "wyniki historyczne:", "historyczna stopa zwrotu") and not risk_terms:
        add_violation(13, "Wyniki z przeszłości stanowią dominujący i najbardziej wyeksponowany element materiału promocyjnego.")

    # Reguła 14: Ostrzeżenie przy wynikach historycznych (art. 44 ust. 4 lit. d)
    if has_history and not contains_any(low, "nie stanowią wiarygodnego wskaźnika przyszłych wyników",
                                        "nie są gwarancją przyszłych zysków", "nie gwarantują powtórzenia w przyszłości"):
        add_violation(14, "Brak wymaganego zastrzeżenia: 'Wyniki historyczne nie stanowią wiarygodnego wskaźnika przyszłych wyników'.")

    # Reguła 15: Prognozy przyszłych wyników (art. 44 ust. 6)
    has_forecast = bool(contains_any(low, "prognozujemy wzrost", "wzrośnie o minimum", "przewidujemy zysk", "będzie rosnąć", "prognoza stóp zwrotu"))
    if has_forecast and not contains_any(low, "prognoza nie jest wiarygodnym wskaźnikiem", "prognozy obarczone są ryzykiem"):
        add_violation(15, "Sformułowano prognozę przyszłych wyników bez wyraźnego ostrzeżenia, że prognoza nie stanowi wiarygodnego wskaźnika.")

    # Reguła 16: Informacja podatkowa (art. 44 ust. 7)
    has_tax_reference = bool(contains_any(low, "brak podatku", "optymalizacja podatkowa", "korzyści podatkowe", "podatek belki", "zwolnienie z opodatkowania"))
    if has_tax_reference and not contains_any(low, "indywidualnej sytuacji", "zależy od indywidualnej sytuacji", "może ulec zmianie"):
        add_violation(16, "Odwołanie do korzyści podatkowych bez zastrzeżenia, że traktowanie zależy od indywidualnej sytuacji podatnika i może ulec zmianie.")

    # Reguła 17: Zakaz sugerowania aprobaty organu nadzoru (art. 44 ust. 8)
    if "knf" in low and contains_any(low, "zatwierdzony przez knf", "aprobata knf", "rekomendowany przez knf", "posiada akredytację knf"):
        add_violation(17, "Bezprawne sugerowanie, że produkt lub usługa uzyskała zatwierdzenie, aprobatę lub rekomendację KNF.")

    # Reguła 18: Nadzór jako argument bezpieczeństwa (art. 44 ust. 8)
    if "knf" in low and contains_any(low, "w pełni bezpiecz", "gwarancja bezpieczeństwa dzięki knf", "pod nadzorem knf co gwarantuje zysk", "spełniamy rygorystyczne wymogi knf więc nie stracisz"):
        add_violation(18, "Wykorzystanie faktu podlegania nadzorowi KNF jako argumentu gwarantującego bezpieczeństwo zainwestowanego kapitału.")

    return issues
