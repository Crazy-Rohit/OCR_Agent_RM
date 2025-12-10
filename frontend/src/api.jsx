import axios from "axios";

const API_BASE = "http://127.0.0.1:8000";

export async function uploadDocument(file, documentType) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("document_type", documentType);

  const res = await axios.post(`${API_BASE}/api/v1/ocr/extract`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });

  return res.data;
}
