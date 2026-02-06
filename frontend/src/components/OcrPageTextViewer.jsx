import React, { useMemo, useState } from "react";

function buildPageText(p) {
  if (p && typeof p.text === "string" && p.text.trim().length) return p.text;
  if (p && Array.isArray(p.words) && p.words.length) return p.words.map((w) => w.text).join(" ");
  return "";
}

function downloadText(filename, content) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function safeBaseName(name) {
  const n = (name || "file").replace(/\.[^/.]+$/, "");
  return n.replace(/[^a-zA-Z0-9._-]+/g, "_").slice(0, 80) || "file";
}

export default function OcrPageTextViewer() {
  const [files, setFiles] = useState([]); // File[]
  const [results, setResults] = useState([]); // [{fileName, data}]
  const [selectedFileIdx, setSelectedFileIdx] = useState(0);
  const [pageIdx, setPageIdx] = useState(0);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // ✅ Your real backend endpoint (single-file)
  const OCR_URL = "http://127.0.0.1:8000/api/v1/ocr/extract";

  const selected = results[selectedFileIdx] || null;
  const data = selected ? selected.data : null;
  const pages = (data && data.pages) || [];
  const page = pages[pageIdx];

  const fullText = useMemo(() => {
    if (!data) return "";
    if (typeof data.full_text === "string" && data.full_text.trim().length) return data.full_text;
    return pages.map((p) => buildPageText(p)).join("\n\n");
  }, [data, pages]);

  const pageText = useMemo(() => (page ? buildPageText(page) : ""), [page]);

  async function runOcrForAll() {
    if (!files.length) return;
    setLoading(true);
    setError(null);
    setResults([]);
    setSelectedFileIdx(0);
    setPageIdx(0);

    try {
      const out = [];
      for (const f of files) {
        const form = new FormData();
        form.append("file", f);

        const res = await fetch(OCR_URL, { method: "POST", body: form });
        if (!res.ok) throw new Error(`${f.name}: OCR failed: ${res.status} ${res.statusText}`);

        const json = await res.json();
        out.push({ fileName: f.name, data: json });
      }
      setResults(out);
    } catch (e) {
      setError(e && e.message ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  function onPickFiles(e) {
    const picked = Array.from((e.target.files && e.target.files) || []);
    setFiles(picked);
  }

  function downloadSelectedFullTxt() {
    if (!selected || !data) return;
    const base = safeBaseName(selected.fileName);
    downloadText(`${base}_ocr_output.txt`, fullText);
  }

  function downloadSelectedPageTxt() {
    if (!selected || !page) return;
    const base = safeBaseName(selected.fileName);
    const pn = (page && page.page_number) || pageIdx + 1;
    downloadText(`${base}_page_${pn}.txt`, pageText);
  }

  return (
    <div style={{ padding: 16, maxWidth: 1300, margin: "0 auto" }}>
      <div style={{ fontSize: 26, fontWeight: 800, marginBottom: 14 }}>OCR Result (Multi-file → Page-wise + TXT)</div>

      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 10, flexWrap: "wrap" }}>
        <input
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.docx"
          onChange={onPickFiles}
        />

        <button
          onClick={runOcrForAll}
          disabled={!files.length || loading}
          style={{
            padding: "10px 14px",
            borderRadius: 10,
            border: "1px solid #ccc",
            cursor: !files.length || loading ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "Running..." : `Run OCR (${files.length || 0} files)`}
        </button>

        <button
          onClick={downloadSelectedFullTxt}
          disabled={!data}
          style={{
            padding: "10px 14px",
            borderRadius: 10,
            border: "1px solid #ccc",
            cursor: !data ? "not-allowed" : "pointer",
          }}
        >
          Download TXT (Selected File)
        </button>

        <button
          onClick={downloadSelectedPageTxt}
          disabled={!page}
          style={{
            padding: "10px 14px",
            borderRadius: 10,
            border: "1px solid #ccc",
            cursor: !page ? "not-allowed" : "pointer",
          }}
        >
          Download Page TXT (Selected File)
        </button>
      </div>

      {error ? <div style={{ marginBottom: 10, color: "crimson", fontWeight: 600 }}>{error}</div> : null}

      {!results.length ? (
        <div style={{ color: "#666", marginTop: 10 }}>
          Select multiple files (Ctrl/Shift) and click Run OCR.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "300px 260px 1fr", gap: 16, marginTop: 14 }}>
          {/* Left: File list */}
          <div style={{ border: "1px solid #ddd", borderRadius: 12, padding: 10, height: "70vh", overflow: "auto" }}>
            <div style={{ fontWeight: 800, marginBottom: 10 }}>Files</div>
            {results.map((r, i) => (
              <button
                key={`${r.fileName}-${i}`}
                onClick={() => {
                  setSelectedFileIdx(i);
                  setPageIdx(0);
                }}
                style={{
                  width: "100%",
                  textAlign: "left",
                  padding: "10px 10px",
                  marginBottom: 8,
                  borderRadius: 10,
                  border: "1px solid #ccc",
                  background: i === selectedFileIdx ? "#f2f2f2" : "white",
                  cursor: "pointer",
                }}
                title={r.fileName}
              >
                {r.fileName}
              </button>
            ))}
          </div>

          {/* Middle: Page list */}
          <div style={{ border: "1px solid #ddd", borderRadius: 12, padding: 10, height: "70vh", overflow: "auto" }}>
            <div style={{ fontWeight: 800, marginBottom: 10 }}>Pages</div>
            {pages.map((p, i) => (
              <button
                key={`${p.page_number || i + 1}-${i}`}
                onClick={() => setPageIdx(i)}
                style={{
                  width: "100%",
                  textAlign: "left",
                  padding: "10px 10px",
                  marginBottom: 8,
                  borderRadius: 10,
                  border: "1px solid #ccc",
                  background: i === pageIdx ? "#f2f2f2" : "white",
                  cursor: "pointer",
                }}
              >
                Page {p.page_number || i + 1}
              </button>
            ))}
          </div>

          {/* Right: page text + raw json */}
          <div style={{ display: "grid", gridTemplateRows: "1fr 260px", gap: 12 }}>
            <div style={{ border: "1px solid #ddd", borderRadius: 12, padding: 12, height: "calc(70vh - 272px)", overflow: "auto" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <div style={{ fontWeight: 800 }}>
                  Page Text {page ? `(Page ${page.page_number || pageIdx + 1})` : ""}
                </div>
              </div>
              <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
                {pageText || "(No text extracted for this page)"}
              </pre>
            </div>

            <div style={{ border: "1px solid #ddd", borderRadius: 12, padding: 12, overflow: "auto" }}>
              <div style={{ fontWeight: 800, marginBottom: 10 }}>Raw JSON (Selected File)</div>
              <pre style={{ margin: 0, fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
                {JSON.stringify(data, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
