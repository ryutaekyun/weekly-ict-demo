"""ICT 9대 분야 분류 기준.

Phase 2-2 지시사항 — "분류 기준은 9대 분야별 키워드만으로 구성하지 말고, 분야의 정의·포함
주제·제외 주제·경계 사례를 함께 정의"에 따라 키워드 목록이 아니라 분야별 정의/포함/제외/경계
사례를 1차 자료로 두고, 키워드는 규칙 기반 분류기가 참조하는 2차 자료로만 둔다.

주의: 이 taxonomy는 규칙 기반(키워드 매칭) 분류와, 향후 AI 분류 프롬프트에 그대로 주입하는
컨텍스트로 함께 쓰인다 — 어느 쪽이든 "분야 정의"는 이 한 곳만 수정하면 된다.
"""

from dataclasses import dataclass, field

from app.models.enums import FieldCode


@dataclass(frozen=True)
class FieldDefinition:
    code: FieldCode
    name_ko: str
    definition: str
    includes: list[str]
    excludes: list[str]
    boundary_cases: list[str]
    # 키워드는 (가중치, 문자열) 쌍 — 구체적인 복합어일수록 가중치를 높게 둬서
    # "AI"처럼 너무 일반적인 토큰 하나로 다른 분야 문서를 오분류하는 것을 줄인다.
    keywords: list[tuple[float, str]] = field(default_factory=list)
    # 이 분야로 오분류되기 쉬운 "행정 절차성" 문구 — 값 자체가 분야를 의미하지는 않는다.
    administrative_boilerplate: list[str] = field(default_factory=list)


FIELD_DEFINITIONS: dict[FieldCode, FieldDefinition] = {
    FieldCode.SOC: FieldDefinition(
        code=FieldCode.SOC,
        name_ko="디지털사회혁신",
        definition=(
            "ICT를 활용해 디지털 포용·격차해소·공공서비스 혁신 등 사회 문제를 해결하는 정책·사업. "
            "기술 자체보다 '누구에게 어떤 사회적 효용을 주는가'가 핵심이다."
        ),
        includes=[
            "디지털 포용·디지털 격차 해소(고령층, 장애인, 농어촌 등)",
            "초고속망·공공 와이파이 등 보편적 접근성 정책",
            "전자정부·공공서비스 디지털 전환",
            "디지털 리터러시·역량강화 교육",
        ],
        excludes=[
            "순수 통신망 기술 규격·주파수 할당(→ 통신·네트워크)",
            "AI 윤리·데이터 정책 전반(사회적 효용이 아니라 기술 자체가 주제면 → 인공지능·데이터)",
        ],
        boundary_cases=[
            "'농어촌 광대역 보급 정책'은 기술 규격이 아니라 접근성 격차 해소가 목적이므로 SOC로 분류한다",
            "'공공 와이파이망 주파수 간섭 기준'처럼 기술 규격이 핵심이면 NET로 분류한다",
            "'WCAG/EPUB 접근성 명세' 같은 W3C 기술표준 자체는 NET로 분류한다 — 'accessibility'라는 단어가 "
            "있어도 장애인 접근성 '정책'이 아니라 웹 표준 '규격'이 주제이기 때문이다(실데이터 검증에서 "
            "WCAG 번역 공지가 이 키워드만으로 SOC로 오분류된 사례를 수정함)",
        ],
        keywords=[
            (3.0, "digital divide"), (3.0, "디지털 격차"), (3.0, "digital inclusion"), (3.0, "디지털 포용"),
            (2.0, "broadband access"), (2.0, "보편적 서비스"), (1.0, "accessibility"), (1.0, "접근성"),
            (1.5, "전자정부"), (1.5, "e-government"), (1.0, "공공서비스"),
        ],
        administrative_boilerplate=["agency information collection activities", "paperwork reduction act"],
    ),
    FieldCode.NET: FieldDefinition(
        code=FieldCode.NET,
        name_ko="통신·네트워크",
        definition="이동통신·유선망·인터넷 프로토콜 등 통신 인프라 자체의 기술·표준·정책.",
        includes=["5G/6G 등 이동통신 기술", "유무선 네트워크 프로토콜·표준(W3C, IETF 등)", "망 중립성·상호접속 정책", "광대역망 구축 기술"],
        excludes=["전파·위성·방송 전송(→ 방송·전파·위성)", "네트워크 보안 자체가 핵심이면(→ 보안·블록체인)"],
        boundary_cases=[
            "'위성 인터넷(스타링크 등)'은 위성 측면이 강하면 BCAST, 지상 네트워크 프로토콜 측면이 강하면 NET로 본다 — 원문에서 더 비중 있게 다루는 쪽을 따른다",
        ],
        keywords=[
            (3.0, "web standard"), (3.0, "웹 표준"), (2.5, "network protocol"), (2.0, "broadband"),
            (2.0, "광대역"), (2.0, "5g network"), (2.0, "6g network"), (2.0, "5g technology"),
            (2.0, "6g technology"), (2.0, "이동통신"), (1.5, "interoperability"), (1.5, "상호운용성"),
            (2.5, "wcag"), (2.0, "web content accessibility guidelines"), (2.0, "epub accessibility"),
        ],
        administrative_boilerplate=[],
    ),
    FieldCode.BCAST: FieldDefinition(
        code=FieldCode.BCAST,
        name_ko="방송·전파·위성",
        definition="방송 전송·주파수 자원 관리·위성통신 등 전파 매체를 이용한 전송 기술·정책.",
        includes=["방송통신 주파수 할당·간섭 규제", "위성통신·위성항법", "지상파/케이블/OTT 전송 규제", "IoT 저전력 통신(전파자원 관점)"],
        excludes=["방송 콘텐츠 심의·저작권(→ 콘텐츠·미디어)", "순수 유선망 프로토콜(→ 통신·네트워크)"],
        boundary_cases=["'OTT 플랫폼 규제'는 전송망 규제면 BCAST, 콘텐츠 심의·저작권이면 CONTENT로 분류한다"],
        keywords=[
            (3.0, "spectrum"), (3.0, "주파수"), (2.5, "satellite"), (2.5, "위성"), (2.0, "broadcasting"),
            (2.0, "방송"), (1.5, "frequency allocation"), (1.5, "전파"),
        ],
        administrative_boilerplate=["agency information collection activities"],
    ),
    FieldCode.SW: FieldDefinition(
        code=FieldCode.SW,
        name_ko="SW·자율주행",
        definition="소프트웨어 공학·클라우드·자율주행 등 소프트웨어 중심 기술(데이터·AI 모델 자체는 제외).",
        includes=["자율주행차 소프트웨어·안전기준", "클라우드 네이티브·SaaS", "오픈소스 SW 정책", "디지털콘텐츠 제작 SW 도구"],
        excludes=["AI 모델·알고리즘 자체의 성능/윤리(→ 인공지능·데이터)", "차량 안전기준 중 전자장치가 아닌 일반 기계적 안전(→ 분류 보류/관련성 낮음)"],
        boundary_cases=[
            "'자율주행차 자동긴급제동장치(일반 기계·센서) 안전기준'처럼 AV 소프트웨어·자율주행 판단로직과 무관한 일반 차량안전 규정은 SW로 보지 않고 관련성 낮음으로 처리한다",
            "'자율주행 레벨3 소프트웨어 인증 기준'은 SW로 분류한다",
        ],
        keywords=[
            (3.0, "autonomous vehicle"), (3.0, "자율주행"), (2.5, "self-driving"), (2.0, "cloud native"),
            (2.0, "클라우드"), (1.5, "open source"), (1.5, "오픈소스"), (1.0, "software"),
        ],
        administrative_boilerplate=["agency information collection activities", "vehicle safety standard  general"],
    ),
    FieldCode.AI: FieldDefinition(
        code=FieldCode.AI,
        name_ko="인공지능·데이터",
        definition="인공지능 모델·알고리즘·데이터 거버넌스 자체의 기술·정책·윤리.",
        includes=["생성형 AI·대규모언어모델", "AI 안전성·정렬·평가", "데이터 프라이버시·데이터 거버넌스", "빅데이터 분석 기법"],
        excludes=["AI가 적용된 특정 산업 응용이 주제의 중심이면 해당 산업 분야(예: 자율주행 SW)로 분류", "반도체 하드웨어 자체가 중심이면(→ 반도체·양자)"],
        boundary_cases=[
            "'AI 반도체 수출통제'처럼 정책의 규제 대상이 반도체 하드웨어(품목)면 SEMI로, AI 모델 성능·안전성이 중심이면 AI로 분류한다",
            "'AI 의무 적용(고위험 AI 시스템 규정)'처럼 AI 시스템 자체를 규율하면 AI로 분류한다",
        ],
        keywords=[
            (3.0, "artificial intelligence"), (3.0, "인공지능"), (3.0, "large language model"), (2.5, "생성형 ai"),
            (2.5, "machine learning"), (2.0, "머신러닝"), (2.0, "data governance"), (2.0, "데이터 거버넌스"),
            (1.5, "algorithm"), (1.0, "데이터"),
        ],
        administrative_boilerplate=["agency information collection activities"],
    ),
    FieldCode.CONTENT: FieldDefinition(
        code=FieldCode.CONTENT,
        name_ko="콘텐츠·미디어",
        definition="디지털 콘텐츠·저작권·미디어 유통 플랫폼 정책.",
        includes=["저작권 등록·보호 제도", "OTT/스트리밍 콘텐츠 유통 정책", "메타버스·XR 콘텐츠", "디지털 콘텐츠 산업 통계"],
        excludes=["콘텐츠를 전달하는 전송망 기술 자체(→ 통신/방송)", "콘텐츠 제작 SW 툴 자체 기술(→ SW)"],
        boundary_cases=["'저작권청의 AI 생성물 저작권 등록 지침'은 저작권 제도가 중심이므로 CONTENT로 분류한다"],
        keywords=[
            (3.0, "copyright"), (3.0, "저작권"), (2.5, "streaming"), (2.0, "스트리밍"), (2.0, "metaverse"),
            (2.0, "메타버스"), (1.5, "콘텐츠"), (1.5, "미디어"),
        ],
        administrative_boilerplate=[],
    ),
    FieldCode.SEC: FieldDefinition(
        code=FieldCode.SEC,
        name_ko="보안·블록체인",
        definition="사이버보안·암호기술·블록체인/디지털자산 기술 및 정책.",
        includes=["사이버보안 표준·가이드라인(NIST 등)", "암호 알고리즘·양자내성암호", "블록체인·디지털자산 규제", "개인정보 유출 대응"],
        excludes=["AI 모델의 '안전성(safety)' 자체는 AI로, 시스템 침해·암호화 같은 보안기술이 중심이면 SEC로 분류한다"],
        boundary_cases=["'AI 시스템 보안 취약점 가이드라인'처럼 AI와 보안이 겹치면, 다루는 범위가 보안 통제 체계면 SEC, AI 모델 자체의 위험 평가면 AI로 분류한다"],
        keywords=[
            (3.0, "cybersecurity"), (3.0, "사이버보안"), (2.5, "encryption"), (2.5, "암호"), (2.0, "blockchain"),
            (2.0, "블록체인"), (1.5, "vulnerability"), (1.5, "취약점"), (1.5, "cyberattack"), (1.5, "사이버 공격"),
            (1.5, "data breach"),
        ],
        administrative_boilerplate=["agency information collection activities"],
    ),
    FieldCode.SEMI: FieldDefinition(
        code=FieldCode.SEMI,
        name_ko="반도체·양자",
        definition="반도체 소자·공정·장비와 양자컴퓨팅/통신/센싱 하드웨어 기술·산업정책.",
        includes=["반도체 설계·공정·장비 기술", "반도체 공급망·수출통제 정책", "양자컴퓨터/양자통신/양자센서", "AI 가속기 등 전용 반도체"],
        excludes=["반도체가 탑재되는 응용 소프트웨어·서비스 자체(→ 해당 응용 분야)"],
        boundary_cases=["'AI 반도체 수출통제'는 규제 대상이 반도체 품목이므로 SEMI로 분류한다(AI 모델 규제가 아님)"],
        keywords=[
            (3.0, "semiconductor"), (3.0, "반도체"), (2.5, "quantum computing"), (2.5, "양자"), (2.0, "chip"),
            (1.5, "foundry"), (1.5, "파운드리"), (1.5, "export control"), (1.0, "공급망"),
        ],
        administrative_boilerplate=["agency information collection activities"],
    ),
    FieldCode.CONV: FieldDefinition(
        code=FieldCode.CONV,
        name_ko="ICT 융합기술",
        definition=(
            "스마트헬스·스마트시티·스마트제조·스마트농업·스마트국방·스마트재난안전·탄소중립 등 "
            "ICT를 다른 산업·공공영역에 융합해 적용하는 정책·기술. '범부처 신기술 융합 정책' 성격의 "
            "문서도 여기 포함한다."
        ),
        includes=["스마트시티·스마트제조·스마트농업·스마트국방·스마트재난안전", "탄소중립·그린ICT", "범부처 과학기술정책 중 특정 응용에 한정되지 않는 융합기술 전략"],
        excludes=["단일 기술(AI, 반도체 등) 자체가 중심이면 해당 분야로 우선 분류하고, 여러 산업에 걸친 '융합' 자체가 주제일 때만 CONV를 쓴다"],
        boundary_cases=[
            "'OSTP의 범부처 신흥기술 전략'처럼 특정 산업 하나로 좁혀지지 않는 횡단적 과학기술정책은 CONV로 분류한다",
            "'스마트시티용 AI 신호제어 시스템'처럼 특정 기술(AI)이 명확히 중심이면 AI를 주분야로, CONV를 연관분야로 둘 수 있다",
        ],
        keywords=[
            (3.0, "smart city"), (3.0, "스마트시티"), (2.5, "smart manufacturing"), (2.5, "스마트제조"),
            (2.0, "carbon neutral"), (2.0, "탄소중립"), (2.0, "convergence"), (1.5, "융합"), (1.5, "emerging technology"),
        ],
        administrative_boilerplate=["agency information collection activities"],
    ),
}


def get_field_definition(code: FieldCode) -> FieldDefinition:
    return FIELD_DEFINITIONS[code]


def taxonomy_as_prompt_context() -> str:
    """AI 분류 프롬프트에 그대로 주입할 분야 정의 텍스트 — 키워드가 아니라 정의/포함/제외/경계 사례 전체를 준다."""
    lines: list[str] = []
    for d in FIELD_DEFINITIONS.values():
        lines.append(f"[{d.code.value}] {d.name_ko}")
        lines.append(f"  정의: {d.definition}")
        lines.append(f"  포함: {'; '.join(d.includes)}")
        lines.append(f"  제외: {'; '.join(d.excludes)}")
        if d.boundary_cases:
            lines.append(f"  경계 사례: {'; '.join(d.boundary_cases)}")
    return "\n".join(lines)
