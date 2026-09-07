from __future__ import annotations

from difflib import SequenceMatcher
from itertools import permutations

from .models import CourseAnalysis, CourseSlot, GroupMatch, WordCourseSection, WordGroup
from .normalization import age_bounds, canonical_course_name, normalize_for_match
from .word_reader import best_word_match


def group_pdf_slots(slots: list[CourseSlot]) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = {}
    for idx, slot in enumerate(slots):
        key = normalize_for_match(canonical_course_name(slot.course_name))
        grouped.setdefault(key, []).append(idx)
    return grouped


def _age_score(old_age: str, new_age: str) -> tuple[int, bool]:
    """Valuta la continuità della fascia d'età.

    Per i corsi bambini/ragazzi l'avanzamento di un anno è un segnale forte
    (7 -> 8, 10-12 -> 11-13). Una fascia che invece torna indietro viene
    penalizzata: non deve essere associata solo perché giorno/orario coincidono.
    """
    old_b = age_bounds(old_age)
    new_b = age_bounds(new_age)
    if not old_b or not new_b:
        return 0, False
    if old_b == new_b:
        return 34, False
    delta = (new_b[0] - old_b[0], new_b[1] - old_b[1])
    if delta == (1, 1):
        return 32, True
    # Regressione di livello: segnale contrario molto forte.
    if new_b[0] < old_b[0] or new_b[1] < old_b[1]:
        return -22, True
    overlap = max(0, min(old_b[1], new_b[1]) - max(old_b[0], new_b[0]) + 1)
    if overlap:
        return 16 + min(overlap * 3, 9), True
    return 0, True


def _time_minutes(value: str) -> int | None:
    try:
        h, m = map(int, value.split("."))
        return h * 60 + m
    except Exception:
        return None


def score_group(old: WordGroup, new: CourseSlot) -> tuple[int, str, bool]:
    score = 0
    reasons: list[str] = []
    needs_confirmation = False

    if old.day and new.day and old.day.lower() == new.day.lower():
        score += 30
        reasons.append("stesso giorno")
    elif old.day and new.day:
        needs_confirmation = True

    old_start, new_start = _time_minutes(old.start_time), _time_minutes(new.start_time)
    old_end, new_end = _time_minutes(old.end_time), _time_minutes(new.end_time)
    if old_start is not None and new_start is not None:
        diff = abs(old_start - new_start)
        if diff == 0:
            score += 24
            reasons.append("stesso orario")
        elif diff <= 15:
            score += 18
            reasons.append("orario molto vicino")
            needs_confirmation = True
        elif diff <= 60:
            score += 6
            needs_confirmation = True
    if old_end is not None and new_end is not None and abs(old_end - new_end) <= 15:
        score += 8

    age_points, age_changed = _age_score(old.age_group, new.age_group)
    score += age_points
    if age_points:
        reasons.append("fascia d'età compatibile")
    if age_changed:
        needs_confirmation = True

    # Un label senza età può comunque aiutare (MATTINA, SERA, ecc.).
    if old.label_text and new.section and normalize_for_match(new.section) in normalize_for_match(old.label_text):
        score += 4

    return max(0, min(score, 100)), ", ".join(reasons) or "somiglianza debole", needs_confirmation


def match_groups(old_groups: list[WordGroup], new_slot_indexes: list[int], slots: list[CourseSlot]) -> list[GroupMatch]:
    if not old_groups:
        return [GroupMatch(None, idx, 0, "nuovo gruppo", False) for idx in new_slot_indexes]
    if not new_slot_indexes:
        return [GroupMatch(i, None, 0, "gruppo non presente nel PDF", True) for i in range(len(old_groups))]
    if len(old_groups) == 1 and len(new_slot_indexes) == 1:
        sc, reason, _confirm = score_group(old_groups[0], slots[new_slot_indexes[0]])
        return [GroupMatch(0, new_slot_indexes[0], max(sc, 70), reason or "unico gruppo del corso", False)]

    scores = [[score_group(old, slots[new_idx]) for new_idx in new_slot_indexes] for old in old_groups]
    n_old, n_new = len(old_groups), len(new_slot_indexes)
    best_total = -1
    best_pairs: list[tuple[int, int]] = []

    # I materiali reali hanno al massimo pochi gruppi per corso; brute force è trasparente e sufficiente.
    if n_old <= n_new:
        for perm in permutations(range(n_new), n_old):
            total = sum(scores[i][perm[i]][0] for i in range(n_old))
            if total > best_total:
                best_total = total
                best_pairs = [(i, perm[i]) for i in range(n_old)]
    else:
        for perm in permutations(range(n_old), n_new):
            total = sum(scores[perm[j]][j][0] for j in range(n_new))
            if total > best_total:
                best_total = total
                best_pairs = [(perm[j], j) for j in range(n_new)]

    result: list[GroupMatch] = []
    used_old, used_new = set(), set()
    for old_i, local_new_i in best_pairs:
        sc, reason, confirm = scores[old_i][local_new_i]
        # Una corrispondenza debole è meglio lasciarla non associata. In v0.3
        # questo evita abbinamenti forzati (es. 8-9 anni -> 7 anni) solo perché
        # giorno e orario sono simili.
        if sc < 45 and (n_old > 1 or n_new > 1):
            continue
        used_old.add(old_i)
        used_new.add(local_new_i)
        result.append(GroupMatch(old_i, new_slot_indexes[local_new_i], sc, reason, confirm or sc < 55))
    for i in range(n_old):
        if i not in used_old:
            result.append(GroupMatch(i, None, 0, "gruppo non presente nel PDF", True))
    for j, global_idx in enumerate(new_slot_indexes):
        if j not in used_new:
            result.append(GroupMatch(None, global_idx, 0, "nuovo gruppo", False))
    return result


def analyze_courses(slots: list[CourseSlot], sections: list[WordCourseSection], course_threshold: int = 65) -> list[CourseAnalysis]:
    pdf_groups = group_pdf_slots(slots)
    used_sections: set[int] = set()
    analyses: list[CourseAnalysis] = []

    for key, slot_indexes in pdf_groups.items():
        display_name = slots[slot_indexes[0]].course_name
        section, score = best_word_match(canonical_course_name(display_name), sections)
        section_index = sections.index(section) if section in sections else None
        if section and score >= course_threshold and section_index not in used_sections:
            used_sections.add(section_index)
            matches = match_groups(section.groups, slot_indexes, slots)
            warnings: list[str] = []
            for idx in slot_indexes:
                if slots[idx].warning:
                    warnings.append(f"{slots[idx].source_title}: {slots[idx].warning}")
            for gm in matches:
                if gm.old_group_index is not None and gm.new_slot_index is not None:
                    old = section.groups[gm.old_group_index]
                    new = slots[gm.new_slot_index]
                    if old.lesson_duration_minutes and new.computed_duration_minutes and old.lesson_duration_minutes != new.computed_duration_minutes:
                        warnings.append(
                            f"Durata lezione cambiata: '{old.duration_text}' ma il nuovo orario dura {new.computed_duration_minutes} minuti."
                        )
                    if old.calendar_texts and new.activation_date:
                        warnings.append("La scheda contiene un calendario dettagliato: il PDF indica solo la data di partenza.")
            status = "esistente"
            if any(m.old_group_index is None for m in matches):
                status = "esistente + nuovo gruppo"
            if any(m.new_slot_index is None for m in matches):
                status = "esistente + gruppo assente"
            analyses.append(CourseAnalysis(
                key=key, pdf_name=display_name, word_title=section.title,
                word_section_index=section_index, course_score=score, status=status,
                pdf_slot_indexes=slot_indexes, group_matches=matches, warnings=warnings,
            ))
        else:
            warnings = [slots[i].warning for i in slot_indexes if slots[i].warning]
            analyses.append(CourseAnalysis(
                key=key, pdf_name=display_name, word_title=section.title if section else "",
                word_section_index=None, course_score=score, status="nuovo corso",
                pdf_slot_indexes=slot_indexes, warnings=warnings,
            ))

    # Schede del Word non utilizzate: non compaiono nel PDF oppure sono possibili rinomine.
    for idx, section in enumerate(sections):
        if idx in used_sections:
            continue
        best_pdf_key = ""
        best_score = 0
        for key, slot_indexes in pdf_groups.items():
            title = canonical_course_name(slots[slot_indexes[0]].course_name)
            score = int(round(SequenceMatcher(None, section.normalized_title, normalize_for_match(title)).ratio() * 100))
            if score > best_score:
                best_score, best_pdf_key = score, key
        analyses.append(CourseAnalysis(
            key=f"WORD::{idx}", pdf_name="", word_title=section.title,
            word_section_index=idx, course_score=best_score,
            status="non presente nel PDF", warnings=[f"Possibile continuità con un corso del PDF (somiglianza {best_score}%)"] if best_score >= 55 else [],
        ))

    return analyses


def validate_slot(slot: CourseSlot) -> list[str]:
    issues: list[str] = []
    if not slot.course_name:
        issues.append("Titolo corso mancante")
    start = _time_minutes(slot.start_time)
    end = _time_minutes(slot.end_time)
    if start is None or end is None:
        issues.append("Orario non leggibile")
    elif end <= start:
        issues.append("L'orario finale deve essere successivo all'orario iniziale")
    if slot.activation_date:
        days = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
        actual = days[slot.activation_date.weekday()]
        if actual != slot.day.lower():
            issues.append(f"La data {slot.activation_date.isoformat()} cade di {actual}, ma il corso è sotto {slot.day}")
    elif not slot.activation_raw:
        issues.append("Data di attivazione mancante")
    return issues
