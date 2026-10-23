import { Mark, mergeAttributes } from "@tiptap/core";

export interface FootnoteMarkOptions {
  HTMLAttributes: Record<string, unknown>;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    footnoteMark: {
      setFootnoteMark: (footnoteId: string) => ReturnType;
      unsetFootnoteMark: () => ReturnType;
    };
  }
}

// 원고 본문의 문장 ↔ 각주(ManuscriptFootnote) 연결 마크. footnoteId만 저장하고 번호는
// 문서 내 등장 순서로 매번 다시 계산한다(문단 이동·삭제 후에도 번호가 어긋나지 않도록).
export const FootnoteMark = Mark.create<FootnoteMarkOptions>({
  name: "footnoteMark",

  addOptions() {
    return { HTMLAttributes: {} };
  },

  addAttributes() {
    return {
      footnoteId: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-footnote-id"),
        renderHTML: (attributes) => {
          if (!attributes.footnoteId) return {};
          return { "data-footnote-id": attributes.footnoteId };
        },
      },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-footnote-id]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, { class: "footnote-ref" }), 0];
  },

  addCommands() {
    return {
      setFootnoteMark:
        (footnoteId: string) =>
        ({ commands }) =>
          commands.setMark(this.name, { footnoteId }),
      unsetFootnoteMark:
        () =>
        ({ commands }) =>
          commands.unsetMark(this.name),
    };
  },
});

export function collectFootnoteOrder(doc: import("@tiptap/pm/model").Node): string[] {
  const order: string[] = [];
  doc.descendants((node) => {
    node.marks.forEach((mark) => {
      if (mark.type.name === "footnoteMark" && mark.attrs.footnoteId) {
        const id = mark.attrs.footnoteId as string;
        if (!order.includes(id)) order.push(id);
      }
    });
  });
  return order;
}
