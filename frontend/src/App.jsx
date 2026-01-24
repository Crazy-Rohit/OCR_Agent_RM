import { useState, useRef, useMemo, useEffect } from "react";
import { uploadDocuments } from "./api";

function App() {
  const [files, setFiles] = useState([]);
  const [docType, setDocType] = useState("generic");
  const [zeroRetention, setZeroRetention] = useState(true);

  // ✅ NEW: enable layout toggle
  const [enableLayout, setEnableLayout] = useState(true);

  const [batchResult, setBatchResult] = useState(null);
  const [activeIdx, setActiveIdx] = useState(0);
  const [loading, setLoading] = useState(false);

  const [activeTab, setActiveTab] = useState("full");
  const [layoutPageNumber, setLayoutPageNumber] = useState(1);

  // ✅ NEW: JSON toggle
  const [showJson, setShowJson] = useState(false);

  const [error, setError] = useState(null);
  const [isReading, setIsReading] = useState(false);
  const utteranceRef = useRef(null);

  const activeItem = useMemo(() => batchResult?.results?.[activeIdx] || null, [batchResult, activeIdx]);
  const activeResult = useMemo(() => activeItem?.response || null, [activeItem]);
  const activePages = useMemo(() => activeResult?.pages || [], [activeResult]);

  const selectedLayoutPage = useMemo(() => {
    return activePages.find((p) => p.page_number === layoutPageNumber) || null;
  }, [activePages, layoutPageNumber]);

  useEffect(() => {
    setLayoutPageNumber(1);
  }, [activeIdx]);

  const handleUpload = async () => {
    if (!files.length) {
      setError("Please choose at least 1 file.");
      return;
    }
    setError(null);
    setLoading(true);
    setBatchResult(null);
    setIsReading(false);
    setShowJson(false);
    window.speechSynthesis.cancel();

    try {
      const data = await uploadDocuments(files, docType, zeroRetention, enableLayout);
      setBatchResult(data);
      setActiveIdx(0);
      setActiveTab("full");
      setLayoutPageNumber(1);
      setShowJson(false);
    } catch (err) {
      console.error(err);
      setError(err?.response?.data?.detail || err?.message || "Something went wrong processing the file.");
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadTxt = () => {
    const result = activeResult;
    if (!result) return;

    const blob = new Blob([result.full_text || ""], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");

    const baseName = (result.metadata && result.metadata.file_name) || "ocr_output";
    a.href = url;
    a.download = baseName.replace(/\.[^/.]+$/, "") + "_ocr.txt";
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleStartReading = () => {
    const result = activeResult;
    if (!result || !result.full_text) return;

    if (!("speechSynthesis" in window)) {
      setError("Text-to-speech is not supported in this browser.");
      return;
    }

    window.speechSynthesis.cancel();

    const utter = new SpeechSynthesisUtterance(result.full_text);
    utter.lang = "en-US";
    utter.rate = 1;

    utter.onend = () => setIsReading(false);
    utter.onerror = () => setIsReading(false);

    utteranceRef.current = utter;
    setIsReading(true);
    window.speechSynthesis.speak(utter);
  };

  const handleStopReading = () => {
    window.speechSynthesis.cancel();
    setIsReading(false);
  };

  const bboxStr = (b) => {
    if (!b) return "";
    const { x1, y1, x2, y2 } = b;
    if ([x1, y1, x2, y2].some((v) => v === undefined || v === null)) return "";
    return `(${x1},${y1}) → (${x2},${y2})`;
  };

  const clip = (t, n = 180) => {
    const s = (t || "").replace(/\s+/g, " ").trim();
    if (s.length <= n) return s;
    return s.slice(0, n) + "…";
  };

  const copyJson = async () => {
    if (!batchResult) return;
    const text = JSON.stringify(batchResult, null, 2);
    try {
      await navigator.clipboard.writeText(text);
    } catch (e) {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
  };

  return (
    <div className="container">
      {/* Upload / controls */}
      <div className="card">
        <h2>OCR Agent – Phase 2 (Layout)</h2>
        <p style={{ fontSize: "0.9rem", color: "#6b7280" }}>
          Upload a PDF, image, or DOCX to extract text + optionally view layout (words/lines/blocks/tables).
        </p>

        <div style={{ marginTop: "12px" }}>
          <div className="label">Document file</div>
          <input
            type="file"
            multiple
            accept=".pdf,.docx,image/*"
            onChange={(e) => {
              const picked = Array.from(e.target.files || []);
              const map = new Map();
              for (const f of picked) {
                if (!map.has(f.name)) map.set(f.name, f);
              }
              setFiles(Array.from(map.values()));
            }}
          />
          <div style={{ fontSize: "0.75rem", color: "#6b7280", marginTop: 4 }}>
            Supported: PDF, DOCX, JPG, PNG, TIFF
          </div>
        </div>

        <div style={{ marginTop: "12px" }}>
          <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input type="checkbox" checked={zeroRetention} onChange={(e) => setZeroRetention(e.target.checked)} />
            Zero data retention (do not save uploads)
          </label>
        </div>

        {/* ✅ NEW */}
        <div style={{ marginTop: "10px" }}>
          <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input type="checkbox" checked={enableLayout} onChange={(e) => setEnableLayout(e.target.checked)} />
            Enable Layout (words/lines/blocks/tables)
          </label>
          <div style={{ fontSize: "0.75rem", color: "#6b7280", marginTop: 4 }}>
            Disable this if you only want text (smaller response, faster).
          </div>
        </div>

        <div style={{ marginTop: "12px" }}>
          <div className="label">Document type</div>
          <select
            value={docType}
            onChange={(e) => setDocType(e.target.value)}
            style={{
              marginTop: "4px",
              padding: "6px 8px",
              borderRadius: "6px",
              border: "1px solid #d1d5db",
            }}
          >
            <option value="generic">Generic</option>
            <option value="invoice">Invoice</option>
            <option value="bill">Utility Bill</option>
            <option value="claim">Claim Form</option>
          </select>
        </div>

        {error && <div className="error">{error}</div>}

        <button className="button" style={{ marginTop: "14px" }} disabled={loading} onClick={handleUpload}>
          {loading ? "Processing..." : "Extract Text"}
        </button>

        {batchResult && (
          <div className="meta">
            <div>Files processed: {batchResult.results?.length || 0}</div>
            <div>Zero retention: {String(batchResult.zero_retention)}</div>
            <div>Max allowed: {batchResult.max_docs_allowed}</div>
          </div>
        )}
      </div>

      {/* Output */}
      <div className="card">
        <h3 style={{ marginBottom: "8px" }}>OCR Output</h3>

        {batchResult?.results?.length > 0 && (
          <div style={{ marginBottom: 10 }}>
            <div className="label">Select file output</div>
            <select
              value={activeIdx}
              onChange={(e) => setActiveIdx(Number(e.target.value))}
              style={{
                marginTop: "4px",
                padding: "6px 8px",
                borderRadius: "6px",
                border: "1px solid #d1d5db",
                width: "100%",
              }}
            >
              {batchResult.results.map((r, idx) => (
                <option key={`${r.file_hash || idx}`} value={idx}>
                  {r.filename} {r.skipped_duplicate ? "(duplicate skipped)" : ""} {r.error ? "(error)" : ""}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="tabs">
          <button className={activeTab === "full" ? "active" : ""} onClick={() => setActiveTab("full")}>
            Full Text
          </button>
          <button className={activeTab === "pages" ? "active" : ""} onClick={() => setActiveTab("pages")}>
            Page-wise
          </button>
          <button className={activeTab === "layout" ? "active" : ""} onClick={() => setActiveTab("layout")}>
            Layout
          </button>
        </div>

        {activeTab === "layout" && activeResult && activePages.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <div className="label">Select page for layout</div>
            <select
              value={layoutPageNumber}
              onChange={(e) => setLayoutPageNumber(Number(e.target.value))}
              style={{
                marginTop: "4px",
                padding: "6px 8px",
                borderRadius: "6px",
                border: "1px solid #d1d5db",
                width: "100%",
              }}
            >
              {activePages.map((p) => (
                <option key={p.page_number} value={p.page_number}>
                  Page {p.page_number}
                </option>
              ))}
            </select>
          </div>
        )}

        <div
          style={{
            background: "#fafafa",
            padding: "12px",
            borderRadius: "8px",
            marginTop: "10px",
            height: "340px",
            overflow: "auto",
            whiteSpace: activeTab === "layout" ? "normal" : "pre-wrap",
            fontSize: "0.9rem",
          }}
        >
          {!batchResult && <span style={{ color: "#9ca3af" }}>No output yet.</span>}

          {batchResult &&
            (() => {
              const item = batchResult.results?.[activeIdx];
              if (!item) return null;
              if (item.error) return `Error: ${item.error}`;
              if (item.skipped_duplicate) return "Duplicate file skipped.";
              const result = item.response;
              if (!result) return "No result.";

              if (activeTab === "full") return result.full_text;

              if (activeTab === "pages") {
                return (
                  <>
                    {result.pages.map((p) => (
                      <div key={p.page_number} style={{ marginBottom: "12px" }}>
                        <div style={{ fontWeight: 600, fontSize: "0.8rem", marginBottom: "4px" }}>
                          Page {p.page_number}
                        </div>
                        <div>{p.text}</div>
                      </div>
                    ))}
                  </>
                );
              }

              // Layout tab
              const p = selectedLayoutPage;
              if (!p) return "No page selected.";

              const blocks = p.blocks || [];
              const lines = p.lines || [];
              const tables = p.tables || [];

              return (
                <div>
                  <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 10 }}>
                    <div className="pill">Lines: {lines.length}</div>
                    <div className="pill">Blocks: {blocks.length}</div>
                    <div className="pill">Tables: {tables.length}</div>
                  </div>

                  <details open>
                    <summary style={{ cursor: "pointer", fontWeight: 600 }}>Blocks</summary>
                    <div style={{ marginTop: 8 }}>
                      {blocks.length === 0 && <div style={{ color: "#6b7280" }}>No blocks found.</div>}
                      {blocks.map((b, i) => (
                        <div
                          key={i}
                          style={{
                            padding: "10px",
                            border: "1px solid #e5e7eb",
                            borderRadius: "8px",
                            marginBottom: "8px",
                            background: "white",
                          }}
                        >
                          <div style={{ fontSize: "0.78rem", color: "#6b7280" }}>
                            <b>#{i + 1}</b> · type: <b>{b.block_type || "text"}</b> · bbox: {bboxStr(b)}
                            {b.confidence !== undefined && b.confidence !== null ? (
                              <> · conf: {Number(b.confidence).toFixed(1)}</>
                            ) : null}
                          </div>
                          <div style={{ marginTop: 6 }}>{clip(b.text, 240)}</div>
                        </div>
                      ))}
                    </div>
                  </details>

                  <details style={{ marginTop: 10 }}>
                    <summary style={{ cursor: "pointer", fontWeight: 600 }}>Lines</summary>
                    <div style={{ marginTop: 8 }}>
                      {lines.length === 0 && <div style={{ color: "#6b7280" }}>No lines found.</div>}
                      {lines.map((l, i) => (
                        <div key={i} style={{ marginBottom: 6 }}>
                          <span style={{ fontSize: "0.78rem", color: "#6b7280" }}>
                            #{i + 1} · bbox: {bboxStr(l)}
                            {l.confidence !== undefined && l.confidence !== null ? (
                              <> · conf: {Number(l.confidence).toFixed(1)}</>
                            ) : null}
                          </span>
                          <div>{l.text}</div>
                        </div>
                      ))}
                    </div>
                  </details>

                  <details style={{ marginTop: 10 }}>
                    <summary style={{ cursor: "pointer", fontWeight: 600 }}>Tables</summary>
                    <div style={{ marginTop: 8 }}>
                      {tables.length === 0 && <div style={{ color: "#6b7280" }}>No tables detected.</div>}
                      {tables.map((t, i) => (
                        <div
                          key={i}
                          style={{
                            padding: "10px",
                            border: "1px solid #e5e7eb",
                            borderRadius: "8px",
                            marginBottom: "8px",
                            background: "white",
                          }}
                        >
                          <div style={{ fontSize: "0.78rem", color: "#6b7280" }}>
                            <b>#{i + 1}</b> · bbox: {bboxStr(t)}
                          </div>
                          <pre
                            style={{
                              marginTop: 8,
                              background: "#f9fafb",
                              padding: 10,
                              borderRadius: 8,
                              overflow: "auto",
                              whiteSpace: "pre-wrap",
                            }}
                          >
                            {t.text || ""}
                          </pre>
                            {t.rows && t.rows.length > 0 && (
  <div style={{ marginTop: 10 }}>
    <div style={{ fontSize: "0.78rem", color: "#6b7280", marginBottom: 6 }}>
      Structured table ({t.n_rows} rows × {t.n_cols} cols)
    </div>

    <div style={{ overflow: "auto" }}>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <tbody>
          {t.rows.map((row, ri) => (
            <tr key={ri}>
              {row.map((cell, ci) => (
                <td
                  key={ci}
                  style={{
                    border: "1px solid #e5e7eb",
                    padding: "6px",
                    verticalAlign: "top",
                    fontSize: "0.85rem",
                  }}
                >
                  {cell || ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
)}



                        </div>
                      ))}
                    </div>
                  </details>
                </div>
              );
            })()}
        </div>

        <div style={{ marginTop: "10px", display: "flex", gap: "8px", flexWrap: "wrap" }}>
          <button
            className="button"
            onClick={handleDownloadTxt}
            disabled={!batchResult || !batchResult.results?.[activeIdx]?.response}
          >
            Download Text
          </button>

          <button
            className="button"
            onClick={isReading ? handleStopReading : handleStartReading}
            disabled={!batchResult || !batchResult.results?.[activeIdx]?.response}
          >
            {isReading ? "Stop Reading" : "Read Aloud"}
          </button>

          <button className="button" onClick={() => setShowJson((v) => !v)} disabled={!batchResult}>
            {showJson ? "Hide JSON" : "Show JSON"}
          </button>
        </div>

        {batchResult && showJson && (
          <div style={{ marginTop: 12 }}>
            <div className="label">Raw API JSON</div>
            <pre
              style={{
                background: "#0b1020",
                color: "#e5e7eb",
                padding: "12px",
                borderRadius: "10px",
                overflow: "auto",
                maxHeight: "320px",
                fontSize: "0.78rem",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {JSON.stringify(batchResult, null, 2)}
            </pre>

            <button className="button" style={{ marginTop: 8 }} onClick={copyJson}>
              Copy JSON
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
