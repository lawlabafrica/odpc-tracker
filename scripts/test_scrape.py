#!/usr/bin/env python3
"""Quick test -- process 5 cases only"""
import sys
sys.path.insert(0, '/root/.openclaw/workspace/odpc-tracker/scripts')

import os, re, json, subprocess, time, urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
PDF_CACHE = Path("/tmp/odpc_pdfs")
PDF_CACHE.mkdir(exist_ok=True)

def fetch_pdf_urls(year):
    url = f"https://www.odpc.go.ke/{year}-determinations/"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        html = r.read().decode("utf-8", errors="ignore")
    return re.findall(r'href="(https://www\.odpc\.go\.ke/wp-content/uploads/[^"]+\.pdf)"', html)

def download_pdf(url, dest):
    if dest.exists() and dest.stat().st_size > 5000:
        return True
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        dest.write_bytes(r.read())
    return True

def ocr_last_pages(pdf_path, n=4):
    result = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True, timeout=10)
    m = re.search(r"Pages:\s+(\d+)", result.stdout)
    total = int(m.group(1)) if m else 8
    start = max(1, total - n + 1)
    ppm_prefix = f"/tmp/test_ocr_{pdf_path.stem}"
    subprocess.run(["pdftoppm", "-r", "150", "-f", str(start), "-l", str(total), str(pdf_path), ppm_prefix], capture_output=True, timeout=60)
    text = ""
    for ppm in sorted(Path("/tmp").glob(f"test_ocr_{pdf_path.stem}*.ppm")):
        r = subprocess.run(["tesseract", str(ppm), "stdout", "quiet"], capture_output=True, text=True, timeout=30)
        text += r.stdout
        ppm.unlink(missing_ok=True)
    return text

# Test with 3 cases from 2026
print("Fetching 2026 URLs...")
urls = fetch_pdf_urls("2026")[:3]
for url in urls:
    fname = url.split("/")[-1]
    dest = PDF_CACHE / fname
    print(f"\nTesting: {fname[:60]}")
    download_pdf(url, dest)
    text = ocr_last_pages(dest)
    
    # Check outcome
    t = text.upper()
    if "DISMISSED" in t:
        outcome = "Dismissed"
    elif "FOUND LIABLE" in t or "UPHELD" in t:
        outcome = "Upheld"
    else:
        outcome = "Unknown"
    
    comp = None
    for m in re.finditer(r"KES[.\s]*([0-9,]+)", t):
        try:
            v = float(m.group(1).replace(",",""))
            if v >= 10000:
                comp = int(v)
                break
        except: pass
    
    print(f"  Outcome: {outcome} | Compensation: {comp}")
    print(f"  Text sample: {text[:200].strip()[:100]}")
