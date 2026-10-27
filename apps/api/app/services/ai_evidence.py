"""AI 생성 문장의 원문 근거 검증(순수 함수).

AI가 쓴 '발췌문(quote)'이 실제 원문에 있는지, 문장 속 날짜·수치가 그 발췌문에 있는지를 서버가 직접 확인한다.
AI가 만든 문서 ID·URL·페이지 번호는 믿지 않는다 — URL은 DB의 원문 주소, 위치는 원문 텍스트에서 계산한 값만 쓴다.
"""

import difflib
import re

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
DATE_PATTERNS = [
    (re.compile(r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*[.일]?"), lambda m: (m[1], m[2], m[3])),
    (re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I), lambda m: (m[3], MONTHS[m[1].lower()], m[2])),
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\.?,?\s+(\d{{4}})\b", re.I), lambda m: (m[3], MONTHS[m[2].lower()], m[1])),
]
NUM_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
INJECTION_PATTERNS = re.compile(
    r"(ignore (all |any )?(previous|prior|above) (instructions|prompts)|disregard (the )?(system|previous)|you are now|system prompt|"
    r"이전 (지시|명령)(을|를)? 무시|시스템 (프롬프트|지시)|api[ _-]?key|reveal (your|the) (instructions|prompt))",
    re.I,
)
URL_RE = re.compile(r"https?://\S+")


def normalize(text: str) -> str:
    """대조용 정규형 — 공백·하이픈·따옴표 표기 차이(PDF 줄바꿈 분철 'distil- lation' 등)를 무시하고 비교한다."""
    t = (text or "").replace(" ", " ").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.lower()
    return re.sub(r"[\s\-‐-―­]+", "", t)


def extract_dates(text: str) -> set[str]:
    found = set()
    for pat, conv in DATE_PATTERNS:
        for m in pat.finditer(text or ""):
            try:
                y, mo, d = conv(m)
                found.add(f"{int(y):04d}-{int(mo):02d}-{int(d):02d}")
            except (ValueError, KeyError):
                continue
    return found


def _strip_dates(text: str) -> str:
    out = text or ""
    for pat, _ in DATE_PATTERNS:
        out = pat.sub(" ", out)
    return out


def extract_numbers(text: str) -> set[str]:
    return {m.replace(",", "").rstrip(".") for m in NUM_RE.findall(_strip_dates(text))}


def check_values(claim_text: str, evidence_text: str) -> list[str]:
    """문장의 날짜·수치가 근거 발췌문에 모두 있어야 한다. 없는 값 목록을 돌려준다(비어 있으면 일치)."""
    problems = []
    for d in sorted(extract_dates(claim_text) - extract_dates(evidence_text)):
        problems.append(f"날짜 {d}")
    ev_nums = extract_numbers(evidence_text)
    ev_dates_digits = {p for d in extract_dates(evidence_text) for p in d.split("-")}
    for n in sorted(extract_numbers(claim_text) - ev_nums):
        # 연도 등 날짜 조각이 다른 표기로 쓰인 경우는 날짜 검사가 맡는다
        if n.lstrip("0") in {p.lstrip("0") for p in ev_dates_digits} and not extract_dates(claim_text):
            continue
        problems.append(f"수치 {n}")
    return problems


def locate_quote(full_text: str, quote: str) -> tuple[bool, str | None, str]:
    """원문에서 발췌문을 찾는다. (찾았는지, 위치 라벨, 설명). 위치는 원문 텍스트에서 계산 가능할 때만 만든다."""
    q = normalize(quote)
    if len(q) < 12:
        return False, None, "발췌문이 너무 짧아 근거로 인정할 수 없음"
    label = _paragraph_label(full_text, q)
    if label is not None:
        return True, label, "원문과 일치"
    hay = normalize(full_text)
    if q in hay:
        return True, None, "원문과 일치(여러 문단에 걸쳐 있어 위치 미확인)"
    pos, _ = _fuzzy_find(hay, q)
    if pos >= 0:
        return True, None, "공백·표기 차이를 허용한 근사 일치(위치 미확인)"
    return False, None, "원문에서 이 발췌문을 찾지 못함"


def _fuzzy_find(hay: str, q: str, threshold: float = 0.94) -> tuple[int, float]:
    if len(hay) < len(q) // 2:
        return -1, 0.0
    step = max(10, len(q) // 6)
    best_pos, best = -1, 0.0
    for i in range(0, max(1, len(hay) - len(q) + 1), step):
        r = difflib.SequenceMatcher(None, hay[i : i + len(q)], q, autojunk=False).ratio()
        if r > best:
            best, best_pos = r, i
    return (best_pos, best) if best >= threshold else (-1, best)


def _paragraph_label(full_text: str, q_norm: str) -> str | None:
    """쪽(폼 피드 문자)·문단(빈 줄) 단위로 나눠 발췌문이 들어 있는 곳을 센다. 못 찾으면 None."""
    pages = full_text.split("\f")
    for pi, page in enumerate(pages, start=1):
        for gi, para in enumerate([x for x in re.split(r"\n\s*\n", page) if x.strip()], start=1):
            if q_norm in normalize(para):
                return f"p.{pi}, {gi}문단" if len(pages) > 1 else f"{gi}문단"
    return None


def scan_injection(text: str) -> list[str]:
    return sorted({m.group(0).lower() for m in INJECTION_PATTERNS.finditer(text or "")})[:5]


def strip_urls(text: str) -> tuple[str, bool]:
    cleaned = URL_RE.sub("", text or "").strip()
    return cleaned, cleaned != (text or "").strip()


# ---------------------------------------------------------------- 의미 불일치 가능성(값은 있지만 뜻이 달라진 주장) ----
ROLE_PATTERNS = {
    "시행일": re.compile(r"시행|발효|적용 개시|take[s]? effect|effective|come[s]? into (?:force|effect)|become[s]? effective|applies? (?:on|from)", re.I),
    "발표일": re.compile(r"발표|공고|공표|게재|고시|제정안|published|announced|issued|released|proposed", re.I),
    "준수 시한": re.compile(r"준수|이행|제출 기한|마감|시한|기한|comply|compliance|must (?:be|document|submit)|deadline|no later than|due\b", re.I),
    "의견수렴 마감": re.compile(r"의견 ?수렴|의견 제출|comment[s]? (?:are )?due|comment period|submit comments", re.I),
}
UNIT_ALIASES = {"%": "%", "퍼센트": "%", "percent": "%", "kg": "kg", "㎏": "kg", "g": "g", "t": "t", "톤": "t", "ton": "t", "tons": "t",
                "gw": "gw", "mw": "mw", "ghz": "ghz", "mhz": "mhz", "nm": "nm", "tb": "tb", "gb": "gb", "원": "원", "달러": "usd", "usd": "usd", "$": "usd",
                "명": "명", "건": "건", "개": "개", "배": "배", "년": "년", "개월": "개월", "일": "일", "days": "일", "months": "개월", "years": "년"}
_UNIT_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s?(%|퍼센트|percent|kg|㎏|g|톤|tons?|t|gw|mw|ghz|mhz|nm|tb|gb|원|달러|usd|\$|명|건|개월|개|배|년|일|days|months|years)(?![a-z])", re.I)
GT = re.compile(r"초과|이상|넘|over|more than|greater than|exceed|at least|above", re.I)
LT = re.compile(r"미만|이하|under|less than|below|at most|no more than|fewer than", re.I)
NEG_KO = re.compile(r"않|아니|없|불가|금지|제외|못 ?한|면제|배제")
NEG_EN = re.compile(r"\b(?:not|no|never|without|prohibit\w*|exempt\w*|except|unless|cannot|can't|doesn't|don't|isn't|aren't)\b", re.I)


def date_roles(text: str) -> dict[str, set[str]]:
    """문장 속 각 날짜 앞뒤 문맥에서 날짜의 역할(시행일·발표일·준수 시한·의견수렴 마감)을 추정한다."""
    roles: dict[str, set[str]] = {}
    for pat, conv in DATE_PATTERNS:
        for m in pat.finditer(text or ""):
            try:
                y, mo, d = conv(m)
                iso = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            except (ValueError, KeyError):
                continue
            ctx = text[max(0, m.start() - 70) : m.end() + 20]
            found = {name for name, rp in ROLE_PATTERNS.items() if rp.search(ctx)}
            roles.setdefault(iso, set()).update(found)
    return roles


def unit_pairs(text: str) -> list[tuple[str, str]]:
    return [(n.replace(",", ""), UNIT_ALIASES.get(u.lower(), u.lower())) for n, u in _UNIT_RE.findall(_strip_dates(text or ""))]


def semantic_flags(claim_text: str, quote: str) -> list[str]:
    """값(날짜·수치)이 발췌문에 존재하더라도 뜻이 달라졌을 가능성(날짜 역할·단위·부등호·부정)을 알린다. 단정이 아니라 '검토 필요' 신호다."""
    flags: list[str] = []
    cr, qr = date_roles(claim_text), date_roles(quote)
    for iso, c_roles in cr.items():
        q_roles = qr.get(iso)
        if c_roles and q_roles and not (c_roles & q_roles):
            flags.append(f"날짜 {iso}의 역할이 다름(문장: {'/'.join(sorted(c_roles))} ↔ 발췌문: {'/'.join(sorted(q_roles))})")
    cu, qu = unit_pairs(claim_text), unit_pairs(quote)
    q_by_num: dict[str, set[str]] = {}
    for n, u in qu:
        q_by_num.setdefault(n, set()).add(u)
    for n, u in cu:
        if n in q_by_num and u not in q_by_num[n]:
            flags.append(f"수치 {n}의 단위가 다름(문장: {u} ↔ 발췌문: {'/'.join(sorted(q_by_num[n]))})")
    c_dir = {"초과·이상" if GT.search(claim_text) else None, "미만·이하" if LT.search(claim_text) else None} - {None}
    q_dir = {"초과·이상" if GT.search(quote) else None, "미만·이하" if LT.search(quote) else None} - {None}
    if len(c_dir) == 1 and len(q_dir) == 1 and c_dir != q_dir:
        flags.append(f"수량 조건이 반대일 수 있음(문장: {next(iter(c_dir))} ↔ 발췌문: {next(iter(q_dir))})")
    c_neg = bool(NEG_KO.search(claim_text)) or bool(NEG_EN.search(claim_text))
    q_neg = bool(NEG_EN.search(quote)) or bool(NEG_KO.search(quote))
    if c_neg != q_neg:
        flags.append("부정·긍정 의미가 다를 수 있음(문장과 발췌문의 부정 표현 유무가 다름)")
    return flags


def value_elsewhere(problems: list[str], full_text: str) -> list[str]:
    """발췌문에는 없지만 같은 문서의 다른 위치에는 있는 값 — 근거를 엉뚱한 위치에 연결했을 가능성."""
    out = []
    dates = extract_dates(full_text)
    nums = extract_numbers(full_text)
    for p in problems:
        kind, _, val = p.partition(" ")
        if (kind == "날짜" and val in dates) or (kind == "수치" and val in nums):
            out.append(p)
    return out
