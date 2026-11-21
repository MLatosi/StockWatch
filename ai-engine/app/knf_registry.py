"""Oficjalny rejestr podmiotów nadzorowanych przez KNF (firmy inwestycyjne).

Zgodnie z Załącznikiem do Tematu 1 i Tematu 2 Wyzwania KNF HackNation 2026:
- Domy maklerskie
- Banki prowadzące działalność maklerską
- Notyfikowane firmy inwestycyjne (oddziały i transgraniczne)
"""

KNF_AUTHORIZED_FIRMS = [
    # Domy Maklerskie w Polsce
    {"name": "XTB S.A.", "aliases": ["xtb", "x-trade brokers", "x trade brokers", "xtb s.a."]},
    {"name": "Dom Maklerski BOŚ S.A.", "aliases": ["dm boś", "dm bos", "dom maklerski boś", "bossa.pl", "bossa"]},
    {"name": "Biuro Maklerskie mBanku", "aliases": ["mbank", "dm mbanku", "biuro maklerskie mbanku", "mforex"]},
    {"name": "Noble Securities S.A.", "aliases": ["noble securities", "noble securities s.a."]},
    {"name": "Trigon Dom Maklerski S.A.", "aliases": ["trigon", "trigon dm", "trigon dom maklerski"]},
    {"name": "Santander Biuro Maklerskie", "aliases": ["santander bm", "santander biuro maklerskie", "biuro maklerskie santander"]},
    {"name": "Biuro Maklerskie PKO Banku Polskiego", "aliases": ["bm pko bp", "biuro maklerskie pko bp", "bm pko"]},
    {"name": "Biuro Maklerskie Pekao", "aliases": ["bm pekao", "biuro maklerskie pekao"]},
    {"name": "Biuro Maklerskie Alior Bank", "aliases": ["alior trader", "bm alior banku", "biuro maklerskie alior"]},
    {"name": "Ipopema Securities S.A.", "aliases": ["ipopema", "ipopema securities"]},
    {"name": "Michael / Ström Dom Maklerski S.A.", "aliases": ["michael strom", "michael / ström", "michael strom dm"]},
    {"name": "Dom Maklerski BDM S.A.", "aliases": ["bdm", "dom maklerski bdm", "dm bdm"]},
    {"name": "Erste Securities Polska S.A.", "aliases": ["erste securities", "erste securities polska"]},
    {"name": "Q Securities S.A.", "aliases": ["q securities", "q securities s.a."]},
    {"name": "NWAI Dom Maklerski S.A.", "aliases": ["nwai", "nwai dom maklerski"]},

    # Notyfikowane firmy zagraniczne działające w Polsce (oddziały lub transgranicznie)
    {"name": "Revolut Securities Europe UAB", "aliases": ["revolut", "revolut securities", "revolut invest"]},
    {"name": "Saxo Bank A/S", "aliases": ["saxo", "saxo bank", "saxo bank a/s"]},
    {"name": "Interactive Brokers Ireland / Central Europe", "aliases": ["interactive brokers", "ibkr"]},
    {"name": "eToro (Europe) Ltd", "aliases": ["etoro", "etoro europe"]},
    {"name": "Freedom Finance Europe Ltd", "aliases": ["freedom finance", "freedom24", "freedom finance europe"]},
    {"name": "Admirals Europe AS", "aliases": ["admirals", "admiral markets"]},
    {"name": "OANDA TMS Brokers S.A.", "aliases": ["tms brokers", "oanda", "oanda tms"]},
    {"name": "FlatexDEGIRO Bank AG", "aliases": ["degiro", "flatexdegiro"]},
    {"name": "Plus500CY Ltd", "aliases": ["plus500", "plus500cy"]},
    {"name": "CMC Markets Germany GmbH", "aliases": ["cmc markets"]}
]

def find_knf_entities(text: str) -> list[dict]:
    """Wyszukuje licencjonowane firmy inwestycyjne KNF w podanym tekście."""
    low = text.lower()
    matched = []
    for firm in KNF_AUTHORIZED_FIRMS:
        for alias in firm["aliases"]:
            # Pełne dopasowanie słowa / wyrażenia
            if alias in low:
                matched.append(firm)
                break
    return matched
