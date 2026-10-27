"""9대 분야 공식 출처 시드 스크립트.

실행: python -m app.seed_sources

중요: 여기 등록하는 URL은 전부 이 작업 중 실제로 curl로 접속해 응답(RSS 또는 JSON)을 직접
확인한 것만 넣는다(추측 URL 절대 금지 — 진행 원칙). 2026-10-22 Phase 2-1 기준 9대 분야
전체에 최소 1곳, 일부 분야는 2곳의 실제 작동 출처를 확보했다. 정확한 확보 현황과 미확보
사유는 docs/PLATFORM_PLAN.md §5-2 "Phase 2-1 출처 확보 현황" 표를 참고.

Federal Register(federalregister.gov) API는 미국 연방관보 공개 API로, API 키 없이
기관(agency)·검색어(term) 조건으로 미리 필터링한 URL을 그대로 쓴다. 쿼리 하나하나를
curl로 직접 호출해 해당 분야와 실제로 관련된 문서가 나오는지 확인한 뒤에만 등록했다.
"""

from app.core.db import Base, SessionLocal, engine
from app.models.enums import FieldCode, SourceType
from app.models.source import Source

FR_BASE = "https://www.federalregister.gov/api/v1/articles.json"

# (분야, 출처명, 운영기관, 국가코드, URL, 수집방식, api_provider, 1차출처 여부, 신뢰도)
VERIFIED_SOURCES = [
    # --- 기존(1단계에서 확보, 재검증 완료) ---
    (
        FieldCode.AI,
        "arXiv API — cs.AI 최신 논문",
        "arXiv (Cornell University)",
        "INT",
        # arXiv RSS(export.arxiv.org/rss)는 robots.txt 로 자동 수집이 허용되지 않아 공식 API(Atom)를 쓴다. 호출 간격 3초 준수.
        "https://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=30",
        SourceType.API,
        "arxiv_api",
        False,  # 프리프린트 저장소 — 1차 정부/표준화 출처 아님
        2,
    ),
    (
        FieldCode.SEC,
        "NIST News",
        "National Institute of Standards and Technology",
        "US",
        "https://www.nist.gov/news-events/news/rss.xml",
        SourceType.RSS,
        None,
        True,
        1,
    ),
    (
        FieldCode.NET,
        "W3C News",
        "World Wide Web Consortium",
        "INT",
        "https://www.w3.org/news/feed/",
        SourceType.RSS,
        None,
        True,
        1,
    ),
    # --- Phase 2-1 신규(Federal Register API, 전부 curl로 응답 확인) ---
    (
        FieldCode.AI,
        "Federal Register — NIST × AI",
        "NIST (via Federal Register)",
        "US",
        FR_BASE + "?conditions%5Bagencies%5D%5B%5D=national-institute-of-standards-and-technology"
        "&conditions%5Bterm%5D=artificial+intelligence&per_page=20&order=newest",
        SourceType.API,
        "federal_register",
        True,
        1,
    ),
    (
        FieldCode.SOC,
        "Federal Register — NTIA × 광대역(디지털 포용)",
        "National Telecommunications and Information Administration",
        "US",
        FR_BASE + "?conditions%5Bagencies%5D%5B%5D=national-telecommunications-and-information-administration"
        "&conditions%5Bterm%5D=broadband&per_page=20&order=newest",
        SourceType.API,
        "federal_register",
        True,
        1,
    ),
    (
        FieldCode.BCAST,
        "Federal Register — FCC(방송·전파, 확정 규칙만)",
        "Federal Communications Commission",
        "US",
        FR_BASE + "?conditions%5Bagencies%5D%5B%5D=federal-communications-commission"
        "&conditions%5Btype%5D%5B%5D=RULE&conditions%5Btype%5D%5B%5D=PRORULE&per_page=20&order=newest",
        SourceType.API,
        "federal_register",
        True,
        1,
    ),
    (
        FieldCode.SW,
        "Federal Register — NHTSA × 자율주행차(Autonomous Vehicle)",
        "National Highway Traffic Safety Administration",
        "US",
        FR_BASE + "?conditions%5Bagencies%5D%5B%5D=national-highway-traffic-safety-administration"
        "&conditions%5Bterm%5D=autonomous+vehicle&per_page=20&order=newest",
        SourceType.API,
        "federal_register",
        True,
        1,
    ),
    (
        FieldCode.CONTENT,
        "Federal Register — US Copyright Office(콘텐츠·저작권)",
        "U.S. Copyright Office",
        "US",
        FR_BASE + "?conditions%5Bagencies%5D%5B%5D=copyright-office-library-of-congress&per_page=20&order=newest",
        SourceType.API,
        "federal_register",
        True,
        1,
    ),
    (
        FieldCode.SEMI,
        "Federal Register — BIS × 반도체 수출통제",
        "Bureau of Industry and Security",
        "US",
        FR_BASE + "?conditions%5Bagencies%5D%5B%5D=industry-and-security-bureau"
        "&conditions%5Bterm%5D=semiconductor&per_page=20&order=newest",
        SourceType.API,
        "federal_register",
        True,
        1,
    ),
    (
        FieldCode.CONV,
        "Federal Register — OSTP(신기술 융합정책)",
        "White House Office of Science and Technology Policy",
        "US",
        FR_BASE + "?conditions%5Bagencies%5D%5B%5D=science-and-technology-policy-office&per_page=20&order=newest",
        SourceType.API,
        "federal_register",
        True,
        1,
    ),
]

# 2026-10-22 품질 재점검에서 제외한 출처 — 등록·접속은 됐지만 반려한 경우를 기록해 둔다.
REJECTED_SOURCES_NOTE = """품질 재점검 과정에서 제외/교체한 출처:
- NSF "Convergence Accelerator" term 필터: 응답이 전부 "Agency Information Collection
  Activities"류 행정 공고뿐이었고 실질적 정책·연구 문서가 없어 OSTP로 교체함.
- NTIA/FCC는 필터 없이 기관 전체 피드를 쓰면 Privacy Act 기록공고·OMB 서류수집 공고가
  대다수를 차지해 type=RULE/PROPOSED RULE로 좁혔다.
- NHTSA는 기관 전체 피드가 일반 차량안전 규정(연비, 카시트 등) 위주라 term="automated
  driving system"으로 좁혀 자율주행 관련 문서만 남겼다."""

MISSING_SECOND_SOURCE_NOTE = """"분야별 2곳 이상" 목표 대비, 현재 2곳을 확보한 분야는 인공지능·데이터뿐이다.
나머지 7개 분야는 각 1곳만 확보된 상태 — 추가 출처 확보는 Phase 2-1 후속 작업으로 남겨둔다.
자세한 사유는 docs/PLATFORM_PLAN.md §5-2 참고."""


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        created = 0
        for field_code, name, org_name, country_code, url, source_type, api_provider, is_primary, tier in VERIFIED_SOURCES:
            if db.query(Source).filter(Source.url == url).first():
                continue
            db.add(
                Source(
                    name=name,
                    org_name=org_name,
                    field_code=field_code,
                    country_code=country_code,
                    url=url,
                    source_type=source_type,
                    api_provider=api_provider,
                    is_primary_source=is_primary,
                    reliability_tier=tier,
                )
            )
            created += 1
        db.commit()
        print(f"출처 시드 완료 — {created}건 신규 등록(전체 {len(VERIFIED_SOURCES)}건 중)")
        print(MISSING_SECOND_SOURCE_NOTE)
        print()
        print(REJECTED_SOURCES_NOTE)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
