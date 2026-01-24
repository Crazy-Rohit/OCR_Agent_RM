import axios from "axios";

// If backend runs on 8000 locally:
const BASE_URL = "http://127.0.0.1:8000";

// Must match settings.API_V1_STR in backend (most likely "/api/v1")
const API_PREFIX = "/api/v1";

export async function uploadDocuments(files, documentType, zeroRetention, enableLayout = true) {
  const formData = new FormData();
  for (const f of files) formData.append("files", f);

  formData.append("document_type", documentType);
  formData.append("zero_retention", String(zeroRetention));

  // ✅ Correct endpoint using API prefix
  const url = `${BASE_URL}${API_PREFIX}/ocr/batch?enable_layout=${enableLayout ? "true" : "false"}`;

  const res = await axios.post(url, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });

  return res.data;
}
