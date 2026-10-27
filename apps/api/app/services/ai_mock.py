"""개발·자동 테스트 전용 모의 AI 공급자 — 실제 AI가 아니다.

AI_PROVIDER=mock 과 AI_ALLOW_MOCK=1 을 함께 지정해야만 켜지며, 저장되는 분석에는 provider="mock"·is_mock=True가 남고
화면에는 '모의 응답(테스트용)'이 표시된다. 프롬프트에 들어 있는 원문에서 문장을 그대로 발췌해 결과 구조를 채우므로
근거 검증 로직(발췌 존재·날짜·수치 대조)을 실제와 같은 경로로 시험할 수 있다. 사실을 새로 만들어내지 않는다.
AI_MOCK_FLAWS=1 이면 검증 실패를 시연하기 위해 일부러 틀린 문장(없는 날짜·없는 발췌문)을 하나씩 섞는다.
"""

import json
import os
import re

from app.services.ai_service import AIResult

DOC_RE = re.compile(r'<document id="(D\d+)"[^>]*>\n(.*?)\n</document>', re.S)
SPEC_RE = re.compile(r"<<SPEC>>(.*?)<<END>>", re.S)
SENT_SPLIT = re.compile(r"(?<=[.!?。])\s+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_SPLIT.split(text.replace("\n", " ")) if 40 <= len(s.strip()) <= 260]


class MockProvider:
    name = "mock"
    model = "mock-extractive-v1"

    def complete_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> AIResult:
        docs = {m.group(1): m.group(2) for m in DOC_RE.finditer(user_prompt)}
        spec_m = SPEC_RE.search(user_prompt)
        if not spec_m:  # 분류·구조화 추출 등 기존 서비스의 호출은 모의 응답으로 대체하지 않고 규칙 기반 폴백을 쓰게 한다
            from app.services.ai_service import AIServiceError

            raise AIServiceError("모의 공급자는 3-6 AI 분석 전용입니다(다른 호출은 규칙 기반으로 대체됨)")
        sections = json.loads(spec_m.group(1))
        sents = {d: _sentences(t) for d, t in docs.items()}
        flaws = os.environ.get("AI_MOCK_FLAWS", "") == "1"
        out_sections = []
        cursor = {d: 0 for d in docs}
        doc_ids = list(docs)
        for sec in sections:
            items = []
            n_items = 1 if sec["key"] in ("title_ko", "title_en") else 2
            for k in range(n_items):
                d = doc_ids[(len(out_sections) + k) % len(doc_ids)] if doc_ids else None
                if d is None or not sents.get(d):
                    continue
                s = sents[d][cursor[d] % len(sents[d])]
                cursor[d] += 1
                evidence = [{"doc": d, "quote": s}]
                if sec["key"] in ("disputes", "country_comparison") and len(doc_ids) >= 2:
                    d2 = doc_ids[(doc_ids.index(d) + 1) % len(doc_ids)]
                    if sents.get(d2):
                        evidence.append({"doc": d2, "quote": sents[d2][0]})
                kind = "interpretation" if sec.get("interpretation") else "fact"
                text = f"[모의] {s}" if kind == "fact" else f"[모의 해석] 원문 내용을 바탕으로 한 시사점 예시임."
                items.append({"text": text, "type": kind, "evidence": evidence if kind == "fact" else []})
            if sec["key"] in ("to_verify", "further_research", "monitoring"):
                items.append({"text": "[모의] 최신 시행일·후속 조치 여부는 공식 관보에서 추가 확인이 필요함.", "type": "gap", "evidence": []})
            out_sections.append({"key": sec["key"], "items": items})
        if flaws and out_sections and doc_ids and sents.get(doc_ids[0]):
            first = out_sections[0]["items"]
            first.append({"text": "[모의-검증실패 시연] 시행일은 2099.1.1.임.", "type": "fact", "evidence": [{"doc": doc_ids[0], "quote": sents[doc_ids[0]][0]}]})
            first.append({"text": "[모의-검증실패 시연] 원문에 없는 문장을 근거로 제시함.", "type": "fact",
                          "evidence": [{"doc": doc_ids[0], "quote": "This sentence was never written in the source document at all."}]})
        payload = {"sections": out_sections, "insufficient": False, "notes": ["모의 응답(테스트용) — 실제 AI 분석이 아님"]}
        text = json.dumps(payload, ensure_ascii=False)
        return AIResult(provider=self.name, model=self.model, text=text, input_tokens=len(user_prompt) // 3, output_tokens=len(text) // 3)
