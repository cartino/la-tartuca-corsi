from __future__ import annotations

import io
import re
from dataclasses import asdict
from difflib import SequenceMatcher

from docx import Document

from .models import WordCourseSection, WordGroup
from .normalization import ITALIAN_DAYS, age_bounds, clean_spaces, normalize_for_match

COURSE_URL_RE = re.compile(r"https?://(?:www\.)?latartuca\.it/corso/", re.IGNORECASE)
TIME_RE = re.compile(r"\b(\d{1,2}\.\d{2})\b")
DAY_RE = re.compile("|".join(map(re.escape, ITALIAN_DAYS)), re.IGNORECASE)
FIELD_PREFIXES = (
    "frequenza", "durata", "quota", "insegnante", "conduttore", "attivazione",
    "prossima attivazione", "inizio corso", "calendario", "sede"
)


def _parse_day_times(text: str) -> tuple[str, str, str]:
    d = DAY_RE.search(text or "")
    times = TIME_RE.findall(text or "")
    return (d.group(0).lower() if d else "", times[0] if len(times) >= 1 else "", times[1] if len(times) >= 2 else "")


def _duration_minutes_from_text(text: str) -> int | None:
    text = clean_spaces(text).lower()
    m = re.search(r"da\s+(\d+)\s*minuti", text)
    if m:
        return int(m.group(1))
    m = re.search(r"da\s+(\d+)\s*ora(?:e)?\s+e\s+(\d+)\s*minuti", text)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.search(r"da\s+(\d+)\s*ore?\b", text)
    if m:
        return int(m.group(1)) * 60
    m = re.search(r"da\s+1\s*ora\s+e\s+(\d+)\s*minuti", text)
    if m:
        return 60 + int(m.group(1))
    return None


def _looks_like_label(text: str) -> bool:
    t = clean_spaces(text)
    if not t or t.lower().startswith(FIELD_PREFIXES) or COURSE_URL_RE.search(t):
        return False
    # I label dei gruppi nel documento reale sono quasi sempre brevi e in maiuscolo.
    alpha = [c for c in t if c.isalpha()]
    if not alpha:
        return False
    if t.upper().startswith("GRUPPO"):
        return len(t) < 110
    upper_ratio = sum(c.isupper() for c in alpha) / len(alpha)
    return upper_ratio > 0.65 and len(t) < 90


def _age_from_label(text: str) -> str:
    bounds = age_bounds(text)
    if not bounds:
        return ""
    a, b = bounds
    return f"{a} anni" if a == b else f"{a}-{b} anni"


def _build_groups(paragraphs, start: int, end: int) -> list[WordGroup]:
    freq_indexes = [i for i in range(start, end) if paragraphs[i].text.strip().lower().startswith("frequenza")]
    groups: list[WordGroup] = []
    previous_freq = start

    for gidx, freq_idx in enumerate(freq_indexes):
        next_freq = freq_indexes[gidx + 1] if gidx + 1 < len(freq_indexes) else end
        # Cerca il label più vicino prima della Frequenza, ma dopo la precedente frequenza.
        label_idx = None
        label_text = ""
        for i in range(freq_idx - 1, max(previous_freq, start) - 1, -1):
            text = paragraphs[i].text.strip()
            if not text:
                continue
            if _looks_like_label(text):
                label_idx = i
                label_text = clean_spaces(text)
                break
            # Non attraversare la descrizione o un altro campo strutturato.
            if text.lower().startswith(FIELD_PREFIXES):
                continue
            if len(text) > 120:
                break

        frequency_text = clean_spaces(paragraphs[freq_idx].text)
        day, start_time, end_time = _parse_day_times(frequency_text)
        duration_text = quota_text = teacher_text = activation_text = ""
        duration_idx = quota_idx = teacher_idx = activation_idx = None
        calendar_texts: list[str] = []
        calendar_indexes: list[int] = []

        for i in range(freq_idx + 1, next_freq):
            text = clean_spaces(paragraphs[i].text)
            lower = text.lower()
            if lower.startswith("durata") and not duration_text:
                duration_text, duration_idx = text, i
            elif lower.startswith("quota") and not quota_text:
                quota_text, quota_idx = text, i
            elif (lower.startswith("insegnante") or lower.startswith("conduttore")) and not teacher_text:
                teacher_text, teacher_idx = text, i
            elif (lower.startswith("attivazione") or lower.startswith("prossima attivazione") or lower.startswith("inizio corso")) and not activation_text:
                activation_text, activation_idx = text, i
            elif lower.startswith("calendario"):
                calendar_texts.append(text)
                calendar_indexes.append(i)

        groups.append(WordGroup(
            index=gidx,
            label_text=label_text,
            label_paragraph_index=label_idx,
            frequency_text=frequency_text,
            frequency_paragraph_index=freq_idx,
            duration_text=duration_text,
            duration_paragraph_index=duration_idx,
            quota_text=quota_text,
            quota_paragraph_index=quota_idx,
            teacher_text=teacher_text,
            teacher_paragraph_index=teacher_idx,
            activation_text=activation_text,
            activation_paragraph_index=activation_idx,
            calendar_texts=calendar_texts,
            calendar_paragraph_indexes=calendar_indexes,
            day=day,
            start_time=start_time,
            end_time=end_time,
            age_group=_age_from_label(label_text),
            lesson_duration_minutes=_duration_minutes_from_text(duration_text),
        ))
        previous_freq = freq_idx
    return groups


def read_word_course_sections(docx_bytes: bytes) -> list[WordCourseSection]:
    doc = Document(io.BytesIO(docx_bytes))
    paragraphs = doc.paragraphs
    starts = [i for i, p in enumerate(paragraphs) if COURSE_URL_RE.search(p.text.strip())]
    sections: list[WordCourseSection] = []

    for pos, start in enumerate(starts):
        end = starts[pos + 1] if pos + 1 < len(starts) else len(paragraphs)
        url = clean_spaces(paragraphs[start].text)
        title = ""
        first_content_idx = start + 1
        for i in range(start + 1, end):
            text = clean_spaces(paragraphs[i].text)
            if text:
                title = text
                first_content_idx = i
                break
        groups = _build_groups(paragraphs, first_content_idx + 1, end)
        frequency = groups[-1].frequency_text if groups else ""
        activation = groups[-1].activation_text if groups else ""

        description: list[str] = []
        first_structured = min([g.label_paragraph_index or g.frequency_paragraph_index or end for g in groups], default=end)
        for i in range(first_content_idx + 1, first_structured):
            t = clean_spaces(paragraphs[i].text)
            if t and not t.lower().startswith("sede"):
                description.append(t)

        site_text = "\n".join(clean_spaces(p.text) for p in paragraphs[start:end] if clean_spaces(p.text))
        sections.append(WordCourseSection(
            url=url,
            title=title,
            paragraph_start=start,
            paragraph_end=end,
            frequency_text=frequency,
            activation_text=activation,
            normalized_title=normalize_for_match(title),
            groups=groups,
            description_paragraphs=description,
            site_text=site_text,
        ))
    return sections


def best_word_match(course_name: str, word_sections: list[WordCourseSection]) -> tuple[WordCourseSection | None, int]:
    target = normalize_for_match(course_name)
    if not target or not word_sections:
        return None, 0
    best = None
    score = 0
    for section in word_sections:
        current = int(round(SequenceMatcher(None, target, section.normalized_title).ratio() * 100))
        if target in section.normalized_title or section.normalized_title in target:
            current = max(current, 88)
        if current > score:
            score = current
            best = section
    return best, score


def word_sections_as_dicts(sections: list[WordCourseSection]) -> list[dict]:
    return [asdict(item) for item in sections]
