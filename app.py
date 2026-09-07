from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from src.analysis_engine import analyze_courses, validate_slot
from src.pdf_parser import parse_schedule_pdf
from src.report_generator import generate_control_report
from src.word_generator import generate_updated_word_v03
from src.word_reader import read_word_course_sections

st.set_page_config(page_title="La Tartuca - Aggiornamento corsi", page_icon="🐢", layout="wide")

st.title("🐢 La Tartuca - Aggiornamento corsi")
st.caption("Versione online v0.3 - confronto PDF/Word, casi dubbi, controlli e generazione Word + report.")

with st.sidebar:
    st.header("Impostazioni")
    fallback_year = st.number_input(
        "Anno (solo se non leggibile nel PDF)", min_value=2020, max_value=2100, value=datetime.now().year
    )
    course_threshold = st.slider("Soglia associazione automatica corso", 50, 95, 65)
    st.info(
        "L'app non modifica il sito e non invia file al webmaster. "
        "I documenti caricati vengono elaborati nella sessione corrente e non vengono salvati dall'app in un archivio permanente. "
        "Le decisioni dubbie restano sempre alla responsabile."
    )
    st.caption(
        "Ogni browser/PC ha una sessione separata: per continuare una lavorazione iniziata su un altro dispositivo "
        "occorre ricaricare PDF e Word e ripetere le eventuali scelte non ancora esportate."
    )
    if st.button("🧹 Nuova lavorazione / azzera sessione", use_container_width=True):
        st.session_state.clear()
        st.rerun()

st.header("1. Carica i due documenti")
left, right = st.columns(2)
with left:
    pdf_file = st.file_uploader("PDF del trimestre attuale", type=["pdf"])
with right:
    word_file = st.file_uploader("Word di base (situazione precedente)", type=["docx"])

if pdf_file is None or word_file is None:
    st.warning("Per iniziare servono sia il PDF del trimestre attuale sia il Word di base.")
    st.stop()

try:
    slots = parse_schedule_pdf(pdf_file.getvalue(), fallback_year=int(fallback_year))
    word_sections = read_word_course_sections(word_file.getvalue())
except Exception as exc:
    st.error(f"Impossibile leggere i documenti: {exc}")
    st.stop()

# ----- controllo/correzione dati PDF -----
rows = []
for idx, slot in enumerate(slots, start=1):
    rows.append({
        "ID": idx,
        "Corso": slot.course_name,
        "Titolo nel PDF": slot.source_title,
        "Sezione calendario": slot.section,
        "Giorno": slot.day,
        "Dalle": slot.start_time,
        "Alle": slot.end_time,
        "Età": slot.age_group,
        "Data attivazione": slot.activation_date.isoformat() if slot.activation_date else slot.activation_raw,
    })

df = pd.DataFrame(rows)
with st.expander("Controlla i dati estratti dal PDF", expanded=False):
    st.write("Correggi solo eventuali letture errate. Le modifiche valgono per questa sessione.")
    edited_df = st.data_editor(
        df, hide_index=True, use_container_width=True,
        disabled=["ID", "Titolo nel PDF"], num_rows="fixed", key="courses_editor_v03"
    )
else_df = df

# Streamlit non espone direttamente il valore dell'editor fuori dal blocco se non eseguito diversamente:
try:
    edited_df
except NameError:
    edited_df = df

effective_slots = deepcopy(slots)
for row in edited_df.to_dict(orient="records"):
    slot = effective_slots[int(row["ID"]) - 1]
    slot.course_name = str(row["Corso"]).strip()
    slot.section = str(row["Sezione calendario"]).strip()
    slot.day = str(row["Giorno"]).strip().lower()
    slot.start_time = str(row["Dalle"]).strip()
    slot.end_time = str(row["Alle"]).strip()
    slot.age_group = "" if pd.isna(row["Età"]) else str(row["Età"]).strip()
    raw = str(row["Data attivazione"]).strip()
    try:
        slot.activation_date = date.fromisoformat(raw)
        slot.activation_raw = raw
    except ValueError:
        slot.activation_date = None
        slot.activation_raw = raw

blocking_errors: list[str] = []
for idx, slot in enumerate(effective_slots, start=1):
    for issue in validate_slot(slot):
        blocking_errors.append(f"Riga {idx} - {slot.source_title or slot.course_name}: {issue}")

analyses = analyze_courses(effective_slots, word_sections, course_threshold=int(course_threshold))

st.header("2. Risultato del confronto")
summary_rows = []
for a in analyses:
    summary_rows.append({
        "PDF": a.pdf_name or "-",
        "Word": a.word_title or "-",
        "Esito": a.status,
        "Punteggio": a.course_score,
        "Avvisi": " | ".join(a.warnings),
    })
summary_df = pd.DataFrame(summary_rows)
st.dataframe(summary_df, hide_index=True, use_container_width=True)

counts = summary_df["Esito"].value_counts().to_dict() if not summary_df.empty else {}
c1, c2, c3, c4 = st.columns(4)
c1.metric("Schede Word", len(word_sections))
c2.metric("Celle nel PDF", len(effective_slots))
c3.metric("Corsi nuovi", counts.get("nuovo corso", 0))
c4.metric("Errori PDF", len(blocking_errors))

if blocking_errors:
    st.error("Ci sono errori bloccanti nel PDF. Correggili nella tabella prima di generare il Word.")
    for item in blocking_errors:
        st.write(f"❌ {item}")

# Tutte le decisioni dell'utente vengono raccolte qui.
decisions: dict = {}
unresolved: list[str] = []
all_warnings: list[str] = []
for a in analyses:
    all_warnings.extend([f"{a.pdf_name or a.word_title}: {w}" for w in a.warnings])


def _old_group_label(group) -> str:
    label = group.label_text or group.frequency_text or f"Gruppo {group.index + 1}"
    timing = " ".join(x for x in [group.day, f"{group.start_time}-{group.end_time}" if group.start_time else ""] if x)
    return f"{label} | {timing}" if timing else label


def _new_slot_label(slot) -> str:
    label = slot.age_group or slot.source_title or slot.course_name
    return f"{label} | {slot.day} {slot.start_time}-{slot.end_time}"


def _proposal_for_new_slot(analysis, new_slot_idx):
    for gm in analysis.group_matches:
        if gm.new_slot_index == new_slot_idx:
            if gm.old_group_index is None:
                return "NEW", gm
            return str(gm.old_group_index), gm
    return "NEW", None


def _course_needs_resolution(analysis) -> bool:
    if analysis.word_section_index is None:
        return False
    if any(gm.needs_confirmation for gm in analysis.group_matches):
        return True
    if any(gm.old_group_index is None or gm.new_slot_index is None for gm in analysis.group_matches):
        return True
    return False


def _effective_matches(analysis):
    """Restituisce le associazioni effettive dopo le scelte della responsabile.

    Se il corso non richiede una sistemazione manuale usa le proposte automatiche.
    Per i corsi aperti nella maschera v0.3, ogni nuovo gruppo ha una provenienza
    esplicita: vecchio gruppo, nuovo gruppo o caso speciale.
    """
    if analysis.word_section_index is None:
        return []
    if not _course_needs_resolution(analysis):
        return list(analysis.group_matches)
    from src.models import GroupMatch
    section = word_sections[analysis.word_section_index]
    out = []
    used_old = set()
    for slot_idx in analysis.pdf_slot_indexes:
        value = decisions.get(f"mapping::{analysis.word_section_index}::{slot_idx}", "")
        if value == "NEW":
            out.append(GroupMatch(None, slot_idx, 0, "nuovo gruppo", False))
        elif value == "SPECIAL" or value == "":
            continue
        else:
            try:
                old_idx = int(value)
            except Exception:
                continue
            used_old.add(old_idx)
            score = 0
            reason = "associazione scelta dalla responsabile"
            for gm in analysis.group_matches:
                if gm.old_group_index == old_idx and gm.new_slot_index == slot_idx:
                    score, reason = gm.score, gm.reason
                    break
            out.append(GroupMatch(old_idx, slot_idx, score, reason, False))
    for old_idx in range(len(section.groups)):
        if old_idx not in used_old:
            out.append(GroupMatch(old_idx, None, 0, "gruppo precedente non associato", True))
    return out


st.header("3. Risolvi solo i casi che richiedono una decisione")
st.caption(
    "Le modifiche certe vengono applicate automaticamente. Per i corsi con più gruppi o livelli, "
    "l'app propone una sistemazione complessiva: puoi correggerla senza entrare in un ciclo di conferme."
)

# --- v0.3: sistemazione globale dei gruppi all'interno di ciascun corso ---
for a in analyses:
    if not _course_needs_resolution(a):
        continue
    section = word_sections[a.word_section_index]
    sec_idx = a.word_section_index
    with st.expander(f"🧩 Sistemazione gruppi - {section.title}", expanded=True):
        st.write(
            "Per ogni gruppo del **nuovo PDF**, scegli da quale gruppo del vecchio Word deriva. "
            "Se non deriva da nessuno, scegli **NUOVO GRUPPO**."
        )
        st.caption(
            "Un vecchio gruppo può essere usato una sola volta. Se resta senza destinazione, "
            "più sotto potrai indicare che non parte, che è stato dimenticato o che è confluito in un altro gruppo."
        )

        # Prima calcoliamo le scelte già presenti nello stato, così possiamo nascondere
        # negli altri menu i vecchi gruppi già usati.
        mapping_keys = {slot_idx: f"mapping::{sec_idx}::{slot_idx}" for slot_idx in a.pdf_slot_indexes}
        selected_by_slot = {}
        for slot_idx, key in mapping_keys.items():
            if key in st.session_state:
                selected_by_slot[slot_idx] = st.session_state[key]

        for slot_idx in a.pdf_slot_indexes:
            slot = effective_slots[slot_idx]
            key = mapping_keys[slot_idx]
            proposed, proposal_gm = _proposal_for_new_slot(a, slot_idx)

            already_used = {
                str(v) for other_slot, v in selected_by_slot.items()
                if other_slot != slot_idx and str(v).isdigit()
            }
            current = str(st.session_state.get(key, proposed))
            choices = []
            for old_idx, old_group in enumerate(section.groups):
                if str(old_idx) in already_used and str(old_idx) != current:
                    continue
                choices.append(str(old_idx))
            choices += ["NEW", "SPECIAL"]
            if current not in choices:
                choices.insert(0, current)

            labels = {str(i): f"Dal vecchio Word: {_old_group_label(g)}" for i, g in enumerate(section.groups)}
            labels["NEW"] = "NUOVO GRUPPO - non deriva da un gruppo precedente"
            labels["SPECIAL"] = "CASO SPECIALE / NON SO - richiede una decisione prima di procedere"

            st.markdown(f"**Nuovo PDF:** {_new_slot_label(slot)}")
            if proposal_gm is not None:
                if proposal_gm.old_group_index is not None:
                    old = section.groups[proposal_gm.old_group_index]
                    st.caption(
                        f"Proposta app: {_old_group_label(old)} · {proposal_gm.reason} · punteggio {proposal_gm.score}"
                    )
                else:
                    st.caption("Proposta app: nuovo gruppo")

            value = st.selectbox(
                "Origine di questo gruppo",
                choices,
                index=choices.index(current) if current in choices else 0,
                format_func=lambda x, labels=labels: labels.get(str(x), str(x)),
                key=key,
            )
            decisions[key] = value
            selected_by_slot[slot_idx] = value
            if value == "SPECIAL":
                unresolved.append(f"{section.title} - {_new_slot_label(slot)}: risolvere il caso speciale")
            st.divider()

        # Difesa aggiuntiva: uno stesso vecchio gruppo non può alimentare due gruppi nuovi.
        chosen_old = [str(v) for v in selected_by_slot.values() if str(v).isdigit()]
        duplicates = sorted({x for x in chosen_old if chosen_old.count(x) > 1})
        for dup in duplicates:
            unresolved.append(f"{section.title}: lo stesso vecchio gruppo è stato associato a più gruppi nuovi")

        used_old = {int(v) for v in selected_by_slot.values() if str(v).isdigit()}
        unassigned_old = [i for i in range(len(section.groups)) if i not in used_old]
        if unassigned_old:
            st.markdown("#### Vecchi gruppi rimasti senza destinazione")
            for old_idx in unassigned_old:
                old = section.groups[old_idx]
                label = _old_group_label(old)
                st.write(f"**Prima:** {label}")
                key = f"oldgroup::{sec_idx}::{old_idx}"
                action_label = st.selectbox(
                    "Che cosa è successo a questo gruppo?",
                    [
                        "Seleziona...",
                        "Non parte questo trimestre",
                        "È stato dimenticato nel PDF",
                        "È confluito in un altro gruppo",
                        "Altro / caso particolare",
                    ],
                    key=f"ui::{key}",
                )
                mapping = {
                    "Non parte questo trimestre": "non_parte",
                    "È stato dimenticato nel PDF": "dimenticato",
                    "È confluito in un altro gruppo": "confluito",
                    "Altro / caso particolare": "altro",
                }
                decisions[key] = mapping.get(action_label, "")
                if decisions[key] == "dimenticato":
                    unresolved.append(f"{section.title} - {label}: correggere il PDF perché il gruppo è stato dimenticato")
                elif decisions[key] == "confluito":
                    candidates = [str(i) for i in a.pdf_slot_indexes]
                    target_key = f"oldgroup_target::{sec_idx}::{old_idx}"
                    target = st.selectbox(
                        "In quale gruppo del nuovo PDF è confluito?",
                        [""] + candidates,
                        format_func=lambda x: "Seleziona..." if x == "" else _new_slot_label(effective_slots[int(x)]),
                        key=f"ui::{target_key}",
                    )
                    decisions[target_key] = target
                    if not target:
                        unresolved.append(f"{section.title} - {label}: indicare il gruppo in cui è confluito")
                elif decisions[key] == "altro":
                    note_key = f"oldgroup_note::{sec_idx}::{old_idx}"
                    note = st.text_input("Scrivi l'istruzione/note da riportare", key=f"ui::{note_key}")
                    decisions[note_key] = note
                    if not note.strip():
                        unresolved.append(f"{section.title} - {label}: descrivere il caso particolare")
                elif not decisions[key]:
                    unresolved.append(f"{section.title} - {label}: decidere cosa fare con il vecchio gruppo")

# --- nuovi gruppi scelti esplicitamente nella sistemazione v0.3 ---
for a in analyses:
    if a.word_section_index is None or not _course_needs_resolution(a):
        continue
    section = word_sections[a.word_section_index]
    sec_idx = a.word_section_index
    first_group = section.groups[0] if section.groups else None
    for slot_idx in a.pdf_slot_indexes:
        if decisions.get(f"mapping::{sec_idx}::{slot_idx}") != "NEW":
            continue
        slot = effective_slots[slot_idx]
        with st.expander(f"🟢 Completa il nuovo gruppo - {section.title}: {slot.age_group or slot.source_title}", expanded=False):
            st.write(f"Dal PDF: **{slot.day} {slot.start_time}-{slot.end_time}**, partenza **{slot.activation_raw}**")
            prefix = f"newgroup::{sec_idx}::{slot_idx}"
            data = {
                "label": st.text_input("Nome del gruppo", value=f"GRUPPO {slot.age_group.upper()}" if slot.age_group else "", key=f"ui::{prefix}::label"),
                "sede": st.text_input("Sede (se serve specificarla)", value="", key=f"ui::{prefix}::sede"),
                "durata": st.text_input("Durata", value=(first_group.duration_text.replace("Durata:", "").strip() if first_group and first_group.duration_text else ""), key=f"ui::{prefix}::durata"),
                "quota": st.text_input("Quota", value=(first_group.quota_text.replace("Quota:", "").strip() if first_group and first_group.quota_text else ""), key=f"ui::{prefix}::quota"),
                "insegnante": st.text_input("Insegnante", value=(first_group.teacher_text.split(":", 1)[-1].strip() if first_group and first_group.teacher_text else ""), key=f"ui::{prefix}::insegnante"),
                "calendario": st.text_input("Calendario dettagliato (solo se necessario)", value="", key=f"ui::{prefix}::calendario"),
            }
            decisions[prefix] = data
            if not data["durata"] or not data["quota"]:
                unresolved.append(f"Completare durata e quota del nuovo gruppo {section.title} - {slot.age_group or slot.source_title}")

# --- campi che il PDF non può aggiornare da solo: durata/calendario ---
# Usa le associazioni effettive scelte nella nuova schermata, non le vecchie proposte.
for a in analyses:
    if a.word_section_index is None:
        continue
    section = word_sections[a.word_section_index]
    for gm in _effective_matches(a):
        if gm.old_group_index is None or gm.new_slot_index is None:
            continue
        old = section.groups[gm.old_group_index]
        new = effective_slots[gm.new_slot_index]
        if old.lesson_duration_minutes and new.computed_duration_minutes and old.lesson_duration_minutes != new.computed_duration_minutes:
            with st.expander(f"🟡 Durata da verificare - {section.title}", expanded=False):
                st.write(f"Nel Word: **{old.duration_text}**")
                st.write(f"Dal nuovo orario risultano **{new.computed_duration_minutes} minuti** per lezione.")
                key = f"duration::{a.word_section_index}::{gm.old_group_index}"
                value = st.text_input("Scrivi il nuovo testo della durata", value="", key=f"ui::{key}")
                decisions[key] = value
                if not value:
                    unresolved.append(f"Aggiornare la durata di {section.title}")
        if old.calendar_texts and new.activation_date:
            with st.expander(f"🟡 Calendario dettagliato - {section.title}", expanded=False):
                st.write("Il Word precedente contiene un calendario dettagliato che non può essere ricostruito dal solo PDF.")
                st.write("**Prima:** " + " / ".join(old.calendar_texts))
                key = f"calendar::{a.word_section_index}::{gm.old_group_index}"
                value = st.text_input("Inserisci il nuovo calendario completo", value="", key=f"ui::{key}")
                decisions[key] = value
                if not value:
                    unresolved.append(f"Inserire il calendario dettagliato aggiornato di {section.title}")

# --- corsi completamente nuovi ---
for a in analyses:
    if a.status != "nuovo corso":
        continue
    with st.expander(f"🆕 Nuovo corso - {a.pdf_name}", expanded=False):
        slots_for_course = [effective_slots[i] for i in a.pdf_slot_indexes]
        for slot in slots_for_course:
            st.write(f"• {slot.source_title}: {slot.day} {slot.start_time}-{slot.end_time}, {slot.activation_raw}")
        prefix = f"newcourse::{a.key}"
        data = {
            "titolo": st.text_input("Titolo da usare nel Word", value=a.pdf_name, key=f"ui::{prefix}::titolo"),
            "sezione": st.text_input("Sezione della pagina Tutti i corsi", value="", key=f"ui::{prefix}::sezione"),
            "descrizione": st.text_area("Descrizione del corso", value="", key=f"ui::{prefix}::descrizione", height=120),
            "sede": st.text_input("Sede", value="via Varesina, 19", key=f"ui::{prefix}::sede"),
            "durata": st.text_input("Durata", value="", key=f"ui::{prefix}::durata"),
            "quota": st.text_input("Quota", value="", key=f"ui::{prefix}::quota"),
            "insegnante": st.text_input("Insegnante / conduttore", value="", key=f"ui::{prefix}::insegnante"),
            "calendario": st.text_input("Calendario dettagliato (se serve)", value="", key=f"ui::{prefix}::calendario"),
            "url": st.text_input("URL (facoltativo: normalmente lo creerà il webmaster)", value="", key=f"ui::{prefix}::url"),
        }
        decisions[prefix] = data
        required = ["titolo", "sezione", "descrizione", "sede", "durata", "quota", "insegnante"]
        missing = [name for name in required if not str(data.get(name, "")).strip()]
        if missing:
            unresolved.append(f"Completare il nuovo corso {a.pdf_name}: mancano {', '.join(missing)}")

# --- intere schede Word non presenti nel PDF ---
new_course_names = [a.pdf_name for a in analyses if a.status == "nuovo corso"]
for a in analyses:
    if a.status != "non presente nel PDF" or a.word_section_index is None:
        continue
    with st.expander(f"🟠 Corso del Word non presente nel PDF - {a.word_title}", expanded=False):
        key = f"oldcourse::{a.word_section_index}"
        action = st.selectbox(
            "Come va gestito?",
            ["Seleziona...", "Non parte questo trimestre", "È stato dimenticato nel PDF", "Ha cambiato nome/livello"],
            key=f"ui::{key}",
        )
        mapping = {
            "Non parte questo trimestre": "non_parte",
            "È stato dimenticato nel PDF": "dimenticato",
            "Ha cambiato nome/livello": "rinomina",
        }
        decisions[key] = mapping.get(action, "")
        if decisions[key] == "rinomina":
            target = st.selectbox("Nuovo nome/corso corrispondente", [""] + new_course_names, key=f"ui::target::{key}")
            decisions[f"oldcourse_target::{a.word_section_index}"] = target
            if not target:
                unresolved.append(f"Indicare il nuovo corso corrispondente a {a.word_title}")
        elif decisions[key] == "dimenticato":
            unresolved.append(f"{a.word_title}: indicato come dimenticato nel PDF; correggere il PDF prima di procedere")
        elif not decisions[key]:
            unresolved.append(f"Decidere cosa fare con il corso {a.word_title}")

# Avvisi non bloccanti mostrati alla responsabile.
if all_warnings:
    with st.expander(f"Avvisi automatici ({len(all_warnings)})", expanded=False):
        for warning in all_warnings:
            st.write(f"⚠️ {warning}")

st.header("4. Controllo finale e generazione")
if unresolved:
    st.warning(f"Restano {len(unresolved)} decisioni/informazioni da completare.")
    for item in unresolved:
        st.write(f"• {item}")
else:
    st.success("Tutti i casi dubbi sono stati risolti.")

can_generate = not blocking_errors and not unresolved

if can_generate:
    try:
        output_docx = generate_updated_word_v03(
            word_file.getvalue(), effective_slots, word_sections, analyses, decisions
        )
        report_docx = generate_control_report(analyses, decisions, blocking_errors, all_warnings)
        st.download_button(
            "Scarica Word operativo",
            output_docx,
            "La_Tartuca_Word_aggiornato_v03.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )
        st.download_button(
            "Scarica report di controllo",
            report_docx,
            "La_Tartuca_Report_controllo_v03.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )
    except Exception as exc:
        st.error(f"Errore durante la generazione: {exc}")
else:
    st.info("I pulsanti di generazione compariranno quando non resteranno errori bloccanti o decisioni aperte.")

with st.expander("Cosa fa e cosa non fa la v0.3"):
    st.markdown(
        """
**Fa:**
- legge il PDF vettoriale e il Word di base;
- ignora l'eventuale vecchia parte generale prima della prima scheda corso;
- riconosce corsi e gruppi, compresi più orari nella stessa scheda;
- aggiorna giorno, orario, attivazione e fasce d'età associate;
- evidenzia in giallo le modifiche;
- fa compilare i dati non deducibili dal PDF;
- ricostruisce la parte generale “Tutti i corsi”;
- genera Word operativo e report sintetico.

**Non fa:**
- non modifica il sito;
- non inventa descrizioni, quote, insegnanti o calendari;
- non decide da sola nei casi di rinomina/livello ambiguo;
- non genera il Word finché rimangono errori bloccanti o casi dichiarati “dimenticati nel PDF”.
        """
    )
