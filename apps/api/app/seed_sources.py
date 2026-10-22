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
        "arXiv cs.AI",
        "Cornell University (arXiv)",
        "INT",
        "http://export.arxiv.org/rss/cs.AI",
        SourceType.RSS,
        None,
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
        "Federal Register — NTIA(디지털 포용·통신정보)",
        "National Telecommunications and Information Administration",
        "US",
        FR_BASE + "?conditions%5Bagencies%5D%5B%5D=national-telecommunications-and-information-administration"
        "&per_page=20&order=newest",
        SourceType.API,
        "federal_register",
        True,
        1,
    ),
    (
        FieldCode.BCAST,
        "Federal Register — FCC(방송·전파)",
        "Federal Communications Commission",
        "US",
        FR_BASE + "?conditions%5Bagencies%5D%5B%5D=federal-communications-commission&per_page=20&order=newest",
        SourceType.API,
        "federal_register",
        True,
        1,
    ),
    (
        FieldCode.SW,
        "Federal Register — NHTSA(자율주행·차량안전)",
        "National Highway Traffic Safety Administration",
        "US",
        FR_BASE + "?conditions%5Bagencies%5D%5B%5D=national-highway-traffic-safety-administration"
        "&per_page=20&order=newest",
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
        "Federal Register — NSF Convergence Accelerator(ICT 융합)",
        "National Science Foundation",
        "US",
        FR_BASE + "?conditions%5Bagencies%5D%5B%5D=national-science-foundation"
        "&conditions%5Bterm%5D=convergence&per_page=20&order=newest",
        SourceType.API,
        "federal_register",
        True,
        1,
    ),
]

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
    finally:
        db.close()


if __name__ == "__main__":
    seed()
