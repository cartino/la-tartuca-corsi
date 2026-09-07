from __future__ import annotations

import io
import re
from datetime import date
from typing import Iterable

import fitz

from .models import CourseSlot
from .normalization import canonical_course_name, clean_spaces

TIME_RE = re.compile(r"^(\d{1,2}\.\d{2})\s*[–-]\s*(\d{1,2}\.\d{2})", re.IGNORECASE)
DATE_RE = re.compile(r"\b(?:Dal\s+)?(\d{1,2})/(\d{1,2})\b", re.IGNORECASE)
DURATION_RE = re.compile(r"\((\d+)\s*minuti?\)", re.IGNORECASE)
AGE_RANGE_RE = re.compile(r"\b(\d+)\s*[–-]\s*(\d+)\s*anni\b", re.IGNORECASE)
AGE_SINGLE_RE = re.compile(r"\b(\d+)\s*anni\b", re.IGNORECASE)
AGE_BARE_RANGE_RE = re.compile(r"\b(\d+)\s*[–-]\s*(\d+)\s*$", re.IGNORECASE)

HEADER_DAYS = {
    "Lunedì": "lunedì",
    "Martedì": "martedì",
    "Mercoledì": "mercoledì",
    "Giovedì": "giovedì",
    "Venerdì": "venerdì",
    "SABATO": "sabato",
}


def _extract_year(page_text: str, fallback_year: int | None) -> int:
    match = re.search(r"\b(20\d{2})\b", page_text)
    if match:
        return int(match.group(1))
    if fallback_year:
        return fallback_year
    raise ValueError("Non trovo l'anno nel PDF: inseriscilo manualmente nell'app.")


def _get_day_centers(page: fitz.Page) -> list[tuple[float, str]]:
    found: list[tuple[float, str]] = []
    for word in page.get_text("words"):
        x0, _y0, x1, _y1, text = word[:5]
        if text in HEADER_DAYS:
            found.append(((x0 + x1) / 2, HEADER_DAYS[text]))
    if len(found) >= 5:
        return sorted(found)
    # Fallback calibrato sul modello La Tartuca in A4 orizzontale.
    return [
        (124.5, "lunedì"),
        (269.9, "martedì"),
        (425.7, "mercoledì"),
        (567.5, "giovedì"),
        (691.7, "venerdì"),
        (787.3, "sabato"),
    ]


def _nearest_day(x_center: float, centers: Iterable[tuple[float, str]]) -> str:
    return min(centers, key=lambda item: abs(item[0] - x_center))[1]


def _section_from_y(y_top: float, page_height: float) -> str:
    # Il PDF della Tartuca usa tre fasce orizzontali. Le soglie sono espresse
    # come percentuale, così restano valide anche a risoluzioni leggermente diverse.
    ratio = y_top / page_height
    if ratio < 0.27:
        return "Mattino"
    if ratio < 0.50:
        return "Bambini e ragazzi"
    return "Adulti"


def _extract_age(title: str) -> tuple[str, str]:
    age_group = ""
    match = AGE_RANGE_RE.search(title)
    if match:
        age_group = f"{match.group(1)}-{match.group(2)} anni"
        title = AGE_RANGE_RE.sub("", title)
    else:
        match = AGE_SINGLE_RE.search(title)
        if match:
            age_group = f"{match.group(1)} anni"
            title = AGE_SINGLE_RE.sub("", title)
        else:
            # Alcune celle, es. HAPPY ENGLISH 11-13, omettono la parola "anni".
            match = AGE_BARE_RANGE_RE.search(title)
            if match:
                age_group = f"{match.group(1)}-{match.group(2)} anni"
                title = AGE_BARE_RANGE_RE.sub("", title)
    return clean_spaces(title).strip(" ,-"), age_group


def _parse_date(raw: str, year: int) -> date | None:
    match = DATE_RE.search(raw)
    if not match:
        return None
    return date(year, int(match.group(2)), int(match.group(1)))


def parse_schedule_pdf(pdf_bytes: bytes, fallback_year: int | None = None) -> list[CourseSlot]:
    """Estrae le celle-corso dal calendario PDF della Tartuca.

    Il parser usa il testo vettoriale e le coordinate, non OCR. Ogni blocco che
    inizia con un intervallo orario viene trattato come un corso; gli eventuali
    blocchi immediatamente successivi nella stessa colonna completano titolo e data.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    results: list[CourseSlot] = []

    for page_index, page in enumerate(doc):
        page_text = page.get_text("text")
        year = _extract_year(page_text, fallback_year)
        day_centers = _get_day_centers(page)

        blocks = []
        for raw_block in page.get_text("blocks"):
            x0, y0, x1, y1, text = raw_block[:5]
            text = clean_spaces(text)
            if not text:
                continue
            blocks.append({
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "x_center": (x0 + x1) / 2,
                "text": text,
            })

        anchors = []
        for block in blocks:
            match = TIME_RE.match(block["text"])
            if match:
                block = dict(block)
                block["start_time"] = match.group(1)
                block["end_time"] = match.group(2)
                block["day"] = _nearest_day(block["x_center"], day_centers)
                anchors.append(block)

        for anchor in anchors:
            same_day_next_y = [
                other["y0"]
                for other in anchors
                if other is not anchor
                and other["day"] == anchor["day"]
                and other["y0"] > anchor["y0"] + 3
            ]
            next_anchor_y = min(same_day_next_y) if same_day_next_y else page.rect.height
            search_bottom = min(next_anchor_y - 1, anchor["y0"] + 52)

            nearby = []
            for block in blocks:
                if block is anchor:
                    continue
                if block["y0"] < anchor["y0"] - 1 or block["y0"] > search_bottom:
                    continue
                if abs(block["x_center"] - anchor["x_center"]) > 52:
                    continue
                nearby.append(block)
            nearby.sort(key=lambda b: (b["y0"], b["x0"]))

            anchor_title = TIME_RE.sub("", anchor["text"], count=1).strip()
            title_parts = [anchor_title] if anchor_title else []
            activation_parts: list[str] = []

            for block in nearby:
                text = block["text"]
                if DATE_RE.search(text) or text.lower().startswith("da ottobre"):
                    activation_parts.append(text)
                elif not TIME_RE.match(text):
                    title_parts.append(text)

            source_title = clean_spaces(" ".join(title_parts))
            activation_raw = clean_spaces(" ".join(activation_parts))

            # Se data e titolo erano nello stesso blocco (es. Fotografia), separali.
            lower_title = source_title.lower()
            if "da ottobre" in lower_title:
                idx = lower_title.index("da ottobre")
                activation_raw = clean_spaces(source_title[idx:])
                source_title = clean_spaces(source_title[:idx])

            duration_match = DURATION_RE.search(source_title)
            duration = int(duration_match.group(1)) if duration_match else None
            title_without_duration = DURATION_RE.sub("", source_title)
            title_without_age, age_group = _extract_age(title_without_duration)
            course_name = canonical_course_name(title_without_age)
            activation_date = _parse_date(activation_raw, year)

            warning = ""
            if not source_title:
                warning = "Titolo non riconosciuto"
            elif not activation_raw:
                warning = "Data di attivazione non riconosciuta"
            elif activation_date and activation_date.strftime("%A"):
                # Verifica weekday tramite indice, senza dipendere dalla lingua del sistema.
                expected_index = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"].index(anchor["day"])
                if activation_date.weekday() != expected_index:
                    actual_day = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"][activation_date.weekday()]
                    warning = f"La data cade di {actual_day}, ma la cella è sotto {anchor['day']}"

            results.append(CourseSlot(
                source_title=source_title,
                course_name=course_name,
                day=anchor["day"],
                start_time=anchor["start_time"],
                end_time=anchor["end_time"],
                activation_raw=activation_raw,
                activation_date=activation_date,
                section=_section_from_y(anchor["y0"], page.rect.height),
                age_group=age_group,
                duration_minutes=duration,
                page_number=page_index + 1,
                x_center=round(anchor["x_center"], 2),
                y_top=round(anchor["y0"], 2),
                warning=warning,
            ))

    results.sort(key=lambda item: (item.page_number, item.y_top, item.x_center))
    return results


def parse_schedule_pdf_file(path: str, fallback_year: int | None = None) -> list[CourseSlot]:
    with open(path, "rb") as handle:
        return parse_schedule_pdf(handle.read(), fallback_year=fallback_year)
