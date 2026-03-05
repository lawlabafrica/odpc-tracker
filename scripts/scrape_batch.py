#!/usr/bin/env python3
"""
Batch scraper -- processes N cases starting from offset.
Run multiple times to process all cases.
Usage: python3 scrape_batch.py [offset] [batch_size]
"""

import os, re, json, subprocess, sys, time, urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
YEARS = ["2023", "2024", "2025", "2026"]
DATA_FILE = Path(__file__).parent.parent / "data" / "determinations.json"
PDF_CACHE = Path("/tmp/odpc_pdfs")
PDF_CACHE.mkdir(exist_ok=True)
URLS_CACHE = Path("/tmp/odpc_all_urls.json")

SECTOR_KEYWORDS = {
    "Banking / Financial Services": ["bank", "sacco", "insurance", "microfinance", "diamond trust", "standard chartered", "prime bank", "ncba", "kcb", "equity", "co-op", "jubilee", "britam"],
    "Fintech / Mobile Lending": ["pesa", "loan", "lemon", "rocket", "chapaa", "branch", "faulu", "fintech", "lending", "whitepath", "fingrow", "bora credit", "asa international", "bidii", "mykes", "deltech", "fin kenya", "trustgro"],
    "Healthcare": ["hospital", "clinic", "health", "medical", "pharmacy", "penda", "bd east", "becton"],
    "Education": ["school", "university", "college", "academy", "education", "loans board", "helb", "kenya school", "regenesys", "dmi education"],
    "Technology": ["tech", "digital", "cloud", "truehost", "software", "app", "platform", "brainstorm"],
    "Ride-hailing / Logistics": ["bolt", "uber", "logistics", "transport", "courier", "solar panda", "geosky"],
    "Media / Marketing": ["marketing", "media", "studio", "advertising", "oxygene", "capstudio", "photography", "veejaystudio", "glam"],
    "Telecom": ["safaricom", "airtel", "telkom", "zuku", "wananchi"],
    "Real Estate / Property": ["real estate", "property", "facilities", "sequoia", "arrow facilities"],
    "Credit Reference": ["metropol", "credit reference", "crb", "transunion"],
    "HR / Recruitment": ["recruitment", "staffing", "human resource", "brites"],
    "Sports / Entertainment": ["football", "club", "entertainment", "acakoro"],
    "Utilities / Public": ["water", "kenya power", "county", "ncwsc", "nairobi water"],
    "Retail / Commerce": ["shop", "supermarket", "store", "retail", "motown", "sistar", "mulla pride"],
}

def guess_sector(text):
    t = text.lower()
    for sector, kws in SECTOR_KEYWORDS.items():
        if any(kw in t for kw in kws):
            return sector
    return "General"

def fetch_all_urls():
    if URLS_CACHE.exists():
        return json.loads(URLS_CACHE.read_text())
    all_urls = []
    for year in YEARS:
        url = f"https://www.odpc.go.ke/{year}-determinations/"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")
        urls = re.findall(r'href="(https://www\.odpc\.go\.ke/wp-content/uploads/[^"]+\.pdf)"', html)
        all_urls.extend([(u, year) for u in urls])
        print(f"  {year}: {len(urls)} PDFs")
    URLS_CACHE.write_text(json.dumps(all_urls))
    return all_urls

def download_pdf(url, dest):
    if dest.exists() and dest.stat().st_size > 5000:
        return True
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        dest.write_bytes(r.read())
    return dest.stat().st_size > 5000

def ocr_last_pages(pdf_path, n=4):
    try:
        result = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True, timeout=10)
        m = re.search(r"Pages:\s+(\d+)", result.stdout)
        total = int(m.group(1)) if m else 8
        start = max(1, total - n + 1)
        ppm_prefix = f"/tmp/odpc_batch_{pdf_path.stem}"
        subprocess.run(["pdftoppm", "-r", "150", "-f", str(start), "-l", str(total), str(pdf_path), ppm_prefix],
                       capture_output=True, timeout=60)
        text = ""
        for ppm in sorted(Path("/tmp").glob(f"odpc_batch_{pdf_path.stem}*.ppm")):
            r = subprocess.run(["tesseract", str(ppm), "stdout", "quiet"], capture_output=True, text=True, timeout=30)
            text += r.stdout
            ppm.unlink(missing_ok=True)
        return text
    except:
        return ""

def ocr_first_pages(pdf_path, n=2):
    try:
        ppm_prefix = f"/tmp/odpc_batchf_{pdf_path.stem}"
        subprocess.run(["pdftoppm", "-r", "150", "-f", "1", "-l", str(n), str(pdf_path), ppm_prefix],
                       capture_output=True, timeout=60)
        text = ""
        for ppm in sorted(Path("/tmp").glob(f"odpc_batchf_{pdf_path.stem}*.ppm")):
            r = subprocess.run(["tesseract", str(ppm), "stdout", "quiet"], capture_output=True, text=True, timeout=30)
            text += r.stdout
            ppm.unlink(missing_ok=True)
        return text
    except:
        return ""

def extract_parties_from_ocr(text):
    """Try to extract complainant and respondent from first page OCR"""
    m = re.search(r"([A-Z][A-Z\s\.,]+?)\s*[\.]{3,}\s*COMPLAINANT", text)
    complainant = m.group(1).strip().title() if m else None
    m = re.search(r"([A-Z][A-Z\s\.,&/\(\)]+?)\s*[\.]{3,}\s*RESPONDENT", text)
    respondent = m.group(1).strip().title() if m else None
    return complainant, respondent

def extract_from_filename(url):
    fname = url.split("/")[-1].replace(".pdf", "")
    fname = re.sub(r"^\d{8}-", "", fname)
    parts = re.split(r"\s*-[Vv][Ss]-?\s*|\s+[Vv][Ss]\.?\s+", fname.replace("-", " "), maxsplit=1)
    complainant = parts[0].strip().title() if parts else "Unknown"
    respondent = parts[1].strip().title() if len(parts) > 1 else fname.strip().title()
    return complainant, respondent

def extract_date(url):
    fname = url.split("/")[-1]
    m = re.match(r"(\d{4})(\d{2})(\d{2})-", fname)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"/uploads/(\d{4})/(\d{2})/", url)
    return f"{m.group(1)}-{m.group(2)}" if m else None

def extract_outcome(text):
    t = text.upper()
    if any(x in t for x in ["COMPLAINT IS HEREBY DISMISSED", "COMPLAINT STANDS DISMISSED", "LACKS MERIT", "COMPLAINT IS DISMISSED", "HEREBY DISMISSED"]):
        return "Dismissed"
    if any(x in t for x in ["FOUND LIABLE", "RESPONDENT IS HEREBY FOUND", "COMPLAINT IS UPHELD", "FOUND TO HAVE VIOLATED"]):
        return "Upheld"
    if "PARTIALLY" in t and ("UPHELD" in t or "LIABLE" in t):
        return "Partially Upheld"
    return "Unknown"

def extract_compensation(text):
    t = text.upper()
    patterns = [
        r"(?:ORDERED TO PAY|PAY THE COMPLAINANT)[^.]*?(?:KES|KSHS?|KENYA SHILLINGS?)[.\s]*([0-9,]+)",
        r"(?:KES|KSHS?)[.\s]*([0-9,]+(?:\.[0-9]+)?)\s*(?:AS COMPENSATION|ONLY|SHILLINGS)",
        r"COMPENSATION[^.]*?([0-9,]+)\s*(?:KENYA SHILLINGS|KES|KSHS)",
    ]
    for p in patterns:
        for m in re.finditer(p, t):
            try:
                v = float(m.group(1).replace(",", ""))
                if 10000 <= v <= 10000000:
                    return int(v)
            except:
                pass
    return None

def extract_violations(text):
    t = text.upper()
    violations = []
    checks = [
        ("Unauthorised image use", ["IMAGE", "PHOTO", "PICTURE"]),
        ("Lack of consent", ["WITHOUT CONSENT", "NO CONSENT", "EXPRESS CONSENT", "CONSENT WAS NOT"]),
        ("Commercial use of personal data", ["COMMERCIAL USE", "COMMERCIAL PURPOSES"]),
        ("Unlawful data disclosure", ["UNLAWFUL DISCLOS", "SHARED.*PERSONAL DATA", "THIRD PART.*DATA"]),
        ("Failure to prevent data breach", ["DATA BREACH", "BREACH OF SECURITY", "UNAUTHORISED ACCESS"]),
        ("Unlawful debt collection", ["DEBT COLLECTION", "LOAN.*CONTACT", "DEMANDING PAYMENT"]),
        ("Failure to respond to erasure/deletion request", ["DELETION", "ERASURE", "PULL DOWN", "REMOVE.*IMAGE"]),
        ("Failure to notify data breach", ["72 HOURS", "BREACH NOTIFICATION", "NOTIFY.*BREACH"]),
        ("Obstruction of Data Commissioner", ["OBSTRUCT", "DENIED.*ACCESS.*DATABASE", "REFUSED.*ACCESS"]),
        ("Failure to conduct DPIA", ["DPIA", "DATA PROTECTION IMPACT ASSESSMENT"]),
        ("Unlawful processing of personal data", ["SECTION 25", "UNLAWFUL.*PROCESS"]),
        ("Failure to register with ODPC", ["REGISTER", "REGISTRATION"]),
    ]
    for label, patterns in checks:
        for p in patterns:
            if re.search(p, t):
                violations.append(label)
                break
    return violations or ["Data protection violation"]

def load_existing():
    with open(DATA_FILE) as f:
        return json.load(f)

def save(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def main():
    offset = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    batch_size = int(sys.argv[2]) if len(sys.argv) > 2 else 25

    print(f"Fetching URL list...")
    all_urls = fetch_all_urls()
    batch = all_urls[offset:offset + batch_size]
    print(f"Processing cases {offset+1}-{offset+len(batch)} of {len(all_urls)}")

    existing_data = load_existing()
    existing_urls = {d.get("pdf_url") for d in existing_data["determinations"]}

    new_cases = []
    for i, (url, year) in enumerate(batch):
        if url in existing_urls:
            print(f"  [{offset+i+1}] SKIP (already exists): {url.split('/')[-1][:50]}")
            continue

        fname = url.split("/")[-1]
        pdf_path = PDF_CACHE / fname
        print(f"  [{offset+i+1}] {fname[:60]}")

        if not download_pdf(url, pdf_path):
            print(f"    SKIP: download failed")
            continue

        # OCR
        last_text = ocr_last_pages(pdf_path, n=5)
        first_text = ocr_first_pages(pdf_path, n=2)
        all_text = first_text + last_text

        # Extract parties -- try OCR first, fall back to filename
        ocr_complainant, ocr_respondent = extract_parties_from_ocr(first_text)
        fn_complainant, fn_respondent = extract_from_filename(url)
        complainant = ocr_complainant or fn_complainant
        respondent = ocr_respondent or fn_respondent

        outcome = extract_outcome(last_text)
        comp = extract_compensation(last_text)
        violations = extract_violations(all_text)
        date_str = extract_date(url)
        sector = guess_sector(respondent + " " + fname)
        enforcement = "ENFORCEMENT NOTICE" in all_text.upper()
        prosecution = bool(re.search(r"PROSECUTION.*RECOMMEND|RECOMMEND.*PROSECUTION", all_text.upper()))

        det = {
            "id": f"{year}-{re.sub(r'[^a-z0-9]', '-', fname.lower().replace('.pdf',''))[:40]}",
            "case_number": f"See PDF",
            "date_determined": date_str or year,
            "year": int(year),
            "respondent": respondent,
            "complainant": complainant,
            "complainant_category": "Individual",
            "sector": sector,
            "violation_type": violations,
            "violation_summary": f"{complainant} v {respondent}. {violations[0] if violations else 'Data protection violation'}. Outcome: {outcome}.",
            "outcome": outcome,
            "compensation_kes": comp,
            "compensation_usd_approx": round(comp / 129) if comp else None,
            "enforcement_notice": enforcement,
            "prosecution_recommended": prosecution,
            "pdf_url": url,
            "tags": [sector.lower().split("/")[0].strip()]
        }
        new_cases.append(det)
        print(f"    {respondent[:40]} | {outcome} | KES {comp}")

    # Merge and save
    existing_data["determinations"].extend(new_cases)
    existing_data["determinations"].sort(key=lambda x: x.get("date_determined",""), reverse=True)
    existing_data["metadata"]["total_records"] = len(existing_data["determinations"])
    existing_data["metadata"]["last_updated"] = "2026-03-05"
    save(existing_data)
    print(f"\nBatch done. Added {len(new_cases)} new cases. Total: {len(existing_data['determinations'])}")
    print(f"Next batch: python3 scrape_batch.py {offset + batch_size}")

if __name__ == "__main__":
    main()
