from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Optional


@dataclass
class CourseSlot:
    source_title: str
    course_name: str
    day: str
    start_time: str
    end_time: str
    activation_raw: str
    activation_date: Optional[date]
    section: str
    age_group: str = ""
    duration_minutes: Optional[int] = None
    page_number: int = 1
    x_center: float = 0.0
    y_top: float = 0.0
    warning: str = ""

    @property
    def computed_duration_minutes(self) -> Optional[int]:
        try:
            sh, sm = map(int, self.start_time.split("."))
            eh, em = map(int, self.end_time.split("."))
            return (eh * 60 + em) - (sh * 60 + sm)
        except Exception:
            return None

    def to_dict(self) -> dict:
        data = asdict(self)
        if self.activation_date:
            data["activation_date"] = self.activation_date.isoformat()
        data["computed_duration_minutes"] = self.computed_duration_minutes
        return data


@dataclass
class WordGroup:
    index: int
    label_text: str = ""
    label_paragraph_index: Optional[int] = None
    frequency_text: str = ""
    frequency_paragraph_index: Optional[int] = None
    duration_text: str = ""
    duration_paragraph_index: Optional[int] = None
    quota_text: str = ""
    quota_paragraph_index: Optional[int] = None
    teacher_text: str = ""
    teacher_paragraph_index: Optional[int] = None
    activation_text: str = ""
    activation_paragraph_index: Optional[int] = None
    calendar_texts: list[str] = field(default_factory=list)
    calendar_paragraph_indexes: list[int] = field(default_factory=list)
    day: str = ""
    start_time: str = ""
    end_time: str = ""
    age_group: str = ""
    lesson_duration_minutes: Optional[int] = None


@dataclass
class WordCourseSection:
    url: str
    title: str
    paragraph_start: int
    paragraph_end: int
    frequency_text: str = ""
    activation_text: str = ""
    normalized_title: str = ""
    groups: list[WordGroup] = field(default_factory=list)
    description_paragraphs: list[str] = field(default_factory=list)
    site_text: str = ""


@dataclass
class GroupMatch:
    old_group_index: Optional[int]
    new_slot_index: Optional[int]
    score: int
    reason: str
    needs_confirmation: bool = False


@dataclass
class CourseAnalysis:
    key: str
    pdf_name: str = ""
    word_title: str = ""
    word_section_index: Optional[int] = None
    course_score: int = 0
    status: str = ""
    pdf_slot_indexes: list[int] = field(default_factory=list)
    group_matches: list[GroupMatch] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
