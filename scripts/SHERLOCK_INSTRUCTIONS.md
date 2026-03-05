# Sherlock OCR Job -- Instructions for W

## What this does

Runs full OCR on all 313 ODPC enforcement determination PDFs and extracts:

- Parties (complainant and respondent)
- Case number
- Date of determination
- Date complaint was filed
- Processing time (days from complaint to determination)
- Sector
- Violation types
- Data types involved (health, financial, biometric, image, etc.)
- Legal provisions cited (Section 25, 26, 41, 65, etc.)
- Outcome (Upheld / Dismissed / Partially Upheld)
- Compensation ordered (KES amount)
- Enforcement notice issued (yes/no)
- Prosecution recommended (yes/no)
- Whether respondent participated in the investigation
- Whether ODPC conducted a site visit
- Number of complainants (for group complaints)
- Raw OCR text (first 8,000 characters per case)

The raw OCR text is saved so that Capybara can generate a plain-English
facts summary for each case after you push the results to GitHub.

Estimated runtime: 2-3 hours on Sherlock (full page OCR, 313 PDFs).

---

## Step 1 -- SSH into Sherlock and clone the repo

```bash
ssh <sunetid>@login.sherlock.stanford.edu
mkdir ~/odpc_ocr && cd ~/odpc_ocr
git clone https://github.com/lawlabafrica/odpc-tracker.git
cd odpc-tracker/scripts
```

---

## Step 2 -- Check dependencies

```bash
module load python/3.9
tesseract --version
pdftoppm -v
```

If tesseract is not found:

```bash
module spider tesseract
module load tesseract/<version>
```

If pdftoppm / poppler is not found:

```bash
module spider poppler
module load poppler/<version>
```

---

## Step 3 -- Submit the job

```bash
cd ~/odpc_ocr/odpc-tracker/scripts
sbatch sherlock_job.sh
```

You will see:

```
Submitted batch job 12345678
```

---

## Step 4 -- Monitor progress

```bash
# Check job status
squeue -u $USER

# Watch the log in real time
tail -f odpc_ocr_<jobid>.log

# Check how many cases are done
python3 -c "
import json
d = json.load(open('odpc_ocr_progress.json'))
done = len([v for v in d.values() if 'error' not in v])
print(f'{done} / 313 cases processed')
"
```

The script saves progress every 10 cases. If the job times out or is
interrupted, resubmit -- it will resume from where it stopped.

---

## Step 5 -- Download the output

When the job completes (log shows "=== COMPLETE ==="):

```bash
# Check file size -- should be 2-5 MB
ls -lh ~/odpc_ocr/odpc-tracker/scripts/odpc_ocr_progress.json

# Download to your local machine:
scp <sunetid>@login.sherlock.stanford.edu:~/odpc_ocr/odpc-tracker/scripts/odpc_ocr_progress.json ./
```

---

## Step 6 -- Push to GitHub

```bash
# From your local machine, inside the odpc-tracker repo:
cp odpc_ocr_progress.json data/
git add data/odpc_ocr_progress.json
git commit -m "add Sherlock OCR results -- full dataset"
git push
```

Then tell Capybara: "Sherlock OCR results pushed."

Capybara will then:
1. Merge all 313 cases into determinations.json
2. Generate a plain-English facts summary for each case using the raw OCR text
3. Push the completed tracker to GitHub and redeploy

---

## Notes

- The script is fully resumable. If interrupted, resubmit sherlock_job.sh
  and it will skip already-processed cases.
- PDFs are downloaded to ./odpc_pdfs/ (approximately 2-3 GB total).
  You can delete this folder after the job completes.
- Job requests 4 hours and 16GB RAM. This is conservative -- the job
  will likely finish in 2-3 hours.
- This is legitimate research computing use. The ODPC determinations dataset
  is directly relevant to dissertation research on data protection enforcement
  in Kenya. Full-page OCR of court-equivalent documents is standard academic
  research computing.

---

*Prepared by Capybara / Law Lab Africa -- March 2026*
