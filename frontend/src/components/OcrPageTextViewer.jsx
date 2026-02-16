import React, { useMemo, useState } from "react";

/**
 * Drop-in replacement for: frontend/src/components/OcrPageTextViewer.jsx
 *
 * What it adds:
 * - Renders Phase 3 top-level `document`:
 *    - Markdown view: response.document.markdown
 *    - Structured Blocks view: response.document.pages[].blocks[]
 * - Keeps existing views:
 *    - Page Text (Phase 2/3 text)
 *    - Raw JSON
 * - Better error reporting: shows FastAPI {detail:"..."} on non-2xx
 *
 * Assumptions:
 * - Backend endpoint: POST http://127.0.0.1:8000/api/v1/ocr/extract
 * - Form fields: file, document_type, zero_retention
 */

const API_URL = "http://127.0.0.1:8000/api/v1/ocr/extract";

function prettyJson(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

function safeGet(obj, path, fallback = undefined) {
  try {
    return path.split(".").reduce((acc, key) => (acc ? acc[key] : undefined), obj) ?? fallback;
  } catch {
    return fallback;
  }
}

export default function OcrPageTextViewer() {
  const [files, setFiles] = useState([]);
  const [documentType, setDocumentType] = useState("generic");
  const [zeroRetention, setZeroRetention] = useState(true);

  const [results, setResults] = useState([]); // [{filename, response, error}]
  const [activeIndex, setActiveIndex] = useState(0);
  const [activePage, setActivePage] = useState(1);

  const [viewMode, setViewMode] = useState("markdown"); // markdown | blocks | tables | page | diagnostics | raw
  const [running, setRunning] = useState(false);

  const active = results[activeIndex]?.response || null;
  const activeErr = results[activeIndex]?.error || null;

  const pages = useMemo(() => {
    const ps = active?.pages || [];
    return Array.isArray(ps) ? ps : [];
  }, [active]);

  const maxPages = pages.length || 1;

  const docModel = active?.document || null;
  const docMarkdown = docModel?.markdown || "";
  const docPages = Array.isArray(docModel?.pages) ? docModel.pages : [];
  const docTables = Array.isArray(docModel?.tables) ? docModel.tables : [];

  const blockView = useMemo(() => {
    if (!docPages.length) return [];
    // Find matching page_number, else take first
    const match = docPages.find((p) => p.page_number === activePage) || docPages[0];
    return Array.isArray(match?.blocks) ? match.blocks : [];
  }, [docPages, activePage]);

  async function runOcrForAll() {
    if (!files.length) {
      setResults([{ filename: "", response: null, error: "No files selected." }]);
      return;
    }

    setRunning(true);
    setResults([]);
    setActiveIndex(0);
    setActivePage(1);

    const next = [];

    for (const f of files) {
      const formData = new FormData();
      formData.append("file", f);
      formData.append("document_type", documentType);
      formData.append("zero_retention", String(zeroRetention));

      try {
        const res = await fetch(API_URL, { method: "POST", body: formData });

        let body = null;
        let text = "";
        const ct = res.headers.get("content-type") || "";

        if (ct.includes("application/json")) {
          body = await res.json();
        } else {
          text = await res.text();
        }

        if (!res.ok) {
          const detail =
            body?.detail ||
            body?.message ||
            (typeof body === "string" ? body : "") ||
            text ||
            `${res.status} ${res.statusText}`;
          next.push({ filename: f.name, response: null, error: `OCR failed: ${res.status} ${res.statusText} — ${detail}` });
        } else {
          next.push({ filename: f.name, response: body, error: null });
        }
      } catch (e) {
        next.push({ filename: f.name, response: null, error: `OCR failed: ${String(e?.message || e)}` });
      }
    }

    setResults(next);
    setRunning(false);

    // Default view preference:
    // If document.markdown exists -> markdown, else page
    const firstOk = next.find((x) => x.response);
    if (firstOk?.response?.document?.markdown) setViewMode("markdown");
    else setViewMode("page");
  }

  function onFilesChange(e) {
    const fs = Array.from(e.target.files || []);
    setFiles(fs);
  }

  function renderTabs() {
    const hasDocument = !!active?.document;
    const hasMarkdown = !!active?.document?.markdown;
    const hasTables = Array.isArray(active?.document?.tables) && active.document.tables.length > 0;
    const hasPageMeta = !!pages?.length;
    return (
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        <button onClick={() => setViewMode("page")} disabled={!active}>
          Page Text
        </button>
        <button onClick={() => setViewMode("diagnostics")} disabled={!active || !hasPageMeta}>
          Diagnostics
        </button>
        <button onClick={() => setViewMode("raw")} disabled={!active}>
          Raw JSON
        </button>
        <button onClick={() => setViewMode("markdown")} disabled={!active || !hasMarkdown}>
          Markdown
        </button>
        <button onClick={() => setViewMode("blocks")} disabled={!active || !hasDocument}>
          Blocks
        </button>
        <button onClick={() => setViewMode("tables")} disabled={!active || !hasTables}>
          Tables
        </button>
      </div>
    );
  }

  function renderTableGrid(table) {
    const nRows = Number(table?.n_rows || 0);
    const nCols = Number(table?.n_cols || 0);
    const cells = Array.isArray(table?.cells) ? table.cells : [];
    if (!nRows || !nCols) return <div>Invalid table.</div>;

    const grid = Array.from({ length: nRows }, () => Array.from({ length: nCols }, () => ""));
    for (const c of cells) {
      const r = Number(c?.row || 0);
      const k = Number(c?.col || 0);
      if (r >= 0 && r < nRows && k >= 0 && k < nCols) {
        grid[r][k] = String(c?.text || "");
      }
    }

    return (
      <div style={{ overflowX: "auto", border: "1px solid #ddd", borderRadius: 8 }}>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <tbody>
            {grid.map((row, ri) => (
              <tr key={ri}>
                {row.map((val, ci) => (
                  <td key={ci} style={{ border: "1px solid #ddd", padding: 6, verticalAlign: "top" }}>
                    {val}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  function renderTables() {
    if (!active) return null;
    if (!docTables.length) return <div>No tables extracted.</div>;

    const pageTables = docTables.filter((t) => Number(t?.page_number) === Number(activePage));
    if (!pageTables.length) {
      return <div>No tables extracted on this page.</div>;
    }

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {pageTables.map((t, idx) => (
          <div key={`${t.page_number}-${t.source_block_index ?? idx}`} style={{ border: "1px solid #eee", borderRadius: 10, padding: 10 }}>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
              <div style={{ fontWeight: 700 }}>Table {idx + 1}</div>
              <div style={{ opacity: 0.8 }}>rows: {t.n_rows} cols: {t.n_cols}</div>
              {typeof t.score === "number" ? <div style={{ opacity: 0.8 }}>score: {t.score.toFixed(2)}</div> : null}
              <div style={{ opacity: 0.8 }}>method: {t.method || "heuristic"}</div>
            </div>
            {renderTableGrid(t)}
          </div>
        ))}
      </div>
    );
  }

  function renderHeader() {
    return (
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
        <input type="file" multiple onChange={onFilesChange} />
        <select value={documentType} onChange={(e) => setDocumentType(e.target.value)}>
          <option value="generic">generic</option>
          <option value="invoice">invoice</option>
          <option value="receipt">receipt</option>
          <option value="resume">resume</option>
        </select>
        <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <input type="checkbox" checked={zeroRetention} onChange={(e) => setZeroRetention(e.target.checked)} />
          zero_retention
        </label>
        <button onClick={runOcrForAll} disabled={running || !files.length}>
          {running ? "Running..." : "Run OCR"}
        </button>
      </div>
    );
  }

  function renderResultsList() {
    if (!results.length) return null;
    return (
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
        {results.map((r, idx) => {
          const ok = !!r.response;
          return (
            <button
              key={`${r.filename}-${idx}`}
              onClick={() => {
                setActiveIndex(idx);
                setActivePage(1);
              }}
              style={{
                border: idx === activeIndex ? "2px solid #444" : "1px solid #bbb",
                padding: "6px 10px",
                borderRadius: 8,
                background: ok ? "#fff" : "#ffecec",
                cursor: "pointer",
              }}
              title={ok ? "Success" : r.error || "Error"}
            >
              {r.filename || `file_${idx + 1}`} {ok ? "✅" : "❌"}
            </button>
          );
        })}
      </div>
    );
  }

  function renderPager() {
    if (!active) return null;
    return (
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
        <span style={{ fontWeight: 600 }}>Page:</span>
        <button onClick={() => setActivePage((p) => Math.max(1, p - 1))} disabled={activePage <= 1}>
          Prev
        </button>
        <span>
          {activePage} / {maxPages}
        </span>
        <button onClick={() => setActivePage((p) => Math.min(maxPages, p + 1))} disabled={activePage >= maxPages}>
          Next
        </button>

        <span style={{ marginLeft: 12, fontWeight: 600 }}>Meta:</span>
        <span style={{ fontFamily: "monospace", fontSize: 12 }}>
          phase2_complete={String(active?.metadata?.phase2_complete)} | phase3_complete={String(active?.metadata?.phase3_complete)}
        </span>
      </div>
    );
  }

  function renderActiveView() {
    if (activeErr && !active) {
      return (
        <div style={{ whiteSpace: "pre-wrap", color: "#b00020", background: "#fff3f3", padding: 12, borderRadius: 8 }}>
          {activeErr}
        </div>
      );
    }

    if (!active) return <div style={{ opacity: 0.8 }}>Select multiple files (Ctrl/Shift) and click Run OCR.</div>;

    if (viewMode === "diagnostics") {
      const page = pages.find((p) => p.page_number === activePage) || pages[0] || {};
      const engineUsage = page?.engine_usage || {};
      const diagnostics = page?.diagnostics || {};
      const docDiag = active?.document?.diagnostics || {};

      const hasAny =
        (engineUsage && Object.keys(engineUsage).length) ||
        (diagnostics && Object.keys(diagnostics).length) ||
        (docDiag && Object.keys(docDiag).length);

      if (!hasAny) {
        return <div style={{ opacity: 0.8 }}>No diagnostics/engine usage found in the response.</div>;
      }

      return (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ border: "1px solid #eee", borderRadius: 10, padding: 10 }}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>Page engine_usage (page {activePage})</div>
            <pre style={{ whiteSpace: "pre-wrap", background: "#f6f6f6", padding: 10, borderRadius: 8, margin: 0 }}>
              {prettyJson(engineUsage)}
            </pre>
            <div style={{ marginTop: 8, fontSize: 12, opacity: 0.9 }}>
              Quick read:
              <span style={{ fontFamily: "monospace" }}>
                {" "}
                trocr={String(engineUsage?.trocr)} (enabled={String(engineUsage?.trocr_enabled)}, available={String(engineUsage?.trocr_available)}, skip_reason={String(engineUsage?.trocr_skip_reason)})
              </span>
            </div>
          </div>

          <div style={{ border: "1px solid #eee", borderRadius: 10, padding: 10 }}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>Page diagnostics</div>
            <pre style={{ whiteSpace: "pre-wrap", background: "#f6f6f6", padding: 10, borderRadius: 8, margin: 0 }}>
              {prettyJson(diagnostics)}
            </pre>
          </div>

          <div style={{ border: "1px solid #eee", borderRadius: 10, padding: 10 }}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>Document diagnostics</div>
            <pre style={{ whiteSpace: "pre-wrap", background: "#f6f6f6", padding: 10, borderRadius: 8, margin: 0 }}>
              {prettyJson(docDiag)}
            </pre>
          </div>
        </div>
      );
    }

    if (viewMode === "raw") {
      return (
        <pre style={{ whiteSpace: "pre-wrap", background: "#f6f6f6", padding: 12, borderRadius: 8 }}>
          {prettyJson(active)}
        </pre>
      );
    }

    if (viewMode === "markdown") {
      const md = docMarkdown || "";
      if (!md) return <div style={{ opacity: 0.8 }}>No document.markdown available.</div>;
      return (
        <pre style={{ whiteSpace: "pre-wrap", background: "#f6f6f6", padding: 12, borderRadius: 8 }}>
          {md}
        </pre>
      );
    }

    if (viewMode === "tables") {
      if (!docModel) return <div style={{ opacity: 0.8 }}>No document model available.</div>;
      return renderTables();
    }

    if (viewMode === "blocks") {
      if (!docModel) return <div style={{ opacity: 0.8 }}>No document model available.</div>;
      if (!blockView.length) return <div style={{ opacity: 0.8 }}>No blocks found on this page.</div>;

      return (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {blockView.map((b, i) => {
            const type = b.type || "paragraph";
            const txt = (b.text_normalized || b.text || "").trim();
            return (
              <div key={i} style={{ border: "1px solid #ddd", borderRadius: 10, padding: 10 }}>
                <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                  <span style={{ fontWeight: 700 }}>{type}</span>
                  {b.table_candidate ? <span title="Heuristic table candidate">🧮 table_candidate</span> : null}
                  {b.script === "handwritten" ? (
                    <span title={`Handwriting score: ${typeof b.handwriting_score === "number" ? b.handwriting_score.toFixed(2) : "n/a"}`}>✍️ handwritten</span>
                  ) : null}
                  {b.script === "printed" ? <span title="Likely printed">🖨️ printed</span> : null}
                  {b.marker ? <span style={{ fontFamily: "monospace" }}>marker={b.marker}</span> : null}
                  {typeof b.level === "number" && b.level > 0 ? <span>level={b.level}</span> : null}
                </div>
                <div style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{txt || <i>(empty)</i>}</div>
              </div>
            );
          })}
        </div>
      );
    }

    // viewMode === "page"
    const page = pages.find((p) => p.page_number === activePage) || pages[0];
    const txt = (page?.text_normalized || page?.text || "").trim();
    if (!txt) return <div style={{ opacity: 0.8 }}>No text extracted for this page.</div>;

    return (
      <pre style={{ whiteSpace: "pre-wrap", background: "#f6f6f6", padding: 12, borderRadius: 8 }}>
        {txt}
      </pre>
    );
  }

  return (
    <div style={{ padding: 16, maxWidth: 1100, margin: "0 auto", fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Arial" }}>
      <h2 style={{ marginTop: 0 }}>OCR Viewer</h2>
      {renderHeader()}
      {renderResultsList()}
      {renderTabs()}
      {renderPager()}
      {renderActiveView()}
    </div>
  );
}


