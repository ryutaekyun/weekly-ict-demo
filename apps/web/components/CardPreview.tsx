"use client";

import type { CnScene } from "@/lib/cardNewsApi";

const PT_PER_CM = 28.3465;

// PPTX를 만드는 것과 같은 장면(scene) 데이터를 HTML로 그린다 — 편집 중 미리보기용. 최종 확인은 출력된 PPTX/PNG로 한다.
export default function CardPreview({
  scene, widthPx, selectedKey, onSelect, label,
}: {
  scene: CnScene; widthPx: number; selectedKey?: string | null; onSelect?: (key: string) => void; label?: string;
}) {
  const s = widthPx / scene.width; // cm → px
  const px = (cm: number) => cm * s;
  const font = (pt: number) => (pt / PT_PER_CM) * s;
  const heightPx = scene.height * s;

  return (
    <div
      role="img"
      aria-label={label ?? "카드 미리보기"}
      style={{ position: "relative", width: widthPx, height: heightPx, background: `#${scene.background}`, overflow: "hidden", borderRadius: 6,
        boxShadow: "0 1px 6px rgba(0,0,0,0.25)", fontFamily: "'Malgun Gothic','Noto Sans KR','Apple SD Gothic Neo',sans-serif", flexShrink: 0 }}
    >
      {scene.items.map((it, idx) => {
        if (it.type === "rect") {
          return <div key={idx} style={{ position: "absolute", left: px(it.x), top: px(it.y), width: px(it.w), height: px(it.h),
            background: it.fill ? `#${it.fill}` : "transparent", border: it.line ? `1px solid #${it.line}` : undefined,
            borderRadius: it.radius ? px(Math.min(it.radius, Math.min(it.w, it.h) / 2)) : 0, boxSizing: "border-box" }} />;
        }
        if (it.type === "ellipse") {
          return <div key={idx} style={{ position: "absolute", left: px(it.x), top: px(it.y), width: px(it.w), height: px(it.h),
            background: `#${it.fill}`, borderRadius: "50%" }} />;
        }
        if (it.type === "line") {
          const vertical = Math.abs(it.x1 - it.x2) < 0.001;
          const w = Math.max((it.width_pt / PT_PER_CM) * s, 1);
          return <div key={idx} style={vertical
            ? { position: "absolute", left: px(it.x1) - w / 2, top: px(Math.min(it.y1, it.y2)), width: w, height: px(Math.abs(it.y2 - it.y1)), background: `#${it.color}` }
            : { position: "absolute", left: px(Math.min(it.x1, it.x2)), top: px(it.y1) - w / 2, width: px(Math.abs(it.x2 - it.x1)), height: w, background: `#${it.color}` }} />;
        }
        if (it.type === "text") {
          const selected = it.key && it.key === selectedKey;
          return (
            <div
              key={idx}
              data-key={it.key ?? undefined}
              onClick={it.key && onSelect ? () => onSelect(it.key) : undefined}
              style={{
                position: "absolute", left: px(it.x), top: px(it.y), width: px(it.w), height: px(it.h), boxSizing: "border-box",
                padding: `${px(0.05)}px ${px(0.08)}px`, display: "flex", flexDirection: "column",
                justifyContent: it.valign === "middle" ? "center" : it.valign === "bottom" ? "flex-end" : "flex-start",
                color: `#${it.color}`, fontSize: font(it.size), fontWeight: it.bold ? 700 : 400, lineHeight: it.spacing ?? 1.2,
                textAlign: it.align, whiteSpace: "pre-wrap", wordBreak: "keep-all", overflowWrap: "anywhere",
                cursor: it.key && onSelect ? "pointer" : "default", fontStyle: it.placeholder ? "italic" : "normal",
                outline: selected ? "2px solid #5CAD8E" : it.key && onSelect ? "1px dashed rgba(92,173,142,0.0)" : undefined,
              }}
            >
              {it.text}
            </div>
          );
        }
        if (it.type === "table") {
          return (
            <table key={idx} style={{ position: "absolute", left: px(it.x), top: px(it.y), width: px(it.w), borderCollapse: "collapse", tableLayout: "fixed" }}>
              <colgroup>{it.col_widths.map((w: number, c: number) => <col key={c} style={{ width: px(w) }} />)}</colgroup>
              <tbody>
                {it.rows.map((row: any, r: number) => (
                  <tr key={r} style={{ height: px(row.h) }}>
                    {row.cells.map((cell: any, c: number) => (
                      <td key={c} onClick={cell.key && onSelect ? () => onSelect(cell.key) : undefined}
                        style={{ background: `#${cell.fill}`, color: `#${cell.color}`, fontSize: font(cell.size), fontWeight: cell.bold ? 700 : 400,
                          textAlign: cell.align, border: `1px solid #${it.border}`, padding: `${px(0.08)}px ${px(0.12)}px`, verticalAlign: "middle",
                          whiteSpace: "pre-wrap", wordBreak: "keep-all", cursor: cell.key && onSelect ? "pointer" : "default",
                          fontStyle: cell.placeholder ? "italic" : "normal", overflow: "hidden",
                          outline: cell.key && cell.key === selectedKey ? "2px solid #5CAD8E" : undefined }}>
                        {cell.text}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          );
        }
        if (it.type === "chart") {
          const max = Math.max(...it.values, 1);
          const barW = px(it.w) / (it.values.length * 1.6);
          const base = px(it.h) - font(9) * 2.6;
          return (
            <svg key={idx} onClick={onSelect ? () => onSelect("chart") : undefined} style={{ position: "absolute", left: px(it.x), top: px(it.y), cursor: onSelect ? "pointer" : "default" }}
              width={px(it.w)} height={px(it.h)} aria-label="막대 그래프">
              {it.title && <text x={px(it.w) / 2} y={font(10)} textAnchor="middle" fontSize={font(8.5)} fontWeight={700} fill={`#${it.navy}`}>{it.title}</text>}
              {it.values.map((v: number, i: number) => {
                const x = (px(it.w) / it.values.length) * (i + 0.5);
                const h = ((base - font(14)) * v) / max;
                return (
                  <g key={i}>
                    <rect x={x - barW / 2} y={base - h} width={barW} height={h} fill={`#${it.color}`} />
                    <text x={x} y={base - h - 3} textAnchor="middle" fontSize={font(8)} fontWeight={700}>{v}</text>
                    <text x={x} y={base + font(10)} textAnchor="middle" fontSize={font(8)}>{it.categories[i]}</text>
                  </g>
                );
              })}
              <line x1={0} x2={px(it.w)} y1={base} y2={base} stroke="#9AA3B2" />
            </svg>
          );
        }
        return null;
      })}
    </div>
  );
}
