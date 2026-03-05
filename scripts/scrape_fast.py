#!/usr/bin/env python3
"""
Fast scraper -- no OCR. Extracts all data from filenames and URL structure only.
Marks outcome as [PENDING OCR] for manual/later verification.
Gets all 313 cases into the database quickly.
"""

import re, json, urllib.request
from pathlib import Path
from datetime import datetime

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
YEARS = ["2023", "2024", "2025", "2026"]
DATA_FILE = Path(__file__).parent.parent / "data" / "determinations.json"

SECTOR_KEYWORDS = {
    "Banking / Financial Services": ["bank", "sacco", "insurance", "microfinance", "diamond trust", "standard chartered", "prime bank", "ncba", "kcb", "equity", "co-op", "jubilee", "britam", "dtb"],
    "Fintech / Mobile Lending": ["pesa", "loan", "lemon", "rocket", "chapaa", "branch", "faulu", "lending", "whitepath", "fingrow", "bora", "asa international", "bidii", "mykes", "deltech", "fin-kenya", "trustgro", "platinum credit", "premier credit", "taifa"],
    "Healthcare": ["hospital", "clinic", "health", "medical", "pharmacy", "penda", "bd-east", "becton", "shree", "megahealth"],
    "Education": ["school", "university", "college", "academy", "education", "loans-board", "helb", "kenya-school", "regenesys", "dmi-education", "nairobi-academy", "kings"],
    "Technology": ["tech", "digital", "cloud", "truehost", "software", "brainstorm", "tinycost"],
    "Ride-hailing / Logistics": ["bolt", "uber", "logistics", "transport", "courier", "solar-panda", "geosky", "sinoma"],
    "Media / Marketing": ["marketing", "media", "studio", "advertising", "oxygene", "capstudio", "veejaystudio", "glam", "momentum"],
    "Telecom": ["safaricom", "airtel", "telkom", "zuku", "wananchi"],
    "Real Estate / Property": ["real-estate", "property", "facilities", "sequoia", "arrow-facilities"],
    "Credit Reference": ["metropol", "credit-reference", "crb", "transunion"],
    "HR / Recruitment": ["recruitment", "staffing", "brites", "brites-mgmt"],
    "Sports / Entertainment": ["football", "club", "entertainment", "acakoro"],
    "Utilities / Public": ["water", "kenya-power", "county", "ncwsc"],
    "Retail / Commerce": ["shop", "supermarket", "store", "motown", "sistar", "mulla-pride", "casa-vera", "olerai", "roma-school"],
    "Legal / Professional Services": ["advocates", "law", "nyakundi", "cjs"],
    "Agriculture / NGO": ["one-acre", "grass-international"],
}

def guess_sector(fname):
    f = fname.lower()
    for sector, kws in SECTOR_KEYWORDS.items():
        if any(kw in f for kw in kws):
            return sector
    return "General"

def extract_parties(url):
    fname = url.split("/")[-1].replace(".pdf", "")
    fname_clean = re.sub(r"^\d{8}-", "", fname)
    parts = re.split(r"-[Vv][Ss]-|-VS-", fname_clean, maxsplit=1)
    if len(parts) == 2:
        complainant = parts[0].replace("-", " ").strip().title()
        respondent = parts[1].replace("-", " ").strip().title()
    else:
        complainant = "See PDF"
        respondent = fname_clean.replace("-", " ").strip().title()
    return complainant, respondent

def extract_date(url):
    fname = url.split("/")[-1]
    m = re.match(r"(\d{4})(\d{2})(\d{2})-", fname)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", int(m.group(1))
    m = re.search(r"/uploads/(\d{4})/(\d{2})/", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}", int(m.group(1))
    return None, 0

def fetch_urls():
    all_urls = []
    for year in YEARS:
        url = f"https://www.odpc.go.ke/{year}-determinations/"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")
        urls = re.findall(r'href="(https://www\.odpc\.go\.ke/wp-content/uploads/[^"]+\.pdf)"', html)
        all_urls.extend(urls)
        print(f"  {year}: {len(urls)} PDFs")
    return all_urls

def main():
    print("Fetching all PDF URLs...")
    all_urls = fetch_urls()
    print(f"Total: {len(all_urls)} PDFs found\n")

    with open(DATA_FILE) as f:
        existing = json.load(f)

    existing_urls = {d.get("pdf_url") for d in existing["determinations"]}
    new_cases = []
    skipped = 0

    for url in all_urls:
        if url in existing_urls:
            skipped += 1
            continue

        fname = url.split("/")[-1]
        complainant, respondent = extract_parties(url)
        date_str, year = extract_date(url)
        sector = guess_sector(fname)

        det = {
            "id": f"{year}-{re.sub(r'[^a-z0-9]', '-', fname.lower().replace('.pdf',''))[:45]}",
            "case_number": "See PDF",
            "date_determined": date_str or str(year),
            "year": year,
            "respondent": respondent,
            "complainant": complainant,
            "complainant_category": "Individual",
            "sector": sector,
            "violation_type": ["See PDF"],
            "violation_summary": f"{complainant} v {respondent}. Full details in linked PDF.",
            "outcome": "See PDF",
            "compensation_kes": None,
            "compensation_usd_approx": None,
            "enforcement_notice": None,
            "prosecution_recommended": None,
            "pdf_url": url,
            "tags": [sector.lower().split("/")[0].strip()]
        }
        new_cases.append(det)

    existing["determinations"].extend(new_cases)
    existing["determinations"].sort(key=lambda x: x.get("date_determined",""), reverse=True)
    existing["metadata"]["total_records"] = len(existing["determinations"])
    existing["metadata"]["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    existing["metadata"]["note"] = "Dataset compiled from all published ODPC determinations. Party names extracted from PDF filenames. Outcome/compensation fields marked 'See PDF' pending OCR verification pass."

    with open(DATA_FILE, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    print(f"Done.")
    print(f"  New cases added: {len(new_cases)}")
    print(f"  Already existed: {skipped}")
    print(f"  Total records: {len(existing['determinations'])}")

if __name__ == "__main__":
    main()
