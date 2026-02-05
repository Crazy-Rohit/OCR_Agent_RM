from __future__ import annotations

import json
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "tests" / "golden_inputs"


def _require_golden_inputs() -> None:
    if not GOLDEN_DIR.exists():
        raise SystemExit(
            "Golden inputs not found. Run: python scripts/generate_golden_inputs.py"
        )

    required = [
        GOLDEN_DIR / "hello_v0.png",
        GOLDEN_DIR / "hello_v0.pdf",
        GOLDEN_DIR / "hello_v0_rotated.png",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise SystemExit(
            "Missing golden files:\n" + "\n".join(missing) + "\n\nRun: python scripts/generate_golden_inputs.py"
        )


def _call_ocr(file_path: Path, *, base_url: str) -> dict:
    url = f"{base_url.rstrip('/')}/api/v1/ocr"
    with file_path.open("rb") as f:
        files = {"file": (file_path.name, f, "application/octet-stream")}
        data = {
            "document_type": "golden",
            "zero_retention": "true",
        }
        params = {"enable_layout": "false"}
        r = httpx.post(url, files=files, data=data, params=params, timeout=120.0)
        r.raise_for_status()
        return r.json()


def _normalize_text(s: str) -> str:
    return " ".join((s or "").replace("\n", " ").split()).strip().upper()


def main() -> None:
    _require_golden_inputs()

    base_url = "http://127.0.0.1:8000"
    expected = "HELLO OCR AGENT V0"
    expected_norm = _normalize_text(expected)

    targets = [
        GOLDEN_DIR / "hello_v0.png",
        GOLDEN_DIR / "hello_v0.pdf",
        GOLDEN_DIR / "hello_v0_rotated.png",
    ]

    results = []
    failures = 0

    for fp in targets:
        resp = _call_ocr(fp, base_url=base_url)
        full_text = resp.get("full_text", "")
        got_norm = _normalize_text(full_text)
        ok = expected_norm in got_norm
        if not ok:
            failures += 1

        results.append(
            {
                "file": fp.name,
                "ok": ok,
                "expected_contains": expected,
                "got_excerpt": full_text[:200],
            }
        )

    out_path = ROOT / "runtime" / "golden_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")

    print("\nGolden report:")
    for r in results:
        status = "PASS" if r["ok"] else "FAIL"
        print(f" - {status}: {r['file']}")
    print(f"\nReport saved to: {out_path}")

    if failures:
        raise SystemExit(f"\n❌ Golden test failed: {failures} file(s)")

    print("\n✅ Golden test passed")


if __name__ == "__main__":
    main()
