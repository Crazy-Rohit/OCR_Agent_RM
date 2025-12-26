import axios from "axios";

const API_BASE = "http://127.0.0.1:8000";

export async function uploadDocument(file, documentType, zeroRetention = true) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("document_type", documentType);
  formData.append("zero_retention", zeroRetention ? "true" : "false");

  const res = await axios.post(`${API_BASE}/api/v1/ocr/extract`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });

  return res.data;
}

export async function uploadDocuments(files, documentType, zeroRetention = true) {
  const formData = new FormData();
  for (const f of files) formData.append("files", f);
  formData.append("document_type", documentType);
  formData.append("zero_retention", zeroRetention ? "true" : "false");

  const res = await axios.post(`${API_BASE}/api/v1/ocr/extract-batch`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });

  return res.data;
}
