from __future__ import annotations

import re
import unicodedata

ITALIAN_DAYS = [
    "lunedì",
    "martedì",
    "mercoledì",
    "giovedì",
    "venerdì",
    "sabato",
    "domenica",
]

ITALIAN_MONTHS = [
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
]

# Alias osservati nei materiali reali La Tartuca. Il target è il nome logico
# del corso, non necessariamente il titolo visualizzato nel Word.
DEFAULT_ALIASES = {
    "DANZA PROPED I": "DANZA PROPEDEUTICA",
    "DANZA PROPED": "DANZA PROPEDEUTICA",
    "PRIMI PASSI": "DANZA PRIMI PASSI",
    "DANZA MODERN POP JUNIOR": "DANZA MODERN POP",
    "CERAMICA KIDS": "CERAMICA CREATIVA KIDS",
    "CERAMICA": "CERAMICA CREATIVA",
    "STRETCHING & POSTURA SMART": "STRETCHING E POSTURA SMART",
    "TONO & POSTURA SMART": "TONO POSTURA SMART",
    "TONO&POSTURA SMART": "TONO POSTURA SMART",
    "SHAPE & TONE": "SHAPE TONE",
    "SHAPE&TONE": "SHAPE TONE",
    "DEGUSTAZIONE VINI": "DEGUSTAZIONE VINI LIVELLO BASE",
    "MAGLIA FERRI CIRCOLARI": "MAGLIA CON FERRI CIRCOLARI",
    "UNCINETTO": "UNCINETTO CREATIVO",
    "HAPPY ENGLISH": "HAPPY ENGLISH KIDS",
}


def clean_spaces(value: str) -> str:
    value = (value or "").replace("\u00a0", " ")
    value = value.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", value).strip()


def normalize_for_match(value: str) -> str:
    value = clean_spaces(value).upper()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("&", " E ")
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"\b\d+\s*-\s*\d+\s*(ANNI)?\b", " ", value)
    value = re.sub(r"\b\d+\s*ANNI\b", " ", value)
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    value = re.sub(r"\bSMART\b", " SMART ", value)
    return clean_spaces(value)


def canonical_course_name(value: str, aliases: dict[str, str] | None = None) -> str:
    aliases = {**DEFAULT_ALIASES, **(aliases or {})}
    normalized = normalize_for_match(value)
    # Se il valore è già un target canonico, non riclassificarlo con un alias più generico.
    for _source, target in aliases.items():
        if normalized == normalize_for_match(target):
            return target
    # Prima alias esatti/più specifici.
    ordered = sorted(aliases.items(), key=lambda item: len(normalize_for_match(item[0])), reverse=True)
    for source, target in ordered:
        source_norm = normalize_for_match(source)
        if normalized == source_norm or normalized.startswith(source_norm + " "):
            return target
    return clean_spaces(value).strip(" ,")


def italian_full_date(value) -> str:
    return f"{value.day} {ITALIAN_MONTHS[value.month - 1]} {value.year}"


def age_bounds(value: str) -> tuple[int, int] | None:
    value = clean_spaces(value)
    m = re.search(r"(\d+)\s*-\s*(\d+)", value)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"\b(\d+)\b", value)
    if m:
        n = int(m.group(1))
        return n, n
    return None
