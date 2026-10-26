"""카드 1장 → '장면(scene)' 변환. 장면은 좌표(cm)가 있는 도형·텍스트·표·차트 목록이며,
  - 웹 편집기 미리보기(HTML),
  - PPTX 생성(python-pptx),
  - 사전점검(글자 잘림·겹침·대비 등)
이 모두 같은 장면 데이터를 쓴다 → PPTX와 PNG(=PPTX 렌더링)와 미리보기가 같은 디자인 데이터에서 나온다.
PNG는 이 장면으로 만든 PPTX를 LibreOffice로 렌더링해서 만들며, HTML 화면 캡처로 만들지 않는다.
"""

import json
import re

from app.services.card_news_schema import STAGE_KINDS, STAGE_SLOTS, COUNTRY_SLOTS

PT_PER_CM = 28.3465
STAGE_COLORS = {
    "announce": "1B2A4A", "comment": "6E7685", "final": "2F7D62", "effective": "B5532E", "compliance": "7A5AA6", "other": "6E7685",
}
PAD_CM = 0.08


# ---------------------------------------------------------------- 텍스트 측정 ----
def _char_em(ch: str) -> float:
    o = ord(ch)
    if o >= 0x2E80 or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F:
        return 1.05  # 글꼴 대체 시 약간 넓어질 수 있어 보수적으로 추정
    if ch in (" ", " "):
        return 0.28
    if ch.isdigit():
        return 0.58
    if ch.isupper():
        return 0.68
    if ch.isalpha():
        return 0.55
    if ch in ".,:;'!|":
        return 0.3
    return 0.55


def keep_bracket_together(text: str, size_pt: float, width_cm: float, bold: bool = False) -> str:
    """문장 앞머리의 [..] 묶음(예: "[합성 테스트 데이터]")이 줄바꿈으로 쪼개지지 않도록 줄바꿈 금지 공백으로 잇는다.
    묶음이 한 줄 너비보다 길면(글자 중간에서 끊기게 되므로) 원래 공백을 그대로 둔다."""
    m = re.match(r"^(\[[^\]\n]{1,40}\])", text)
    if not m:
        return text
    inner = max(width_cm - 2 * PAD_CM, 0.1) * PT_PER_CM
    if sum(_char_em(c) for c in m.group(1)) * size_pt * (1.06 if bold else 1.0) > inner:
        return text
    return m.group(1).replace(" ", " ") + text[m.end():]


ASCII_GAP = re.compile(r"(?<=[A-Za-z0-9)])[ ](?=[A-Za-z0-9(])|(?<=No\.)[ ](?=\d)")


def keep_ascii_tokens(text: str) -> str:
    """영문 약어·번호·단위가 줄바꿈에서 쪼개지지 않게(예: 'FMVSS 305a', 'No. 305a') 영문·숫자 사이 공백을 줄바꿈 금지 공백으로 바꾼다."""
    return ASCII_GAP.sub(" ", text)


def fit_source_links(links: list[dict], size_pt: float, width_cm: float) -> tuple[list[dict], str]:
    """출처 한 줄에 들어가도록 같은 기관의 반복 표기를 줄이고, 넘치면 '외 n건'으로 줄인다(전체 목록은 슬라이드 노트·출처 파일에 있음)."""
    shown, prev_org = [], None
    for lk in links:
        label = lk["label"]
        org, _, rest = label.partition(" ")
        if prev_org == org and rest:
            label = rest  # 같은 기관이면 문서번호만
        prev_org = org
        cand = shown + [{"label": label, "url": lk["url"]}]
        if text_lines("출처: " + ", ".join(c["label"] for c in cand), size_pt, width_cm) > 1 and shown:
            break
        shown = cand
    text = "출처: " + ", ".join(c["label"] for c in shown)
    if len(shown) < len(links):
        text += f" 외 {len(links) - len(shown)}건"
    return shown, text


def text_lines(text: str, size_pt: float, width_cm: float, bold: bool = False) -> int:
    """글자 폭 휴리스틱으로 줄 수를 추정한다(한글 1em, 영문 0.55~0.68em, 굵게 +6%). 실제 렌더링 점검이 최종 판단."""
    inner = max(width_cm - 2 * PAD_CM, 0.1) * PT_PER_CM
    factor = 1.06 if bold else 1.0
    total = 0
    for para in str(text).split("\n"):
        if not para:
            total += 1
            continue
        lines, cur = 1, 0.0
        for word in re.split(r"(?<= )", para):
            w = sum(_char_em(c) for c in word) * size_pt * factor
            if cur + w <= inner:
                cur += w
                continue
            if w <= inner:
                lines += 1
                cur = w
                continue
            for c in word:  # 한 단어가 한 줄보다 길면 글자 단위로 줄바꿈
                cw = _char_em(c) * size_pt * factor
                if cur + cw > inner:
                    lines += 1
                    cur = 0.0
                cur += cw
        total += lines
    return total


def text_height_cm(text: str, size_pt: float, width_cm: float, bold: bool = False, spacing: float = 1.2) -> float:
    return text_lines(text, size_pt, width_cm, bold) * size_pt * spacing / PT_PER_CM + 2 * 0.05


def _lum(hex_color: str) -> float:
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# ---------------------------------------------------------------- 장면 빌더 ----
def validate_chart(data: dict | None) -> list[str]:
    """그래프에 필요한 수치·단위·기준연도·비교대상·출처가 갖춰졌는지. 비어 있으면 사유 목록을 돌려준다."""
    reasons = []
    if not data:
        return ["그래프 데이터가 없습니다"]
    series = [s for s in data.get("series", []) if str(s.get("label", "")).strip() and s.get("value") not in (None, "")]
    numeric = []
    for s in series:
        try:
            numeric.append(float(s["value"]))
        except (TypeError, ValueError):
            reasons.append(f"숫자가 아닌 값: {s.get('label')}")
    if len(numeric) < 2:
        reasons.append("비교할 항목이 2개 이상 필요합니다")
    for field, label in (("unit", "단위"), ("base_year", "기준연도"), ("source", "출처")):
        if not str(data.get(field, "")).strip():
            reasons.append(f"{label}가 없습니다")
    return reasons


class SceneBuilder:
    def __init__(self, width_cm: float, height_cm: float, cfg: dict, card: dict, ctx: dict):
        self.W, self.H = width_cm, height_cm
        self.sx, self.sy = width_cm / 7.0, height_cm / 15.62
        self.fs = min(self.sx, self.sy)  # 글자 크기 배율(크기를 바꾼 경우)
        self.cfg, self.card, self.ctx = cfg, card, ctx
        self.elements: dict[str, dict] = card.get("elements", {})
        self.items: list[dict] = []
        self.notes: list[str] = []
        self.export = ctx.get("for_export", False)
        self.m = cfg["margin_cm"] * self.sx
        self.cw = self.W - 2 * self.m
        self.font = cfg["font"]

    # -- 기본 도형 --
    def _x(self, v): return v * self.sx
    def _y(self, v): return v * self.sy

    def rect(self, x, y, w, h, fill=None, line=None, radius=0.0, name=None, base=True):
        if base:
            x, y, w, h = self._x(x), self._y(y), self._x(w), self._y(h)
        self.items.append({"type": "rect", "x": x, "y": y, "w": w, "h": h, "fill": fill, "line": line, "radius": radius, "name": name})

    def ellipse(self, x, y, d, fill, name=None, deco=False):
        # deco=True: 카드 가장자리에 걸쳐 잘리는 배경 장식(의도된 디자인) — 카드 이탈 점검 대상에서 제외한다
        self.items.append({"type": "ellipse", "x": self._x(x), "y": self._y(y), "w": self._x(d), "h": self._x(d), "fill": fill,
                           "name": "장식" if deco else name, "deco": deco})

    def line(self, x1, y1, x2, y2, color, width_pt=1.0):
        self.items.append({"type": "line", "x1": self._x(x1), "y1": self._y(y1), "x2": self._x(x2), "y2": self._y(y2), "color": color, "width_pt": width_pt})

    def _style(self, key):
        el = self.elements.get(key) or {}
        return el, (el.get("style") or {}), (el.get("box") or {})

    def text(self, key, x, y, w, h, size, color, bold=False, align="left", valign="top", prefix="", suffix="", spacing=1.2):
        """편집 요소(key)의 텍스트를 배치한다. 스타일·위치 덮어쓰기를 적용하고, 비어 있으면 미리보기에서만 안내 문구를 보인다."""
        el, st, box = self._style(key)
        if el.get("hidden"):
            return None
        raw = (el.get("text") or "").strip()
        placeholder = False
        if not raw:
            if self.export:
                return None
            raw, placeholder = f"[{self.ctx.get('labels', {}).get(key, key)} 입력]", True
        text = (prefix + raw + suffix) if not placeholder else raw
        links = None
        if key == "source" and not placeholder and self.card.get("links"):
            links, text = fit_source_links(self.card["links"], st.get("size", size) * (self.fs if "size" not in st else 1.0), w)
        size = st.get("size", size)
        shown_size = size * (self.fs if "size" not in st else 1.0)
        text = keep_bracket_together(text, shown_size, box.get("w", self._x(w)), st.get("bold", bold))
        text = keep_ascii_tokens(text)
        item = {
            "type": "text", "key": key, "text": text, "placeholder": placeholder,
            "x": box.get("x", self._x(x)), "y": box.get("y", self._y(y)), "w": box.get("w", self._x(w)), "h": box.get("h", self._y(h)),
            "size": round(size * (self.fs if "size" not in st else 1.0), 2), "bold": st.get("bold", bold),
            "color": "9AA3B2" if placeholder else st.get("color", color), "align": st.get("align", align), "valign": valign,
            "font": self.font, "spacing": spacing,
        }
        if links:
            item["links"] = links
        self.items.append(item)
        return item

    def label(self, x, y, w, h, text, size, color, bold=False, align="left", valign="middle", name=None):
        """고정 문구(편집 요소가 아닌 라벨·번호)."""
        self.items.append({
            "type": "text", "key": None, "text": text, "placeholder": False, "x": self._x(x), "y": self._y(y), "w": self._x(w),
            "h": self._y(h), "size": round(size * self.fs, 2), "bold": bold, "color": color, "align": align, "valign": valign,
            "font": self.font, "spacing": 1.2, "name": name,
        })

    # -- 공통 장식 --
    def footer_note(self, color):
        notes = []
        if self.ctx.get("is_pilot"):
            notes.append("시범")
        if not self.ctx.get("iitp_confirmed"):
            notes.append("내부용·IITP 미확인")
        if self.ctx.get("is_synthetic"):
            # 실제 정책·통계로 오인되지 않도록 눈에 띄는 띠로 표시한다(카드 배경과 무관하게 같은 색)
            self.rect(0, 14.9, 7.0, 0.72, fill="FFE9A8", name="합성 표시 띠")
            self.label(0.55, 14.92, 5.9, 0.68, "합성 테스트 데이터 · 실제 정책·통계 아님\n" + " · ".join(notes), 7, "6B5200", bold=True, valign="middle")
        elif notes:
            self.label(0.55, 15.1, 5.9, 0.42, " · ".join(notes), 7, color, valign="middle")

    def number_tag(self, color, x=5.35):
        self.label(x, 0.28, 1.1, 0.4, f"{self.card['index']:02d}/{self.card['total']:02d}", 7, color, align="right")


def _accent(cfg):
    return cfg["accent"], cfg["accent_soft"]


# ---------------------------------------------------------------- 레이아웃: 공통 표지·마무리 ----
def _cover(b: SceneBuilder, variant: str) -> str:
    cfg = b.cfg
    accent, soft = _accent(cfg)
    navy, white = cfg["navy"], cfg["white"]
    m = 0.55
    b.number_tag("AEB9CF" if variant in ("A", "D") else cfg["gray_text"])
    if variant == "A":
        bg = navy
        b.rect(m, 1.0, 2.9, 0.62, fill=white, radius=0.15)
        b.text("badge", m, 1.0, 2.9, 0.62, 7.5, navy, bold=True, align="center", valign="middle")
        b.text("title", m, 2.3, 5.9, 6.2, 19, white, bold=True)
        b.rect(m, 8.9, 1.4, 0.12, fill=accent)
        b.text("subtitle", m, 9.3, 5.9, 3.2, 10, "D5DDEC")
        b.text("source", m, 13.5, 5.9, 1.3, 7.5, "C0CADD", prefix="출처: ")
        b.footer_note("C0CADD")
    elif variant == "B":
        bg = cfg["white"]
        b.rect(0, 0, 7.0, 8.7, fill=navy)
        b.rect(m, 1.0, 2.9, 0.62, fill=white, radius=0.15)
        b.text("badge", m, 1.0, 2.9, 0.62, 7.5, navy, bold=True, align="center", valign="middle")
        b.text("title", m, 2.2, 5.9, 5.8, 19, white, bold=True)
        b.line(1.2, 9.6, 1.2, 13.9, accent, 2.0)
        for i, yy in enumerate((9.6, 11.3, 13.0)):
            b.ellipse(1.0, yy, 0.4, accent if i == 0 else cfg["navy_soft"])
        b.text("subtitle", 1.95, 9.4, 4.5, 3.4, 9.5, navy)
        b.text("source", m, 13.6, 5.9, 1.2, 7.5, cfg["gray_text"], prefix="출처: ")
        b.footer_note(cfg["gray_text"])
    elif variant == "C":
        bg = soft
        b.ellipse(3.4, 9.2, 4.6, cfg["white"], deco=True)
        b.ellipse(-1.6, 11.2, 4.2, cfg["navy_soft"], deco=True)
        b.rect(m, 1.0, 2.9, 0.62, fill=navy, radius=0.15)
        b.text("badge", m, 1.0, 2.9, 0.62, 7.5, white, bold=True, align="center", valign="middle")
        b.rect(m, 2.5, 0.14, 4.6, fill=accent)
        b.text("title", m + 0.4, 2.4, 5.5, 5.6, 19, navy, bold=True)
        b.text("subtitle", m, 8.3, 5.9, 3.0, 10, navy)
        b.text("source", m, 13.5, 5.9, 1.3, 7.5, cfg["gray_text"], prefix="출처: ")
        b.footer_note(cfg["gray_text"])
    else:  # D
        bg = navy
        b.ellipse(3.0, -1.8, 5.6, "27406B", deco=True)
        b.ellipse(-1.2, 9.6, 4.6, "27406B", deco=True)
        b.rect(m, 1.0, 2.9, 0.62, fill=white, radius=0.15)
        b.text("badge", m, 1.0, 2.9, 0.62, 7.5, navy, bold=True, align="center", valign="middle")
        b.text("title", m, 3.6, 5.9, 5.0, 19, white, bold=True)
        b.rect(m, 8.9, 1.4, 0.12, fill=accent)
        b.text("subtitle", m, 9.3, 5.9, 3.2, 10, "D5DDEC")
        b.text("source", m, 13.5, 5.9, 1.3, 7.5, "C0CADD", prefix="출처: ")
        b.footer_note("C0CADD")
    return bg


def _closing(b: SceneBuilder, variant: str) -> str:
    cfg = b.cfg
    accent, soft = _accent(cfg)
    navy, white = cfg["navy"], cfg["white"]
    m = 0.55
    bg = navy
    b.number_tag("AEB9CF")
    if variant == "B":
        b.line(0.9, 1.0, 0.9, 13.0, accent, 2.0)
    elif variant == "C":
        b.rect(0, 0, 7.0, 0.5, fill=accent)
    elif variant == "D":
        b.ellipse(3.6, 10.6, 5.2, "27406B", deco=True)
    else:
        b.rect(m, 1.0, 1.4, 0.12, fill=accent)
    x0, w0 = (1.4, 5.1) if variant == "B" else (m, 5.9)
    light = cfg["accent_light"]
    b.label(x0, 1.3, w0, 0.5, {"A": "KEY MESSAGE", "B": "SCHEDULE", "C": "IMPLICATION", "D": "INSIGHT"}[variant], 8, light, bold=True)
    b.text("message", x0, 2.0, w0, 5.6, 16, white, bold=True)
    b.line(x0, 8.0, x0 + 1.8, 8.0, accent, 1.5)
    b.label(x0, 8.3, w0, 0.5, {"A": "시사점·후속 과제", "B": "향후 일정", "C": "국내 시사점", "D": "산업적 의미"}[variant], 8, light, bold=True)
    b.text("follow_up", x0, 8.9, w0, 3.8, 9.5, "D5DDEC")
    b.text("source", x0, 13.1, w0, 1.7, 7.5, "C0CADD", prefix="출처: ")
    b.footer_note("C0CADD")
    return bg


def _header(b: SceneBuilder, kind_heading_key="heading", height=2.5) -> None:
    cfg = b.cfg
    b.rect(0, 0, 7.0, height, fill=cfg["navy"])
    b.number_tag("AEB9CF")
    b.text(kind_heading_key, 0.55, 0.65, 5.9, height - 0.8, 13, cfg["white"], bold=True, valign="middle")


# ---------------------------------------------------------------- 레이아웃: 본문 4종 ----
def _body_A(b: SceneBuilder) -> str:
    cfg = b.cfg
    accent, soft = _accent(cfg)
    dark = cfg["accent_dark"]
    navy, white = cfg["navy"], cfg["white"]
    m, cw = 0.55, 5.9
    _header(b)
    filled = [i for i in (1, 2, 3) if ((b.elements.get(f"content_{i}") or {}).get("text") or "").strip()]
    shown = filled if b.export else [1, 2, 3]  # 편집 화면은 비어 있어도 입력 위치를 보여주고, 출력에서는 빈 항목을 숨긴다
    n = max(len(shown), 1)
    gap = 0.2
    box_h = min((9.75 - gap * (n - 1)) / n, 4.4)
    start = 3.0 + (9.75 - (n * box_h + gap * (n - 1))) / 2  # 남은 항목은 머리글과 시사점 사이에 균형 있게 배치
    for pos, i in enumerate(shown):
        y0 = start + pos * (box_h + gap)
        b.rect(m, y0, cw, box_h, fill=white, line=cfg["border"], radius=0.18)
        b.ellipse(m + 0.2, y0 + 0.25, 0.75, dark)
        b.label(m + 0.2, y0 + 0.25, 0.75, 0.75, str(pos + 1 if b.export else i), 9, white, bold=True, align="center")
        b.text(f"content_{i}", m + 1.2, y0 + 0.2, cw - 1.4, box_h - 0.4, 9, navy)
    b.rect(m, 12.95, cw, 1.5, fill=soft, radius=0.15)
    b.label(m + 0.2, 13.0, 1.6, 0.4, "시사점", 7.5, dark, bold=True)
    b.text("implication", m + 0.2, 13.38, cw - 0.4, 1.0, 8, navy)
    b.text("source", m, 14.45, cw, 0.42, 7, cfg["gray_text"], prefix="출처: ", valign="middle")
    b.footer_note(cfg["gray_text"])
    return cfg["bg"]


def _stage_kind(b: SceneBuilder, i: int) -> str:
    el = b.elements.get(f"stage_{i}_kind") or {}
    return (el.get("text") or "other") if (el.get("text") or "other") in STAGE_KINDS else "other"


def _body_B(b: SceneBuilder) -> str:
    cfg = b.cfg
    accent, soft = _accent(cfg)
    navy, white = cfg["navy"], cfg["white"]
    m = 0.55
    _header(b, height=2.3)
    active = [i for i in range(1, STAGE_SLOTS + 1)
              if (b.elements.get(f"stage_{i}_date") or {}).get("text") or (b.elements.get(f"stage_{i}_text") or {}).get("text")]
    if not active:
        active = [1]  # 미리보기에서 첫 단계 입력 위치를 보여준다
    b.line(1.25, 3.0, 1.25, 3.0 + 2.25 * (len(active) - 1) + 0.6, accent, 2.0)
    for pos, i in enumerate(active):
        y = 2.9 + pos * 2.25
        kind = _stage_kind(b, i)
        color = STAGE_COLORS[kind]
        b.ellipse(1.0, y + 0.08, 0.5, color)
        b.rect(1.95, y, 2.3, 0.4, fill=color, radius=0.1)
        b.label(1.95, y, 2.3, 0.4, STAGE_KINDS[kind], 7, white, bold=True, align="center")
        b.text(f"stage_{i}_date", 1.95, y + 0.45, 4.5, 0.5, 9.5, navy, bold=True, valign="middle")
        b.text(f"stage_{i}_text", 1.95, y + 0.98, 4.5, 1.2, 8.5, "2C3A55")
    b.text("source", m, 14.45, 5.9, 0.42, 7, cfg["gray_text"], prefix="출처: ", valign="middle")
    b.footer_note(cfg["gray_text"])
    return cfg["white"]


def _body_C(b: SceneBuilder) -> str:
    cfg = b.cfg
    accent, soft = _accent(cfg)
    navy, white = cfg["navy"], cfg["white"]
    m, cw = 0.55, 5.9
    _header(b)
    b.text("topic", m, 2.7, cw, 0.6, 8.5, cfg["gray_text"], bold=True, valign="middle")
    rows = [{"h": 0.62, "cells": [
        {"text": "국가", "fill": navy, "color": white, "bold": True, "size": 8, "align": "center", "key": None},
        {"text": "핵심 정책 방향", "fill": navy, "color": white, "bold": True, "size": 8, "align": "center", "key": None}]}]
    for i in range(1, COUNTRY_SLOTS + 1):
        name_el, pol_el = b.elements.get(f"country_{i}_name") or {}, b.elements.get(f"country_{i}_policy") or {}
        name, pol = (name_el.get("text") or "").strip(), (pol_el.get("text") or "").strip()
        if not name and not pol and i > 2:
            continue
        if b.export and not name and not pol:
            continue
        rows.append({"h": 2.0, "cells": [
            {"text": name or f"[국가 {i}]", "fill": soft, "color": navy, "bold": True, "size": 8.5, "align": "center", "key": f"country_{i}_name",
             "placeholder": not name},
            {"text": pol or "자료 부족 — 추가 조사 필요", "fill": white, "color": navy if pol else "9AA3B2", "bold": False, "size": 8, "align": "left",
             "key": f"country_{i}_policy", "placeholder": not pol}]})
    height = sum(r["h"] for r in rows)
    b.items.append({"type": "table", "key": "country_table", "x": b._x(m), "y": b._y(3.5), "w": b._x(cw), "h": b._y(height),
                    "col_widths": [b._x(1.45), b._x(cw - 1.45)], "rows": [dict(r, h=b._y(r["h"])) for r in rows], "font": b.font,
                    "border": cfg["border"]})
    y = 3.5 + height + 0.2
    for label, key in (("주요 차이", "difference"), ("공통점·쟁점", "common"), ("국내 시사점 검토", "implication")):
        b.rect(m, y, cw, 1.32, fill=soft if key != "implication" else white, line=cfg["border"], radius=0.12)
        b.label(m + 0.15, y + 0.02, 3.0, 0.4, label, 7.5, cfg["accent_dark"], bold=True)
        b.text(key, m + 0.15, y + 0.38, cw - 0.3, 0.92, 7.5, navy)
        y += 1.4
    b.text("source", m, 14.45, cw, 0.42, 7, cfg["gray_text"], prefix="출처: ", valign="middle")
    b.footer_note(cfg["gray_text"])
    return cfg["bg"]


def _body_D(b: SceneBuilder) -> str:
    cfg = b.cfg
    accent, soft = _accent(cfg)
    navy, white = cfg["navy"], cfg["white"]
    m, cw = 0.55, 5.9
    _header(b)
    has_stat = bool(((b.elements.get("stat_value") or {}).get("text") or "").strip()) or not b.export
    if has_stat:
        b.rect(m, 2.9, cw, 2.7, fill=soft, radius=0.2)
        b.text("stat_value", m + 0.1, 2.95, 3.7, 1.5, 30, navy, bold=True, align="right", valign="middle")
        b.text("stat_unit", m + 3.9, 3.5, 1.8, 0.8, 11, navy, valign="middle")
        b.text("stat_label", m + 0.2, 4.5, cw - 0.4, 1.0, 8.5, navy, align="center", valign="middle")
    chart_el = b.elements.get("chart") or {}
    data = chart_el.get("data") if isinstance(chart_el.get("data"), dict) else None
    problems = validate_chart(data) if data else ["그래프 데이터가 없습니다"]
    synthetic = bool(data and data.get("synthetic"))
    chart_ok = not problems and (b.ctx.get("chart_verified") or synthetic)
    if chart_ok:
        b.rect(m, 5.8, cw, 4.65, fill=white, line=cfg["border"], radius=0.12)
        series = [s for s in data["series"] if str(s.get("label", "")).strip()]
        b.items.append({
            "type": "chart", "key": "chart", "x": b._x(m + 0.1), "y": b._y(5.9), "w": b._x(cw - 0.2), "h": b._y(3.7),
            "categories": [str(s["label"]) for s in series], "values": [float(s["value"]) for s in series],
            "unit": data["unit"], "title": data.get("title", ""), "color": accent, "navy": navy, "font": b.font, "synthetic": synthetic,
        })
        caption = f"기준연도 {data['base_year']} · 단위 {data['unit']}" + (f" · 비교대상 {data['comparison']}" if data.get("comparison") else "")
        if synthetic:
            caption += " · 합성 데이터"
        b.label(m, 9.65, cw, 0.7, caption, 7, cfg["gray_text"], valign="middle")
        top = 10.6
        b.layout = "chart"
    else:
        b.layout = "message"
        reason = "; ".join(problems) if problems else "그래프의 근거가 아직 검증되지 않았습니다"
        b.notes.append(f"그래프 미생성 — 메시지 중심 레이아웃으로 전환: {reason}")
        if not b.export:
            b.rect(m, 5.8, cw, 1.0, fill="FFF4D6", radius=0.1)
            b.label(m + 0.15, 5.85, cw - 0.3, 0.9, "그래프 미표시: " + reason[:60], 7, "6B5200", valign="middle")
        stat_shown = bool(((b.elements.get("stat_value") or {}).get("text") or "").strip()) or not b.export
        top = 7.0 if stat_shown else 3.3  # 핵심 수치가 없으면 헤더 바로 아래부터 내용을 배치한다
    if chart_ok:
        b.rect(m, top, cw, 1.75, fill=white, line=cfg["border"], radius=0.12)
        b.label(m + 0.15, top + 0.02, 3.0, 0.4, "기술·산업적 의미", 7.5, cfg["accent_dark"], bold=True)
        b.text("meaning", m + 0.15, top + 0.42, cw - 0.3, 1.3, 8, navy)
        b.rect(m, top + 1.9, cw, 2.0, fill=navy, radius=0.15)
        b.text("message", m + 0.2, top + 1.95, cw - 0.4, 1.9, 9.5, white, bold=True, valign="middle")
    else:
        b.rect(m, top, cw, 3.2, fill=white, line=cfg["border"], radius=0.12)
        b.label(m + 0.15, top + 0.02, 3.0, 0.4, "기술·산업적 의미", 7.5, cfg["accent_dark"], bold=True)
        b.text("meaning", m + 0.15, top + 0.42, cw - 0.3, 2.7, 9, navy)
        msg_h = min(14.3 - (top + 3.4), 5.6) if top < 5 else 3.6
        b.rect(m, top + 3.4, cw, msg_h, fill=navy, radius=0.15)
        b.text("message", m + 0.25, top + 3.5, cw - 0.5, msg_h - 0.2, 13, white, bold=True, valign="middle")
    b.text("source", m, 14.45, cw, 0.42, 7, cfg["gray_text"], prefix="출처: ", valign="middle")
    b.footer_note(cfg["gray_text"])
    return cfg["bg"]


BODY = {"A": _body_A, "B": _body_B, "C": _body_C, "D": _body_D}


def build_card_scene(width_cm: float, height_cm: float, cfg: dict, template_key: str, card: dict, ctx: dict) -> dict:
    """card = {"kind","bg_color","elements":{key:{...}},"index","total"}; ctx = for_export, labels, is_pilot, is_synthetic, chart_verified..."""
    b = SceneBuilder(width_cm, height_cm, cfg, card, ctx)
    b.layout = "default"
    kind = card["kind"]
    if kind == "cover":
        bg = _cover(b, template_key)
    elif kind == "closing":
        bg = _closing(b, template_key)
    else:
        bg = BODY[template_key](b)
    return {
        "width": width_cm, "height": height_cm, "background": card.get("bg_color") or bg,
        "kind": kind, "layout": b.layout, "items": b.items, "notes": b.notes,
    }


# ---------------------------------------------------------------- 장면 사전점검 ----
def _inside(x, y, it):
    return it["x"] <= x <= it["x"] + it["w"] and it["y"] <= y <= it["y"] + it["h"]


def check_scene(scene: dict, cfg: dict) -> list[dict]:
    """글자 잘림·카드 이탈·겹침·작은 글자·대비 부족을 점검한다. 좌표·글자 폭 기반 추정이며 실제 렌더링 점검과 함께 쓴다."""
    issues: list[dict] = []
    W, H = scene["width"], scene["height"]
    texts = [i for i in scene["items"] if i["type"] == "text" and not i.get("placeholder")]

    def add(level, code, msg, key=None):
        issues.append({"level": level, "code": code, "message": msg, "key": key})

    for t in texts:
        name = t.get("key") or t["text"][:12]
        if t["size"] < cfg["min_font_pt"]:
            add("warn", "tiny_font", f"글자 크기 {t['size']}pt가 최소 기준 {cfg['min_font_pt']}pt보다 작습니다", t.get("key"))
        need = text_height_cm(t["text"], t["size"], t["w"], t["bold"], t.get("spacing", 1.2))
        if need > t["h"] + 0.03:
            add("error", "text_overflow", f"'{name}' 글이 상자보다 깁니다(필요 {need:.1f}cm > {t['h']:.1f}cm) — 카드 분할·문장 축약이 필요합니다", t.get("key"))
        if t["x"] < -0.01 or t["y"] < -0.01 or t["x"] + t["w"] > W + 0.01 or t["y"] + t["h"] > H + 0.01:
            add("error", "out_of_bounds", f"'{name}' 요소가 카드 밖으로 나갑니다", t.get("key"))
    for it in scene["items"]:
        if it["type"] in ("rect", "ellipse") and not it.get("deco"):
            if it["x"] < -0.01 or it["y"] < -0.01 or it["x"] + it["w"] > W + 0.01 or it["y"] + it["h"] > H + 0.01:
                add("error", "out_of_bounds", f"도형 '{it.get('name') or it['type']}'이(가) 카드 밖으로 나갑니다")
    # 텍스트 상자 겹침(서로 다른 요소)
    for a_i in range(len(texts)):
        for b_i in range(a_i + 1, len(texts)):
            a, c = texts[a_i], texts[b_i]
            ox = min(a["x"] + a["w"], c["x"] + c["w"]) - max(a["x"], c["x"])
            oy = min(a["y"] + a["h"], c["y"] + c["h"]) - max(a["y"], c["y"])
            if ox > 0.08 and oy > 0.08:
                add("error", "text_overlap", f"'{a.get('key') or a['text'][:10]}'와 '{c.get('key') or c['text'][:10]}' 텍스트 상자가 겹칩니다")
    # 대비
    bg_stack = [("bg", scene["background"])]
    for it in scene["items"]:
        if it["type"] in ("rect", "ellipse") and it.get("fill"):
            bg_stack.append((it, it["fill"]))
        elif it["type"] == "text" and not it.get("placeholder"):
            cx, cy = it["x"] + it["w"] / 2, it["y"] + it["h"] / 2
            under = scene["background"]
            for obj, fill in bg_stack[1:]:
                if _inside(cx, cy, obj):
                    under = fill
            ratio = contrast_ratio(it["color"], under)
            need = 3.0 if (it["size"] >= 14 or (it["bold"] and it["size"] >= 12)) else 4.5
            if ratio < need:
                add("warn", "low_contrast", f"'{it.get('key') or it['text'][:10]}' 글자색 대비가 낮습니다({ratio:.1f}:1)", it.get("key"))
    for it in scene["items"]:
        if it["type"] == "table":
            for r_idx, row in enumerate(it["rows"]):
                for c_idx, cell in enumerate(row["cells"]):
                    if cell.get("placeholder"):
                        continue
                    w = it["col_widths"][c_idx]
                    need = text_height_cm(cell["text"], cell["size"], w - 0.1, cell.get("bold", False))
                    if need > row["h"] + 0.03:
                        add("error", "text_overflow", f"표 '{cell['text'][:12]}' 칸의 글이 넘칩니다(필요 {need:.1f}cm > {row['h']:.1f}cm)", cell.get("key"))
    for note in scene.get("notes", []):
        add("info", "layout_fallback", note)
    return issues


def element_dict(row) -> dict:
    """DB 요소 행 → 장면 빌더용 dict."""
    def load(s):
        try:
            return json.loads(s) if s else None
        except ValueError:
            return None

    return {
        "type": row.element_type, "text": row.text, "data": load(row.data_json), "style": load(row.style_json) or {},
        "box": load(row.box_json) or {}, "hidden": row.hidden,
    }
