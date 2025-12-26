import { useState, useRef } from "react";
import { uploadDocuments } from "./api";

function App() {
  const [files, setFiles] = useState([]);
  const [docType, setDocType] = useState("generic");
  const [zeroRetention, setZeroRetention] = useState(true);
  const [batchResult, setBatchResult] = useState(null);
  const [activeIdx, setActiveIdx] = useState(0); // which file output to display
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("full"); // "full" or "pages"
  const [error, setError] = useState(null);
  const [isReading, setIsReading] = useState(false);
  const utteranceRef = useRef(null);

  const handleUpload = async () => {
    if (!files.length) {
      setError("Please choose at least 1 file.");
      return;
    }
    setError(null);
    setLoading(true);
    setBatchResult(null);
    setIsReading(false);
    window.speechSynthesis.cancel();

    try {
      const data = await uploadDocuments(files, docType, zeroRetention);
      setBatchResult(data);
      setActiveIdx(0);
    } catch (err) {
      console.error(err);
      setError(
        err?.response?.data?.detail ||
          err?.message ||
          "Something went wrong processing the file."
      );
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadTxt = () => {
    const item = batchResult?.results?.[activeIdx];
    const result = item?.response;
    if (!result) return;

    const blob = new Blob([result.full_text || ""], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");

    const baseName =
      (result.metadata && result.metadata.file_name) || "ocr_output";

    a.href = url;
    a.download = baseName.replace(/\.[^/.]+$/, "") + "_ocr.txt";
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleStartReading = () => {
    const item = batchResult?.results?.[activeIdx];
    const result = item?.response;
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

  return (
    <div className="container">
      {/* Upload / controls */}
      <div className="card">
        <h2>OCR Agent – Phase 1</h2>
        <p style={{ fontSize: "0.9rem", color: "#6b7280" }}>
          Upload a PDF, image, or DOCX to extract text and listen to it.
        </p>

        <div style={{ marginTop: "12px" }}>
          <div className="label">Document file</div>
          <input
  type="file"
  multiple
  accept=".pdf,.docx,image/*"
  onChange={(e) => {
    const picked = Array.from(e.target.files || []);

    // ✅ Keep only ONE per filename on client side
    const map = new Map(); // name -> File
    for (const f of picked) {
      if (!map.has(f.name)) map.set(f.name, f);
      // if you want "latest wins", replace the above line with: map.set(f.name, f);
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
            <input
              type="checkbox"
              checked={zeroRetention}
              onChange={(e) => setZeroRetention(e.target.checked)}
            />
            Zero data retention (do not save uploads)
          </label>
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

        <button
          className="button"
          style={{ marginTop: "14px" }}
          disabled={loading}
          onClick={handleUpload}
        >
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

        {batchResult && batchResult.results && batchResult.results.length > 0 && (
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
                  {r.filename} {r.skipped_duplicate ? "(duplicate skipped)" : ""}{" "}
                  {r.error ? "(error)" : ""}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Tabs */}
        <div className="tabs">
          <button
            className={activeTab === "full" ? "active" : ""}
            onClick={() => setActiveTab("full")}
          >
            Full Text
          </button>
          <button
            className={activeTab === "pages" ? "active" : ""}
            onClick={() => setActiveTab("pages")}
          >
            Page-wise
          </button>
        </div>

        {/* Output area */}
        <div
          style={{
            background: "#fafafa",
            padding: "12px",
            borderRadius: "8px",
            marginTop: "10px",
            height: "280px",
            overflow: "auto",
            whiteSpace: "pre-wrap",
            fontSize: "0.9rem",
          }}
        >
          {!batchResult && (
            <span style={{ color: "#9ca3af" }}>No output yet.</span>
          )}

          {batchResult &&
            (() => {
              const item = batchResult.results?.[activeIdx];
              if (!item) return null;
              if (item.error) return `Error: ${item.error}`;
              if (item.skipped_duplicate) return "Duplicate file skipped.";
              const result = item.response;
              if (!result) return "No result.";
              if (activeTab === "full") return result.full_text;
              return (
                <>
                  {result.pages.map((p) => (
                    <div key={p.page_number} style={{ marginBottom: "12px" }}>
                      <div
                        style={{
                          fontWeight: 600,
                          fontSize: "0.8rem",
                          marginBottom: "4px",
                        }}
                      >
                        Page {p.page_number}
                      </div>
                      <div>{p.text}</div>
                    </div>
                  ))}
                </>
              );
            })()}
        </div>

        {/* Actions */}
        <div style={{ marginTop: "10px" }}>
          <button
            className="button"
            style={{ marginRight: "8px" }}
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
        </div>
      </div>
    </div>
  );
}

export default App;
