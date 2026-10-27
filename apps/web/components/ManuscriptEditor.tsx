"use client";

import { useEditor, EditorContent, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import Link from "@tiptap/extension-link";
import { TableKit } from "@tiptap/extension-table/kit";
import { Table } from "@tiptap/extension-table";
import { useEffect } from "react";
import { FootnoteMark } from "@/lib/footnoteMark";
import { AiInsertMark } from "@/lib/aiInsertMark";

// 표 제목(caption) 속성: 출력 시 "[표 n-m] 제목"으로 인쇄된다
const CaptionTable = Table.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      caption: {
        default: null,
        parseHTML: (el: HTMLElement) => el.getAttribute("data-caption"),
        renderHTML: (attrs: Record<string, unknown>) => (attrs.caption ? { "data-caption": String(attrs.caption) } : {}),
      },
    };
  },
});

export default function ManuscriptEditor({
  initialJson,
  editable,
  onUpdate,
  onEditorReady,
  onFootnoteClick,
}: {
  initialJson: string | null;
  editable: boolean;
  onUpdate: (json: string, text: string) => void;
  onEditorReady: (editor: Editor) => void;
  onFootnoteClick?: (footnoteMarkId: string) => void;
}) {
  let initialContent: unknown = "";
  if (initialJson) {
    try {
      initialContent = JSON.parse(initialJson);
    } catch {
      initialContent = "";
    }
  }

  const editor = useEditor({
    extensions: [
      StarterKit,
      Underline,
      Link.configure({ openOnClick: false, autolink: true }),
      TableKit.configure({ table: false }),
      CaptionTable.configure({ resizable: false }),
      FootnoteMark,
      AiInsertMark,
    ],
    content: initialContent || "<p></p>",
    editable,
    immediatelyRender: false,
    editorProps: {
      // 본문의 각주 번호([n])를 누르면 오른쪽 패널에서 해당 근거(원문·발췌·검증 상태)를 보여준다
      handleClick: (_view, _pos, event) => {
        const el = (event.target as HTMLElement | null)?.closest?.(".footnote-ref");
        const id = el?.getAttribute("data-footnote-id");
        if (id && onFootnoteClick) onFootnoteClick(id);
        return false;
      },
    },
    onUpdate: ({ editor }) => {
      // 읽기 전용(승인 후·권한 없음)으로 전환될 때 발생하는 갱신은 사용자 수정이 아니므로 저장하지 않는다
      if (!editor.isEditable) return;
      onUpdate(JSON.stringify(editor.getJSON()), editor.getText());
    },
  });

  useEffect(() => {
    if (editor) onEditorReady(editor);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editor]);

  useEffect(() => {
    if (editor) editor.setEditable(editable, false); // false: 편집 가능 여부 전환만으로 update(=자동저장)를 일으키지 않는다
  }, [editor, editable]);

  if (!editor) return <div style={{ padding: 12, color: "var(--ink-muted)" }}>편집기 로딩 중...</div>;

  return (
    <div>
      <div style={toolbarStyle}>
        <button type="button" className="tbtn" onClick={() => editor.chain().focus().toggleBold().run()} disabled={!editable}>굵게</button>
        <button type="button" className="tbtn" onClick={() => editor.chain().focus().toggleItalic().run()} disabled={!editable}>기울임</button>
        <button type="button" className="tbtn" onClick={() => editor.chain().focus().toggleUnderline().run()} disabled={!editable}>밑줄</button>
        <button type="button" className="tbtn" onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} disabled={!editable}>H1</button>
        <button type="button" className="tbtn" onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} disabled={!editable}>H2</button>
        <button type="button" className="tbtn" onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()} disabled={!editable}>H3</button>
        <button type="button" className="tbtn" onClick={() => editor.chain().focus().toggleBulletList().run()} disabled={!editable}>글머리표</button>
        <button type="button" className="tbtn" onClick={() => editor.chain().focus().toggleOrderedList().run()} disabled={!editable}>번호목록</button>
        <button
          type="button"
          className="tbtn"
          disabled={!editable}
          onClick={() => {
            const url = window.prompt("링크 URL을 입력하세요");
            if (url) editor.chain().focus().setLink({ href: url }).run();
          }}
        >
          링크
        </button>
        <button
          type="button"
          className="tbtn"
          disabled={!editable}
          onClick={() => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()}
        >
          표 삽입
        </button>
        <button
          type="button"
          className="tbtn"
          disabled={!editable}
          title="커서가 놓인 표의 제목을 입력합니다"
          onClick={() => {
            if (!editor.isActive("table")) { window.alert("제목을 입력할 표 안에 커서를 놓아 주세요"); return; }
            const current = (editor.getAttributes("table").caption as string | null) ?? "";
            const value = window.prompt("표 제목을 입력하세요(비우면 번호만 표시)", current);
            if (value !== null) editor.chain().focus().updateAttributes("table", { caption: value.trim() || null }).run();
          }}
        >
          표 제목
        </button>
        <button type="button" className="tbtn" onClick={() => editor.chain().focus().undo().run()} disabled={!editable}>실행취소</button>
        <button type="button" className="tbtn" onClick={() => editor.chain().focus().redo().run()} disabled={!editable}>다시실행</button>
      </div>
      <div style={editorWrapStyle}>
        <EditorContent editor={editor} />
      </div>
    </div>
  );
}

const toolbarStyle: React.CSSProperties = {
  display: "flex", flexWrap: "wrap", gap: 6, padding: "8px 0", borderBottom: "1px solid var(--border)", marginBottom: 10,
};

const editorWrapStyle: React.CSSProperties = {
  minHeight: 420, fontSize: 14, lineHeight: 1.7,
};
