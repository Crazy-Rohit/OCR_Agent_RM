# Overview

This is the backend service for the OCR Agent (Phase 1), built using FastAPI.
It supports:

OCR for PDF, images, and DOCX

Batch upload (multiple documents at once)

Zero data retention (no file storage when enabled)

Duplicate file handling


## 📁 Folder Structure (Backend)

backend/

│

├── app/

│   ├── main.py              # FastAPI app entry point

│   ├── api/

│   │   └── ocr_routes.py    # OCR endpoints

│   ├── services/

│   │   └── ocr_service.py   # OCR logic (Tesseract, PDF, images)

│   ├── core/

│   │   └── config.py        # Environment & limits

│   └── models/

│       └── schemas.py       # API schemas

│

├── uploads/                 # Used ONLY when retention is disabled

├── requirements.txt

└── README.md                # (this file)


## 🧩 Prerequisites
### 1️⃣ Python (Required)
Python 3.14 (64-bit)
Verify:

python --version

### 2️⃣ Tesseract OCR (Required)
Tesseract is the OCR engine used to extract text from images and scanned PDFs.

#### ✅ Download (Offline-friendly)

Official GitHub release (Windows installer):
https://github.com/UB-Mannheim/tesseract/wiki

Direct installer (recommended):
https://github.com/UB-Mannheim/tesseract/releases
Download the latest 64-bit Windows installer (.exe).

#### ✅ Default Install Path (Recommended)
C:\Program Files\Tesseract-OCR\tesseract.exe


⚠️ Important:
During installation, ensure:

“Add Tesseract to PATH” is checked (if available)
English language data is selected


## ⚙️ Backend Setup (Windows)
### Step 1: Navigate to backend folder
cd C:\ocr_agent\backend

### Step 2: Create & activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

Confirm:
python --version

### Step 3: Upgrade pip tooling (VERY IMPORTANT for Python 3.14)
python -m pip install -U pip setuptools wheel

### Step 4: Install backend dependencies
⚠️ Binary wheels only (prevents C-extension errors):
pip install --only-binary=:all: -r requirements.txt

If cache causes issues:
pip install --no-cache-dir --only-binary=:all: -r requirements.txt

### 🔧 Environment Configuration
Set these before running the server:

$env:TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"
$env:ZERO_RETENTION_DEFAULT="true"
$env:MAX_DOCS_PER_BATCH="30"
$env:MAX_FILE_SIZE_MB="20"

### What these mean:
TESSERACT_CMD → Explicit OCR engine path
ZERO_RETENTION_DEFAULT=true → Files are NOT stored
MAX_DOCS_PER_BATCH → Max files per upload request
MAX_FILE_SIZE_MB → Protects memory usage


### ▶️ Run the Backend Server
Run from the backend directory:
uvicorn app.main:app --reload


Server will start at:
http://127.0.0.1:8000

Swagger API docs:
http://127.0.0.1:8000/docs

