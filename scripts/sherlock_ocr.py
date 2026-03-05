#!/usr/bin/env python3
"""
ODPC Determinations OCR Script -- for Sherlock HPC
Run this on Sherlock to OCR all 313 ODPC determination PDFs.

Usage:
    python3 sherlock_ocr.py

Output:
    odpc_ocr_results.json -- upload this to GitHub or paste contents to Capybara

Requirements:
    - Python 3.6+
    - tesseract (module load tesseract or apt install tesseract-ocr)
    - poppler-utils (for pdftoppm)
    - Internet access (to download PDFs from odpc.go.ke)

Estimated runtime: 30-60 minutes on Sherlock
"""

import os, re, json, subprocess, time, urllib.request, sys
from pathlib import Path
from datetime import datetime

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
YEARS = ["2023", "2024", "2025", "2026"]
PDF_DIR = Path("./odpc_pdfs")
PDF_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = Path("./odpc_ocr_results.json")
PROGRESS_FILE = Path("./odpc_ocr_progress.json")

# ── Helpers ──────────────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def fetch_all_urls():
    all_urls = []
    for year in YEARS:
        url = f"https://www.odpc.go.ke/{year}-determinations/"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")
        urls = re.findall(
            r'href="(https://www\.odpc\.go\.ke/wp-content/uploads/[^"]+\.pdf)"', html
        )
        all_urls.extend([(u, year) for u in urls])
        log(f"  {year}: {len(urls)} PDFs found")
    return all_urls

def download_pdf(url, dest):
    if dest.exists() and dest.stat().st_size > 5000:
        return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            dest.write_bytes(r.read())
        return dest.stat().st_size > 5000
    except Exception as e:
        log(f"    Download failed: {e}")
        return False

def get_page_count(pdf_path):
    try:
        r = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True, timeout=10)
        m = re.search(r"Pages:\s+(\d+)", r.stdout)
        return int(m.group(1)) if m else 8
    except:
        return 8

def ocr_pages(pdf_path, start, end, tag=""):
    """Convert pages to images and OCR them. Returns text."""
    prefix = f"/tmp/odpc_{tag}_{pdf_path.stem}"
    try:
        subprocess.run(
            ["pdftoppm", "-r", "150", "-f", str(start), "-l", str(end),
             str(pdf_path), prefix],
            capture_output=True, timeout=120
        )
        text = ""
        for ppm in sorted(Path("/tmp").glob(f"odpc_{tag}_{pdf_path.stem}*.ppm")):
            r = subprocess.run(
                ["tesseract", str(ppm), "stdout", "quiet"],
                capture_output=True, text=True, timeout=60
            )
            text += r.stdout
            ppm.unlink(missing_ok=True)
        return text
    except Exception as e:
        log(f"    OCR error: {e}")
        return ""

def ocr_all_pages(pdf_path):
    """OCR every page of the PDF. Returns (first_text, last_text, full_text)."""
    total = get_page_count(pdf_path)
    first_end = min(3, total)
    last_start = max(1, total - 4)

    # OCR in chunks of 5 pages to avoid memory issues
    full_text = ""
    chunk = 5
    for start in range(1, total + 1, chunk):
        end = min(start + chunk - 1, total)
        full_text += ocr_pages(pdf_path, start, end, f"p{start}")

    first_text = "\n".join(full_text.split("\n")[:80])   # approx first 3 pages
    last_text = "\n".join(full_text.split("\n")[-100:])  # approx last 4 pages
    return first_text, last_text, full_text

# ── Extraction ────────────────────────────────────────────────────────────────

def extract_parties_ocr(first_text):
    """Extract complainant and respondent from OCR of first pages."""
    complainant, respondent = None, None
    m = re.search(r"([A-Z][A-Z\s\.,\-]+?)\s*[\.·]{3,}\s*COMPLAINANT", first_text)
    if m:
        complainant = m.group(1).strip().title()
    m = re.search(r"([A-Z][A-Z\s\.,\-&/\(\)]+?)\s*[\.·]{3,}\s*RESPONDENT", first_text)
    if m:
        respondent = m.group(1).strip().title()
    return complainant, respondent

def extract_parties_filename(url):
    fname = url.split("/")[-1].replace(".pdf", "")
    fname = re.sub(r"^\d{8}-", "", fname)
    parts = re.split(r"-VS-|-[Vv][Ss]-", fname, maxsplit=1)
    if len(parts) == 2:
        return (
            parts[0].replace("-", " ").strip().title(),
            parts[1].replace("-", " ").strip().title()
        )
    return "See PDF", fname.replace("-", " ").strip().title()

def extract_case_number(first_text):
    m = re.search(
        r"ODPC\s+COMPLAINT\s+NO\.?\s*(\d+)\s+OF\s+(\d{4})",
        first_text.upper()
    )
    if m:
        return f"ODPC Complaint No. {m.group(1)} of {m.group(2)}"
    return "See PDF"

def extract_complaint_date(full_text):
    """Extract the date the complaint was filed."""
    t = full_text.upper()
    patterns = [
        r"COMPLAINT\s+(?:WAS\s+)?(?:FILED|RECEIVED|LODGED)\s+(?:ON\s+)?(?:THE\s+)?(\d{1,2}(?:ST|ND|RD|TH)?\s+\w+\s+\d{4}|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4}|\w+\s+\d{1,2},?\s+\d{4})",
        r"RECEIVED\s+A\s+COMPLAINT\s+ON\s+(\d{1,2}(?:ST|ND|RD|TH)?\s+\w+\s+\d{4}|\w+\s+\d{1,2},?\s+\d{4})",
        r"COMPLAINT\s+ON\s+(\d{1,2}\w*\s+\w+\s+\d{4})",
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            return m.group(1).strip().title()
    return None

def extract_legal_provisions(full_text):
    """Extract which sections of the DPA were cited."""
    t = full_text.upper()
    sections = set()
    for m in re.finditer(r"SECTION\s+(\d+(?:\(\d+\))?(?:\([A-Z]\))?)", t):
        s = m.group(1)
        # Only include substantive DPA sections (not procedural boilerplate)
        try:
            base = int(re.match(r"\d+", s).group())
            if 20 <= base <= 70:  # Core DPA provisions
                sections.add(f"Section {s}")
        except:
            pass
    return sorted(sections)

def extract_respondent_participated(full_text):
    """Check if respondent responded to the complaint."""
    t = full_text.upper()
    non_participation = [
        "FAILED TO RESPOND", "DID NOT RESPOND", "NO RESPONSE",
        "RESPONDENT DID NOT FILE", "RESPONDENT FAILED TO FILE",
        "DESPITE NOTIFICATION", "RESPONDENT HAS NOT RESPONDED"
    ]
    if any(p in t for p in non_participation):
        return False
    if "RESPONDENT" in t and ("RESPONDED" in t or "RESPONSE" in t or "AVERRED" in t):
        return True
    return None  # Unknown

def extract_site_visit(full_text):
    """Check if ODPC conducted a site visit."""
    t = full_text.upper()
    return bool(re.search(r"SITE\s+VISIT|VISITED\s+THE\s+RESPONDENT", t))

def extract_complainant_count(full_text, url):
    """Detect group complaints."""
    fname = url.split("/")[-1].upper()
    # Check filename for "22-OTHERS" style
    m = re.search(r"(\d+)-OTHERS", fname)
    if m:
        return int(m.group(1)) + 1
    m = re.search(r"(\d+)\s+OTHERS", full_text.upper())
    if m:
        return int(m.group(1)) + 1
    # Check for multiple named complainants
    if re.search(r"COMPLAINANTS\b", full_text.upper()):
        return "Multiple -- see PDF"
    return 1

def extract_data_types(full_text):
    """Identify categories of personal data involved."""
    t = full_text.upper()
    types = []
    checks = [
        ("Biometric data",      [r"BIOMETRIC", r"FINGERPRINT", r"IRIS", r"FACE.*RECOGNITION", r"WORLDCOIN"]),
        ("Health data",         [r"HEALTH\s+DATA", r"MEDICAL\s+RECORD", r"PATIENT\s+DATA", r"HEALTH\s+INFORMATION"]),
        ("Financial data",      [r"BANK\s+ACCOUNT", r"FINANCIAL\s+DATA", r"CREDIT\s+SCORE", r"LOAN\s+DATA", r"ACCOUNT\s+DETAILS"]),
        ("Image / photo",       [r"IMAGE\b", r"PHOTO\b", r"PICTURE\b", r"SOCIAL MEDIA.*POST"]),
        ("Contact data",        [r"PHONE\s+NUMBER", r"MOBILE\s+NUMBER", r"EMAIL\s+ADDRESS", r"CONTACT\s+LIST"]),
        ("Identity documents",  [r"NATIONAL\s+ID", r"PASSPORT", r"ID\s+NUMBER", r"GOVERNMENT\s+ID"]),
        ("Location data",       [r"LOCATION\s+DATA", r"GPS", r"ADDRESS\b"]),
        ("Employment data",     [r"EMPLOYMENT", r"PAYROLL", r"SALARY", r"EMPLOYEE\s+DATA"]),
    ]
    for label, patterns in checks:
        for p in patterns:
            if re.search(p, t):
                types.append(label)
                break
    return types or ["Personal data (unspecified)"]

def extract_date(url):
    fname = url.split("/")[-1]
    m = re.match(r"(\d{4})(\d{2})(\d{2})-", fname)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", int(m.group(1))
    m = re.search(r"/uploads/(\d{4})/(\d{2})/", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}", int(m.group(1))
    return None, 0

def extract_outcome(last_text):
    t = last_text.upper()
    if re.search(r"COMPLAINT\s+IS\s+HEREBY\s+DISMISSED|COMPLAINT\s+STANDS\s+DISMISSED|LACKS\s+MERIT|COMPLAINT\s+IS\s+DISMISSED|HEREBY\s+DISMISSED", t):
        return "Dismissed"
    if re.search(r"FOUND\s+LIABLE|RESPONDENT\s+IS\s+HEREBY\s+FOUND|COMPLAINT\s+IS\s+UPHELD|FOUND\s+TO\s+HAVE\s+VIOLATED|HEREBY\s+FOUND\s+GUILTY", t):
        return "Upheld"
    if re.search(r"PARTIALLY\s+UPHELD|PARTIALLY\s+LIABLE", t):
        return "Partially Upheld"
    # Secondary signals
    if "COMPENSATION" in t and re.search(r"KES|KSHS|KENYA SHILLINGS", t):
        return "Upheld"
    if "DISMISSED" in t:
        return "Dismissed"
    return "Unknown"

def extract_compensation(last_text):
    t = last_text.upper()
    # Most specific first: ordered to pay X
    patterns = [
        r"ORDERED\s+TO\s+PAY\s+(?:THE\s+COMPLAINANT\s+)?(?:KENYA\s+SHILLINGS?\s+)?([0-9,]+(?:\.[0-9]+)?)",
        r"PAY\s+(?:THE\s+COMPLAINANT\s+)?(?:KENYA\s+SHILLINGS?\s+)?(?:KES\.?\s*|KSHS\.?\s*)([0-9,]+)",
        r"(?:KES\.?|KSHS\.?)\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:AS\s+COMPENSATION|ONLY|AS\s+DAMAGES)",
        r"COMPENSATION\s+OF\s+(?:KES\.?\s*|KSHS\.?\s*)?([0-9,]+)",
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

def extract_violations(all_text):
    t = all_text.upper()
    violations = []
    checks = [
        ("Unauthorised image/photo use",        [r"IMAGE\b", r"PHOTO\b", r"PICTURE\b", r"SOCIAL MEDIA.*IMAGE"]),
        ("Lack of consent",                     [r"WITHOUT CONSENT", r"NO CONSENT", r"EXPRESS CONSENT", r"CONSENT WAS NOT"]),
        ("Commercial use of personal data",     [r"COMMERCIAL USE", r"COMMERCIAL PURPOSES", r"SECTION 37"]),
        ("Unlawful data disclosure",            [r"UNLAWFUL DISCLOS", r"THIRD PART.*DATA", r"SHARED.*PERSONAL DATA"]),
        ("Failure to prevent data breach",      [r"DATA BREACH", r"BREACH OF SECURITY", r"UNAUTHORISED ACCESS"]),
        ("Unlawful debt collection",            [r"DEBT COLLECTION", r"DEMANDING PAYMENT", r"LOAN.*CONTACT"]),
        ("Failure to respond to erasure request",[r"DELETION\b", r"ERASURE\b", r"PULL DOWN", r"REMOVE.*IMAGE"]),
        ("Failure to notify data breach",       [r"72 HOURS", r"BREACH NOTIFICATION", r"NOTIFY.*BREACH"]),
        ("Obstruction of Data Commissioner",    [r"OBSTRUCT", r"DENIED.*ACCESS.*DATABASE", r"REFUSED.*ACCESS"]),
        ("Failure to conduct DPIA",             [r"DPIA\b", r"DATA PROTECTION IMPACT ASSESSMENT"]),
        ("Unlawful processing",                 [r"SECTION 25\b", r"UNLAWFUL.*PROCESS", r"PROCESS.*UNLAWFUL"]),
        ("Failure to register with ODPC",       [r"REGISTRATION\b.*SECTION", r"REGISTER.*DATA CONTROLLER"]),
        ("Failure to implement security measures",[r"SECTION 41\b", r"APPROPRIATE.*TECHNICAL", r"ORGANISATIONAL MEASURES"]),
    ]
    for label, patterns in checks:
        for p in patterns:
            if re.search(p, t):
                violations.append(label)
                break
    return violations or ["Data protection violation"]

SECTOR_KEYWORDS = {
    "Banking / Financial Services": ["bank", "sacco", "insurance", "microfinance", "diamond trust", "standard chartered", "prime bank", "ncba", "kcb", "equity", "co-op", "jubilee", "britam", "dtb", "trident"],
    "Fintech / Mobile Lending": ["pesa", "loan", "lemon", "rocket", "chapaa", "branch", "faulu", "lending", "whitepath", "fingrow", "bora", "asa-international", "bidii", "mykes", "deltech", "fin-kenya", "trustgro", "platinum", "premier-credit", "taifa", "oya-micro"],
    "Healthcare": ["hospital", "clinic", "health", "medical", "pharmacy", "penda", "becton", "shree", "megahealth"],
    "Education": ["school", "university", "college", "academy", "education", "loans-board", "helb", "kenya-school", "regenesys", "dmi-education", "nairobi-academy"],
    "Technology": ["tech", "digital", "cloud", "truehost", "software", "brainstorm", "tinycost", "capstudio"],
    "Ride-hailing / Logistics": ["bolt", "uber", "logistics", "transport", "courier", "solar-panda", "geosky", "sinoma"],
    "Media / Marketing": ["marketing", "media", "studio", "advertising", "oxygene", "veejaystudio", "glam", "momentum", "oxygene"],
    "Telecom": ["safaricom", "airtel", "telkom", "zuku", "wananchi"],
    "Real Estate / Property": ["real-estate", "property", "facilities", "sequoia", "arrow-facilities"],
    "Credit Reference": ["metropol", "credit-reference", "crb", "transunion"],
    "HR / Recruitment": ["recruitment", "staffing", "brites"],
    "Sports / Entertainment": ["football", "club", "entertainment", "acakoro", "omanyala"],
    "Utilities / Public": ["water", "kenya-power", "county", "ncwsc"],
    "Retail / Commerce": ["shop", "supermarket", "store", "motown", "sistar", "mulla-pride", "casa-vera", "olerai"],
    "Legal / Professional Services": ["advocates", "nyakundi", "cjs"],
    "Agriculture / NGO": ["one-acre", "grass-international"],
}

def guess_sector(fname):
    f = fname.lower()
    for sector, kws in SECTOR_KEYWORDS.items():
        if any(kw in f for kw in kws):
            return sector
    return "General"

# ── Main ──────────────────────────────────────────────────────────────────────

def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {}

def save_progress(results):
    PROGRESS_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False))

def main():
    log("ODPC Determinations OCR -- Sherlock run")
    log("Fetching PDF URL list from odpc.go.ke...")
    all_urls = fetch_all_urls()
    log(f"Total: {len(all_urls)} PDFs\n")

    # Load progress (allows resuming if interrupted)
    results = load_progress()
    log(f"Resuming from {len(results)} previously processed cases\n")

    for i, (url, year) in enumerate(all_urls):
        if url in results:
            log(f"[{i+1}/{len(all_urls)}] SKIP (done): {url.split('/')[-1][:55]}")
            continue

        fname = url.split("/")[-1]
        pdf_path = PDF_DIR / fname
        log(f"[{i+1}/{len(all_urls)}] {fname[:65]}")

        # Download
        if not download_pdf(url, pdf_path):
            log(f"  SKIP: download failed")
            results[url] = {"error": "download_failed", "pdf_url": url}
            continue

        # OCR -- full document
        first_text, last_text, full_text = ocr_all_pages(pdf_path)
        all_text = full_text  # alias for clarity

        # Extract parties
        ocr_complainant, ocr_respondent = extract_parties_ocr(first_text)
        fn_complainant, fn_respondent = extract_parties_filename(url)
        complainant = ocr_complainant or fn_complainant
        respondent = ocr_respondent or fn_respondent

        # Extract all fields
        case_num = extract_case_number(first_text)
        date_str, year_int = extract_date(url)
        complaint_date = extract_complaint_date(full_text)
        outcome = extract_outcome(last_text)
        comp = extract_compensation(last_text)
        violations = extract_violations(all_text)
        data_types = extract_data_types(all_text)
        legal_provisions = extract_legal_provisions(all_text)
        sector = guess_sector(fname)
        enforcement = bool(re.search(r"ENFORCEMENT NOTICE", all_text.upper()))
        prosecution = bool(re.search(
            r"PROSECUTION.*RECOMMEND|RECOMMEND.*PROSECUTION|REFERRED.*PROSECUTION",
            all_text.upper()
        ))
        respondent_participated = extract_respondent_participated(full_text)
        site_visit = extract_site_visit(full_text)
        complainant_count = extract_complainant_count(full_text, url)

        # Calculate processing time if both dates available
        processing_days = None
        if complaint_date and date_str and len(date_str) == 10:
            try:
                from datetime import datetime as dt
                months = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
                         "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
                parts = complaint_date.lower().split()
                if len(parts) == 3:
                    m_num = months.get(parts[1], 0)
                    if m_num:
                        c_date = dt(int(parts[2]), m_num, int(re.sub(r'\D','',parts[0])))
                        d_date = dt.strptime(date_str, "%Y-%m-%d")
                        processing_days = (d_date - c_date).days
            except:
                pass

        result = {
            "pdf_url": url,
            "case_number": case_num,
            "date_determined": date_str or str(year),
            "date_complaint_filed": complaint_date,
            "processing_days": processing_days,
            "year": year_int or int(year),
            "respondent": respondent,
            "complainant": complainant,
            "complainant_count": complainant_count,
            "sector": sector,
            "violation_type": violations,
            "data_types_involved": data_types,
            "legal_provisions_cited": legal_provisions,
            "outcome": outcome,
            "compensation_kes": comp,
            "compensation_usd_approx": round(comp / 129) if comp else None,
            "enforcement_notice": enforcement,
            "prosecution_recommended": prosecution,
            "respondent_participated": respondent_participated,
            "site_visit_conducted": site_visit,
            # Raw OCR text saved so Capybara can generate facts_summary
            # after you push the results to GitHub
            "_raw_ocr_text": full_text[:8000],  # capped at 8000 chars per case
        }
        results[url] = result
        log(f"  {respondent[:45]} | {outcome} | KES {comp}")

        # Save progress every 10 cases
        if (i + 1) % 10 == 0:
            save_progress(results)
            done = sum(1 for v in results.values() if "error" not in v)
            log(f"  -- Progress saved: {done}/{len(all_urls)} complete --\n")

        time.sleep(0.3)

    # Final save
    save_progress(results)

    # Summary stats
    valid = [v for v in results.values() if "error" not in v]
    upheld = sum(1 for v in valid if v.get("outcome") == "Upheld")
    dismissed = sum(1 for v in valid if v.get("outcome") == "Dismissed")
    unknown = sum(1 for v in valid if v.get("outcome") == "Unknown")
    with_comp = [v for v in valid if v.get("compensation_kes")]
    avg_comp = sum(v["compensation_kes"] for v in with_comp) / len(with_comp) if with_comp else 0
    max_comp = max((v["compensation_kes"] for v in with_comp), default=0)

    log("\n=== COMPLETE ===")
    log(f"Total processed: {len(valid)}")
    log(f"Upheld: {upheld} | Dismissed: {dismissed} | Unknown: {unknown}")
    log(f"With compensation: {len(with_comp)}")
    log(f"Average compensation: KES {avg_comp:,.0f}")
    log(f"Highest compensation: KES {max_comp:,.0f}")
    log(f"Output saved to: {OUTPUT_FILE.resolve()}")
    log(f"Upload odpc_ocr_progress.json to GitHub lawlabafrica/odpc-tracker")

    # Write final output (same as progress file, cleaner name)
    OUTPUT_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
