# Sherlock OCR Job -- Instructions for W

## What this does

Runs OCR on all 313 ODPC enforcement determination PDFs, extracts structured data
(parties, outcome, compensation, violation type, enforcement notices), and saves
everything to a JSON file. You run it, I process the output.

Estimated runtime: 45-90 minutes on Sherlock.

---

## Step 1 -- Copy the scripts to Sherlock

SSH into Sherlock and clone the repo directly:

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

If pdftoppm is not found:

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

# Watch the log
tail -f odpc_ocr_<jobid>.log

# Check how many cases done
python3 -c "import json; d=json.load(open('odpc_ocr_progress.json')); print(len(d), 'cases processed')"
```

The script saves progress every 10 cases. If interrupted, resubmit and it resumes.

---

## Step 5 -- Retrieve the output

```bash
# On your local machine:
scp <sunetid>@login.sherlock.stanford.edu:~/odpc_ocr/odpc-tracker/scripts/odpc_ocr_progress.json ./
```

---

## Step 6 -- Push to GitHub

```bash
cp odpc_ocr_progress.json /path/to/odpc-tracker/data/
cd /path/to/odpc-tracker
git add data/odpc_ocr_progress.json
git commit -m "add Sherlock OCR results"
git push
```

Then tell Capybara: "Sherlock OCR results pushed." I will merge them into
the determinations.json and update the tracker automatically.

---

## Notes

- The script is resumable. Resubmit if it times out -- it skips done cases.
- PDFs download to ./odpc_pdfs/ (~2-3 GB). Delete after job completes.
- Job requests 2 hours and 8GB RAM. Increase --time to 04:00:00 if needed.
- Legitimate research computing use -- ODPC enforcement data is directly
  relevant to dissertation research on data protection law in Kenya.

---

*Prepared by Capybara / Law Lab Africa -- March 2026*
