#!/usr/bin/env python3
"""
ODPC Determinations Scraper
Scrapes all PDF links from odpc.go.ke year pages, downloads PDFs,
OCRs them, and extracts structured data into determinations.json
"""

import os, re, json, subprocess, tempfile, time, urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
YEARS = ["2023", "2024", "2025", "2026"]
DATA_DIR = Path(__file__).parent.parent / "data"
PDF_CACHE = Path("/tmp/odpc_pdfs")
PDF_CACHE.mkdir(exist_ok=True)

SECTOR_KEYWORDS = {
    "Banking / Financial Services": ["bank", "sacco", "credit", "insurance", "microfinance", "finance", "dtb", "equity", "kcb", "co-op", "ncba", "prime bank", "diamond trust", "standard chartered"],
    "Fintech / Mobile Lending": ["pesa", "loan", "lemon", "rocketpesa", "chapaa", "branch", "faulu", "fintech", "mobile money", "lending", "credit limited", "whitepath", "fingrow", "bora credit"],
    "Healthcare": ["hospital", "clinic", "health", "medical", "pharmacy", "penda"],
    "Education": ["school", "university", "college", "academy", "education", "loans board", "helb", "kenya school of law"],
    "Technology": ["tech", "digital", "cloud", "truehost", "software", "app", "platform"],
    "Ride-hailing / Logistics": ["bolt", "uber", "logistics", "transport", "courier"],
    "Media / Marketing": ["marketing", "media", "studio", "advertising", "oxygene", "capstudio", "photography"],
    "Telecom": ["safaricom", "airtel", "telkom", "zuku", "wananchi"],
    "Real Estate / Property": ["real estate", "property", "facilities", "sequoia heights"],
    "Retail / Commerce": ["shop", "supermarket", "store", "retail"],
    "HR / Recruitment": ["recruitment", "staffing", "human resource", "brites"],
    "Sports / Entertainment": ["football", "club", "entertainment", "acakoro"],
}

def guess_sector(text):
    text_lower = text.lower()
    for sector, keywords in SECTOR_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return sector
    return "General"

def fetch_pdf_urls(year):
    url = f"https://www.odpc.go.ke/{year}-determinations/"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")
        return re.findall(r'href="(https://www\.odpc\.go\.ke/wp-content/uploads/[^"]+\.pdf)"', html)
    except Exception as e:
        print(f"  Error fetching {year}: {e}")
        return []

def download_pdf(url, dest):
    if dest.exists() and dest.stat().st_size > 5000:
        return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            dest.write_bytes(r.read())
        return dest.stat().st_size > 5000
    except Exception as e:
        print(f"    Download error: {e}")
        return False

def ocr_pdf_pages(pdf_path, pages="1-4"):
    """OCR specific pages of a PDF, return text"""
    try:
        start, end = pages.split("-")
        ppm_prefix = str(pdf_path).replace(".pdf", "_ocr")
        subprocess.run(
            ["pdftoppm", "-r", "150", "-f", start, "-l", end, str(pdf_path), ppm_prefix],
            capture_output=True, timeout=60
        )
        text = ""
        for ppm in sorted(Path("/tmp").glob(f"{Path(ppm_prefix).name}*.ppm")):
            result = subprocess.run(
                ["tesseract", str(ppm), "stdout", "quiet"],
                capture_output=True, text=True, timeout=30
            )
            text += result.stdout
            ppm.unlink(missing_ok=True)
        return text
    except Exception as e:
        return ""

def ocr_last_pages(pdf_path, n=4):
    """OCR last n pages"""
    try:
        result = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True, timeout=10)
        pages_match = re.search(r"Pages:\s+(\d+)", result.stdout)
        total = int(pages_match.group(1)) if pages_match else 10
        start = max(1, total - n + 1)
        return ocr_pdf_pages(pdf_path, f"{start}-{total}")
    except:
        return ""

def extract_from_filename(url):
    """Parse parties from PDF filename"""
    fname = url.split("/")[-1].replace(".pdf", "")
    fname = re.sub(r"^\d{8}-", "", fname)  # remove date prefix
    fname = fname.replace("-", " ").replace("_", " ")
    
    # Try to split on vs/VS
    if " vs " in fname.upper():
        parts = re.split(r"\s+[Vv][Ss]\.?\s+", fname, maxsplit=1)
        complainant = parts[0].strip().title() if len(parts) > 0 else "Unknown"
        respondent = parts[1].strip().title() if len(parts) > 1 else "Unknown"
    else:
        complainant = "Unknown"
        respondent = fname.strip().title()
    
    return complainant, respondent

def extract_date_from_url(url):
    """Try to get date from filename or URL path"""
    # Try date prefix in filename like 20240102-
    fname = url.split("/")[-1]
    m = re.match(r"(\d{4})(\d{2})(\d{2})-", fname)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # Fall back to upload year/month from URL
    m = re.search(r"/uploads/(\d{4})/(\d{2})/", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None

def extract_outcome_and_compensation(text):
    """Parse outcome and compensation from OCR text of last pages"""
    text_upper = text.upper()
    
    outcome = "Unknown"
    compensation_kes = None
    enforcement_notice = False
    prosecution_recommended = False
    
    # Outcome
    if any(x in text_upper for x in ["COMPLAINT IS HEREBY DISMISSED", "COMPLAINT STANDS DISMISSED", "LACKS MERIT"]):
        outcome = "Dismissed"
    elif any(x in text_upper for x in ["FOUND LIABLE", "RESPONDENT IS HEREBY FOUND", "UPHELD", "COMPLAINT IS UPHELD"]):
        outcome = "Upheld"
    elif "PARTIALLY" in text_upper:
        outcome = "Partially Upheld"
    
    # Compensation -- look for KES amounts
    comp_patterns = [
        r"(?:KES|KSHS?|KENYA SHILLINGS?)[.\s]*([0-9,]+(?:\.[0-9]+)?)",
        r"([0-9,]+)\s*(?:KENYA SHILLINGS|KES|KSHS)",
        r"PAY[^.]*?([0-9,]+(?:\.[0-9]+)?)\s*(?:AS COMPENSATION|SHILLINGS)",
    ]
    for pattern in comp_patterns:
        matches = re.findall(pattern, text_upper)
        if matches:
            for m in matches:
                try:
                    val = float(m.replace(",", ""))
                    if val >= 10000:  # filter out small numbers
                        compensation_kes = int(val)
                        break
                except:
                    pass
        if compensation_kes:
            break
    
    if "ENFORCEMENT NOTICE" in text_upper:
        enforcement_notice = True
    if "PROSECUTION" in text_upper and "RECOMMEND" in text_upper:
        prosecution_recommended = True
    
    return outcome, compensation_kes, enforcement_notice, prosecution_recommended

def extract_violation_type(text):
    """Infer violation type from text"""
    violations = []
    t = text.upper()
    checks = [
        ("Unauthorised image use", ["IMAGE", "PHOTO", "PICTURE"]),
        ("Lack of consent", ["WITHOUT CONSENT", "CONSENT WAS NOT", "NO CONSENT", "EXPRESS CONSENT"]),
        ("Commercial use of personal data", ["COMMERCIAL USE", "COMMERCIAL PURPOSES"]),
        ("Unlawful data disclosure", ["DISCLOSED", "DISCLOSURE", "SHARED.*DATA", "DATA.*SHARED"]),
        ("Failure to prevent data breach", ["DATA BREACH", "BREACH OF SECURITY", "UNAUTHORISED ACCESS"]),
        ("Unlawful debt collection", ["DEBT", "LOAN", "CONTACTED.*DEMANDING", "CREDIT"]),
        ("Failure to respond to erasure request", ["DELETION", "ERASURE", "REMOVE.*IMAGE", "PULL DOWN"]),
        ("Failure to notify data breach", ["NOTIFY.*BREACH", "BREACH.*NOTIFICATION", "72 HOURS"]),
        ("Obstruction of Data Commissioner", ["OBSTRUCT", "DENIED.*ACCESS", "REFUSED.*ACCESS"]),
        ("Failure to conduct DPIA", ["DPIA", "DATA PROTECTION IMPACT"]),
        ("Unlawful processing of personal data", ["UNLAWFUL.*PROCESS", "PROCESS.*UNLAWFUL", "SECTION 25"]),
    ]
    for label, patterns in checks:
        for p in patterns:
            if re.search(p, t):
                violations.append(label)
                break
    return violations if violations else ["Data protection violation"]

def make_id(url, year):
    fname = url.split("/")[-1].replace(".pdf", "")
    # Use date prefix if available
    m = re.match(r"(\d{8})-(.+)", fname)
    if m:
        return f"{year}-{m.group(1)[4:6]}-{fname[:20].replace('-','')[:12]}"
    return f"{year}-{fname[:20].replace('-','_')}"

def process_all():
    all_urls = []
    for year in YEARS:
        print(f"\nFetching {year} determination links...")
        urls = fetch_pdf_urls(year)
        print(f"  Found {len(urls)} PDFs")
        all_urls.extend([(url, year) for url in urls])
    
    print(f"\nTotal PDFs to process: {len(all_urls)}")
    
    determinations = []
    
    for i, (url, year) in enumerate(all_urls):
        fname = url.split("/")[-1]
        pdf_path = PDF_CACHE / fname
        
        print(f"\n[{i+1}/{len(all_urls)}] {fname[:60]}")
        
        # Download
        if not download_pdf(url, pdf_path):
            print(f"  SKIP: download failed")
            continue
        
        # Extract from filename
        complainant, respondent = extract_from_filename(url)
        date_str = extract_date_from_url(url)
        sector = guess_sector(respondent + " " + fname)
        
        # OCR last pages for outcome/compensation
        print(f"  OCR last pages...")
        last_text = ocr_last_pages(pdf_path, n=5)
        outcome, comp_kes, enforcement, prosecution = extract_outcome_and_compensation(last_text)
        
        # OCR first pages for violation type if needed
        if outcome == "Unknown" or not last_text:
            first_text = ocr_pdf_pages(pdf_path, "1-2")
            all_text = first_text + last_text
        else:
            first_text = ocr_pdf_pages(pdf_path, "1-2")
            all_text = first_text + last_text
        
        violations = extract_violation_type(all_text)
        
        # Build case number from filename if possible
        case_num = None
        m = re.search(r"ODPC[- ]?COMP(?:LAINT)?[- ]?(?:NO\.?\s*)?(\d+)[- ]OF[- ](\d{4})", fname.upper())
        if m:
            case_num = f"ODPC Complaint No. {m.group(1)} of {m.group(2)}"
        
        det = {
            "id": f"{year}-{fname[:30].replace('.pdf','').replace('-','_')}",
            "case_number": case_num or f"See PDF",
            "date_determined": date_str or year,
            "year": int(year),
            "respondent": respondent,
            "complainant": complainant,
            "complainant_category": "Individual",
            "sector": sector,
            "violation_type": violations,
            "violation_summary": f"{complainant} vs {respondent}. Outcome: {outcome}.",
            "outcome": outcome,
            "compensation_kes": comp_kes,
            "compensation_usd_approx": round(comp_kes / 129) if comp_kes else None,
            "enforcement_notice": enforcement,
            "prosecution_recommended": prosecution,
            "pdf_url": url,
            "tags": [sector.lower().split("/")[0].strip()]
        }
        
        determinations.append(det)
        print(f"  Respondent: {respondent[:50]} | Outcome: {outcome} | Comp: {comp_kes}")
        
        # Save progress every 20 cases
        if (i + 1) % 20 == 0:
            save_json(determinations)
            print(f"  -- Progress saved ({len(determinations)} records) --")
        
        time.sleep(0.5)  # polite delay
    
    save_json(determinations)
    print(f"\nDone. {len(determinations)} determinations saved.")
    return determinations

def save_json(determinations):
    existing_path = DATA_DIR / "determinations.json"
    
    # Load existing manually-curated records
    with open(existing_path) as f:
        existing = json.load(f)
    
    # Keep the manually curated records, add scraped ones
    # De-duplicate by PDF URL
    existing_urls = {d.get("pdf_url") for d in existing["determinations"]}
    
    new_records = [d for d in determinations if d["pdf_url"] not in existing_urls]
    all_records = existing["determinations"] + new_records
    
    # Sort by date descending
    all_records.sort(key=lambda x: x.get("date_determined", ""), reverse=True)
    
    existing["metadata"]["total_records"] = len(all_records)
    existing["metadata"]["last_updated"] = "2026-03-05"
    existing["metadata"]["note"] = "Dataset compiled from all published ODPC determinations. Scraped via OCR from original PDFs."
    existing["determinations"] = all_records
    
    with open(existing_path, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
    
    print(f"  Saved {len(all_records)} total records to {existing_path}")

if __name__ == "__main__":
    process_all()
