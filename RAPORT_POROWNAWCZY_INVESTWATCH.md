# Raport: co rozwijać w InvestWatch, a co zachować

**Data:** 22 listopada 2026 r.  
**Zakres:** lokalny projekt StockWatch/InvestWatch oraz trzy archiwa ZIP przekazane do rozmowy.

## Wniosek

Zachować obecny, prosty przepływ, który już działa: wyszukanie publicznych kandydatów przez Google News RSS → kolejka → pobranie strony → analiza → wynik dla analityka. Rozwijać go stopniowo, dodając przede wszystkim dowody uzasadniające wynik i sposób mierzenia jakości.

Nie kopiować w całości żadnego z trzech repozytoriów. Pierwsze ma najwięcej funkcji, ale jest znacznie bardziej złożone i jego własny raport ujawnia problemy z uruchomieniem oraz ograniczenia źródeł. Drugie dobrze rozdziela kolektory i przetwarzanie, ale jego domyślny scenariusz korzysta z próbek, a publiczne pobieranie z Instagrama i TikToka jest opisane jako zawodne. Trzecie ma mocną dokumentację wymagań, ale w macierzy statusów większość prac pozostaje w toku lub planach.

## Co zachować z obecnego projektu

1. **Działające wyszukiwanie publicznych stron.** Google News RSS i lista haseł dają mierzalny, zrozumiały punkt startowy. W UI należy jasno nazywać to wyszukiwaniem publicznych wyników, a nie skanowaniem całego internetu.
2. **Prosty przepływ od odkrycia do wyniku.** Backend, kolejka, PostgreSQL, silnik analizy i dashboard są już połączone. Zachować ten przepływ i ulepszać go bez przebudowy całego stosu.
3. **Lokalne uruchamianie i brak płatnego API w podstawowej ścieżce.** To praktyczne na demonstrację i pasuje do założenia przetwarzania lokalnego.
4. **Reguły jako wyjaśnialna podstawa.** Reguły są łatwiejsze do pokazania i omówienia niż sam wynik modelu. Ollama powinna je uzupełniać, a nie ukrywać, skąd wzięła się ocena.
5. **Nowy układ wyników.** Karty wyników i uzasadnienia powinny pozostać głównym widokiem; statystyki, konfiguracja i narzędzia mogą być drugorzędne.

## Co dodać — kolejność prac

| Priorytet | Co dodać | Dlaczego | Rozsądny zakres pierwszej wersji |
|---|---|---|---|
| **P0** | Dowód dla każdej reguły | Analityk musi móc szybko sprawdzić, skąd system wziął podejrzenie. | Przy wyniku zapisać `rule_id`, cytowany fragment, podstawę prawną, URL, datę pobrania i wersję analizy. W UI pokazać cytat przy uzasadnieniu. |
| **P0** | Zestaw przykładów z oceną człowieka | Bez etykiet nie wiadomo, czy wyniki są trafne; obecne szacunki FP/FN nie są pomiarem jakości. | Zacząć od 20–50 przykładów: ryzykowne, zgodne, niejednoznaczne i fałszywe dopasowania. Zapisać ocenę eksperta i porównywać ją z wynikiem systemu. |
| **P0** | Uczciwe statusy źródeł i błędów | RSS może pasować tematycznie, ale artykuł może być niedostępny, zduplikowany albo nie zawierać analizowalnego tekstu. | Rozdzielić statusy: znaleziony, pobrany, przeanalizowany, duplikat, niedostępny, błąd. Pokazywać kolejkę i przyczynę niepowodzenia. |
| **P1** | Wspólny format danych i osobne adaptery źródeł | Ułatwi dodanie blogów i innych publicznych źródeł bez przepisywania analizy. | Jeden kontrakt materiału: treść, autor, źródło, dokładny URL, czas pobrania, metadane i dowody. Najpierw dodać 1–2 adaptery blogów/stron publicznych. |
| **P1** | Analiza wyglądu strony | Sama treść tekstowa nie pozwala pewnie ocenić wielkości, kontrastu ani widoczności ostrzeżenia o ryzyku. | Dla wybranych stron użyć Playwright do pobrania tekstu i zrzutu ekranu. W pierwszej iteracji mierzyć tylko te elementy, dla których da się pokazać konkretny dowód. |
| **P1** | Deduplikacja i historia zmian | Ta sama treść może pojawić się w wielu adresach; zmiana strony może być ważniejsza od kolejnego kopiuje/wklej wyniku. | Trzymać hash treści i URL, nie tworzyć kolejnych identycznych wyników, ale zachować informację o nowych adresach i zmianach treści. |
| **P1** | Aktualizowany rejestr firm | Ręczna lista nazw szybko staje się niepełna i może powodować błędne przypisania. | Zastąpić mały ręczny spis wersjonowaną migawką wiarygodnego rejestru; przechować źródło i datę aktualizacji. Nie uznawać braku dopasowania za dowód braku licencji. |
| **P2** | OCR obrazów i treści wideo | To wartościowe dla reklam w social mediach, ale wyraźnie zwiększa zależności, czas analizy i wymagania sprzętowe. | Najpierw umożliwić ręczne dodanie obrazu lub pliku, a dopiero po walidacji rozważyć automatyczny monitoring. |
| **P2** | Kolejka z retry i kontrolą tempa | Przy większej liczbie źródeł pojedynczy worker i brak kontrolowanego ponawiania utrudnią stabilną pracę. | Dodać retry z limitem i opóźnieniem, stan zadania, timeout, retry-after dla ograniczeń źródła oraz możliwość wznowienia po restarcie. |

## Co z innych repozytoriów warto zaadaptować

### Hackaton2026JJFAM/InvestWatch

Warto przejąć **sposób pokazywania dowodów**, testowe przykłady i pomysł analizy widoczności treści w przeglądarce. Repozytorium ma także bogate wzbogacanie danych podmiotów oraz OCR/transkrypcję.

Nie kopiować od razu całego stosu i wszystkich rozszerzeń. Własny raport audytowy repozytorium odnotowuje historyczne blokery instalacji i API; po poprawkach raportuje wiele przechodzących testów, ale czyste uruchomienie całego Compose pozostaje tam niepotwierdzone. Sam README opisuje też ograniczenia automatycznego dostępu do platform społecznościowych.

### PaulWeb30/investwatch

Warto przejąć **oddzielenie kolektorów od preprocessingu i analizy**, wspólny kontrakt danych, replay próbek oraz CI. To wzorzec do późniejszego rozszerzania źródeł.

Nie zakładać, że kolektory oznaczają dostęp do żywych danych: w README kolektorów TikTok i Instagram zapisano, że anonimowy scraping w testowanym stanie nie działał. Tryb replay jest domyślny, więc demonstracja na próbkach nie dowodzi działania monitoringu na platformie.

### ziomal37/investwatch

Warto przejąć **macierz wymagań**, dokumentowanie luk prawnych i reguły zapisane jako dane (np. YAML), dzięki czemu wymagania można powiązać z implementacją i testami.

Nie kopiować dużej architektury ani nie traktować planu jako działającej funkcji. W archiwum macierz pokazuje 4 pozycje `DONE`, 23 `IN_PROGRESS` i 34 `PLANNED`; to cenna mapa kierunku, ale nie dowód ukończonego przepływu.

## Czego nie robić teraz

- Nie obiecywać skanowania wszystkich postów na Instagramie, TikToku ani całego internetu. W publicznym, anonimowym dostępie takie źródła mają ograniczenia i mogą blokować pobieranie.
- Nie dodawać jednocześnie KRS, GLEIF, ESMA, giełdowych rezerw, historycznych notowań, pełnego OCR i transkrypcji wideo. Najpierw ustalić, które funkcje odpowiadają na najważniejszy przypadek UKNF.
- Nie przedstawiać `risk_score` jako prawdopodobieństwa naruszenia, dopóki nie jest skalibrowany na ocenionych przykładach.
- Nie pokazywać szacowanych FP/FN tak, jakby były zmierzone. Oznaczyć je jako orientacyjne albo zastąpić metrykami z walidacji.
- Nie uznawać braku firmy w ręcznej liście za dowód, że firma nie ma zezwolenia.

## Proponowany plan dla Twojego projektu

1. **Najpierw:** dodać cytowane dowody do wyników, dopracować stany zadań oraz przygotować mały, ręcznie oznaczony zestaw przykładów.
2. **Potem:** dodać jeden adapter publicznego źródła poza RSS i kontrakt danych wspólny dla źródeł.
3. **Następnie:** dodać analizę wizualną wybranych stron i sprawdzić ją na przykładach z ostrzeżeniem widocznym, ukrytym oraz zbyt małym.
4. **Dopiero później:** OCR, wideo, kolejne platformy i rozbudowane rejestry — jeśli poprzednie etapy pokażą, że poprawiają wykrywanie.

## Krótka decyzja

**Zostawić:** działający RSS, prosty backend, trwały zapis wyników, reguły i wyniki jako centrum dashboardu.  
**Dodać jako pierwsze:** dowody przy wynikach, rzeczywistą walidację jakości i czytelne błędy pobierania.  
**Po walidacji dodać:** modularne źródła i analizę wizualną.  
**Odłożyć:** szeroki scraping social mediów, wideo/OCR w pełnej automatyzacji i rozbudowane funkcje rynkowe.

## Materiały porównawcze

- [Hackaton2026JJFAM/InvestWatch](https://github.com/Hackaton2026JJFAM/InvestWatch)
- [PaulWeb30/investwatch](https://github.com/PaulWeb30/investwatch)
- [ziomal37/investwatch](https://github.com/ziomal37/investwatch)

Ocena opiera się na stanie kodu i dokumentów w przekazanych archiwach ZIP; statusy i możliwości repozytoriów mogą zmienić się po tej kopii.
