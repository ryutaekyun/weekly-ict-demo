"""카드뉴스 템플릿 4종의 요소 스키마(어떤 카드에 어떤 편집 요소가 있는가)와 기본 설정.

템플릿은 색만 다른 것이 아니라 정보 전달 목적과 레이아웃이 다르다.
  A 핵심 정책·기술 이슈 요약형 — 핵심 내용 3박스 + 시사점
  B 정책 변화·추진 일정형      — 날짜별 타임라인(발표·의견수렴 마감·확정·시행 구분)
  C 주요국 정책·기술 비교형    — 국가별 비교표 + 차이·공통점·국내 시사점
  D 핵심 수치·산업 영향 시각화형 — 핵심 수치 + 막대 그래프(검증된 자료가 있을 때만) + 의미·메시지
레이아웃(좌표) 자체는 card_news_scene.py에 있다.
"""

from dataclasses import dataclass, field

DEFAULT_WIDTH_CM = 7.0
DEFAULT_HEIGHT_CM = 15.62  # 작업용 기본 규격 — IITP 공식 발간 규격으로 확인된 값이 아님

STAGE_KINDS = {
    "announce": "발표", "comment": "의견수렴 마감", "final": "확정·공고", "effective": "시행", "compliance": "준수 시한", "other": "기타",
}

COUNTRY_SLOTS = 3
STAGE_SLOTS = 5


@dataclass
class ElementSpec:
    key: str
    label: str
    type: str = "text"          # text / choice / chart
    max_chars: int = 80
    evidence: bool = False      # 사실·수치·일정·정책명 등 → 원문 근거 연결 대상
    required: bool = False
    hint: str = ""
    options: dict[str, str] = field(default_factory=dict)
    multiline: bool = True

    def as_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label, "type": self.type, "max_chars": self.max_chars,
            "evidence_required": self.evidence, "required": self.required, "hint": self.hint, "options": self.options,
            "multiline": self.multiline,
        }


TEMPLATES: dict[str, dict] = {
    "A": {"name": "A. 핵심 정책·기술 이슈 요약형", "purpose": "핵심 주제와 핵심 내용 3가지, 시사점을 한눈에 전달"},
    "B": {"name": "B. 정책 변화·추진 일정형", "purpose": "발표·확정·시행 등 날짜별 단계를 타임라인으로 전달"},
    "C": {"name": "C. 주요국 정책·기술 비교형", "purpose": "국가별 정책 방향을 표로 비교하고 차이·시사점 정리"},
    "D": {"name": "D. 핵심 수치·산업 영향 시각화형", "purpose": "검증된 핵심 수치와 그래프, 산업적 의미 전달"},
}

DEFAULT_TEMPLATE_CONFIG: dict[str, dict] = {
    "A": {"accent": "5CAD8E", "accent_soft": "E6F4EE", "accent_dark": "276B53", "accent_light": "8FD1B6"},
    "B": {"accent": "6C8EBF", "accent_soft": "E4EEF9", "accent_dark": "3F6BA3", "accent_light": "A9C4EA"},
    "C": {"accent": "D99A6C", "accent_soft": "FBEEE3", "accent_dark": "93501F", "accent_light": "F0C3A0"},
    "D": {"accent": "5FB3B3", "accent_soft": "E2F3F3", "accent_dark": "2A7F7F", "accent_light": "9ADBDB"},
}

BASE_CONFIG = {
    "font": "맑은 고딕",
    "navy": "1B2A4A", "gray": "6E7685", "gray_text": "566070", "green": "5CAD8E", "white": "FFFFFF",
    "bg": "F4F7FB", "navy_soft": "DCE4F0", "border": "D6DEEA",
    "margin_cm": 0.55, "min_font_pt": 7.0,
    "width_cm": DEFAULT_WIDTH_CM, "height_cm": DEFAULT_HEIGHT_CM,
}


def template_config(key: str, override: dict | None = None) -> dict:
    cfg = dict(BASE_CONFIG)
    cfg.update(DEFAULT_TEMPLATE_CONFIG[key])
    if override:
        cfg.update(override)
    return cfg


def _cover() -> list[ElementSpec]:
    return [
        ElementSpec("badge", "분류 배지", max_chars=16, multiline=False, hint="예: 주간 AI·ICT 동향"),
        ElementSpec("title", "표지 제목", max_chars=60, required=True),
        ElementSpec("subtitle", "부제", max_chars=70),
        ElementSpec("source", "출처", max_chars=70, hint="발표 기관·자료명"),
    ]


def _closing(follow_label: str = "후속 과제") -> list[ElementSpec]:
    return [
        ElementSpec("message", "핵심 메시지", max_chars=60, required=True, evidence=True),
        ElementSpec("follow_up", follow_label, max_chars=80),
        ElementSpec("source", "출처", max_chars=80, required=True),
    ]


def element_specs(template_key: str, kind: str) -> list[ElementSpec]:
    if kind == "cover":
        return _cover()
    if kind == "closing":
        return _closing({"A": "시사점·후속 과제", "B": "향후 일정", "C": "국내 시사점", "D": "산업적 의미"}[template_key])
    # body
    head = [ElementSpec("heading", "카드 제목", max_chars=30, required=True, multiline=False)]
    if template_key == "A":
        return head + [
            ElementSpec(f"content_{i}", f"핵심 내용 {i}", max_chars=90, required=(i == 1), evidence=True) for i in (1, 2, 3)
        ] + [
            ElementSpec("implication", "시사점", max_chars=70),
            ElementSpec("source", "출처", max_chars=70, required=True),
        ]
    if template_key == "B":
        specs = list(head)
        for i in range(1, STAGE_SLOTS + 1):
            specs += [
                ElementSpec(f"stage_{i}_kind", f"{i}단계 구분", type="choice", options=STAGE_KINDS),
                ElementSpec(f"stage_{i}_date", f"{i}단계 날짜", max_chars=24, evidence=True, required=(i == 1), multiline=False,
                            hint="원문에서 확인된 날짜만 입력"),
                ElementSpec(f"stage_{i}_text", f"{i}단계 내용", max_chars=60, evidence=True, required=(i == 1)),
            ]
        return specs + [ElementSpec("source", "출처", max_chars=70, required=True)]
    if template_key == "C":
        specs = head + [ElementSpec("topic", "비교 주제", max_chars=40, multiline=False)]
        for i in range(1, COUNTRY_SLOTS + 1):
            specs += [
                ElementSpec(f"country_{i}_name", f"국가 {i}", max_chars=10, multiline=False, required=(i <= 2)),
                ElementSpec(f"country_{i}_policy", f"국가 {i} 핵심 정책 방향", max_chars=70, evidence=True, required=(i <= 2),
                            hint="확인된 자료가 없으면 비워 두고 '추가 조사 필요'로 표시"),
            ]
        return specs + [
            ElementSpec("difference", "주요 차이", max_chars=70),
            ElementSpec("common", "공통점·쟁점", max_chars=70),
            ElementSpec("implication", "국내 시사점 검토", max_chars=70, hint="근거 없이 단정하지 않음"),
            ElementSpec("source", "출처", max_chars=70, required=True),
        ]
    # D
    return head + [
        ElementSpec("stat_value", "핵심 수치", max_chars=12, evidence=True, multiline=False),
        ElementSpec("stat_unit", "단위", max_chars=8, multiline=False),
        ElementSpec("stat_label", "수치 설명", max_chars=40),
        ElementSpec("chart", "통계 그래프", type="chart", evidence=True,
                    hint="수치·단위·기준연도·비교대상·출처가 모두 있고 근거가 검증되었을 때만 그래프를 그림"),
        ElementSpec("meaning", "기술·산업적 의미", max_chars=80),
        ElementSpec("message", "핵심 메시지", max_chars=60, required=True),
        ElementSpec("source", "출처", max_chars=70, required=True),
    ]


def default_card_kinds(body_count: int = 3) -> list[str]:
    return ["cover"] + ["body"] * max(1, min(body_count, 8)) + ["closing"]


# 보고서·요약본의 문장을 카드에 순서대로 채울 때 쓰는 슬롯(근거 대상 텍스트 요소)
FILL_ORDER = {
    "A": ["content_1", "content_2", "content_3"],
    "B": ["stage_1_text", "stage_2_text", "stage_3_text", "stage_4_text", "stage_5_text"],
    "C": ["country_1_policy", "country_2_policy", "country_3_policy"],
    "D": ["meaning", "message"],
}
