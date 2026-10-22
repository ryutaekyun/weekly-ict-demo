"""9대 분야 공식 출처 시드 스크립트.

실행: python -m app.seed_sources

중요: 여기 등록하는 URL은 전부 이 작업 중 실제로 curl/WebSearch로 접속해 RSS 응답을 직접
확인한 것만 넣는다(추측 URL 절대 금지 — 진행 원칙). 2026-10-22 기준 9대 분야 중 3개 분야만
실제 확인된 공식 출처를 찾았고, 나머지 6개 분야는 아직 검증된 출처가 없어 의도적으로 비워둔다.
담당자가 실제 접속 가능한 출처를 확인해 `sources` 테이블에 추가해야 한다(출처 이용약관·robots
정책을 먼저 확인할 것).
"""

from app.core.db import Base, SessionLocal, engine
from app.models.enums import FieldCode, SourceType
from app.models.source import Source

# (분야, 출처명, 운영기관, URL, 신뢰도) — URL은 2026-10-22에 HTTP 200 + 정상 RSS 응답으로 직접 확인함
VERIFIED_SOURCES = [
    (
        FieldCode.AI,
        "arXiv cs.AI",
        "Cornell University (arXiv)",
        "http://export.arxiv.org/rss/cs.AI",
        2,  # 학술 프리프린트 — 동료심사 이전이므로 신뢰도 등급은 공식 기관보다 낮게 설정
    ),
    (
        FieldCode.SEC,
        "NIST News",
        "National Institute of Standards and Technology",
        "https://www.nist.gov/news-events/news/rss.xml",
        1,
    ),
    (
        FieldCode.NET,
        "W3C News",
        "World Wide Web Consortium",
        "https://www.w3.org/news/feed/",
        1,
    ),
]

MISSING_FIELD_NOTE = """아직 검증된 공식 출처가 없는 분야(담당자 확인 필요):
디지털사회혁신, 방송·전파·위성, SW·자율주행, 콘텐츠·미디어, 반도체·양자, ICT 융합기술"""


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for field_code, name, org_name, url, tier in VERIFIED_SOURCES:
            exists = db.query(Source).filter(Source.url == url).first()
            if exists:
                continue
            db.add(
                Source(
                    name=name,
                    org_name=org_name,
                    field_code=field_code,
                    url=url,
                    source_type=SourceType.RSS,
                    reliability_tier=tier,
                )
            )
        db.commit()
        print(f"출처 시드 완료 — {len(VERIFIED_SOURCES)}건 등록")
        print(MISSING_FIELD_NOTE)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
