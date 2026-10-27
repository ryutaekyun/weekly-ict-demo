import { Mark, mergeAttributes } from "@tiptap/core";

// AI가 제안해 연구원이 삽입한 문장 표시 — insertionId로 삽입 기록(원문 버전·AI 원문)과 연결한다. 검증 완료를 뜻하지 않는다.
export const AiInsertMark = Mark.create({
  name: "aiInsert",
  inclusive: false, // 표시된 문장 뒤에 연구원이 이어서 쓰는 글자는 AI 표시가 붙지 않게 한다
  addAttributes() {
    return {
      insertionId: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-ai-insertion"),
        renderHTML: (attrs) => (attrs.insertionId ? { "data-ai-insertion": attrs.insertionId } : {}),
      },
    };
  },
  parseHTML() {
    return [{ tag: "span[data-ai-insertion]" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes(HTMLAttributes, { class: "ai-inserted", title: "AI 제안 문장(연구원 검토용 초안 · 자동 검증 아님)" }), 0];
  },
});
