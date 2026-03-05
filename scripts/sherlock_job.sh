#!/bin/bash
#SBATCH --job-name=odpc_ocr
#SBATCH --time=02:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=4
#SBATCH --output=odpc_ocr_%j.log
#SBATCH --mail-type=END,FAIL

echo "Starting ODPC OCR job at $(date)"
echo "Node: $HOSTNAME"

# Load required modules (adjust if Sherlock module names differ)
module load python/3.9 2>/dev/null || true
module load tesseract 2>/dev/null || true

# Check dependencies
echo "Checking dependencies..."
python3 --version
tesseract --version | head -1
pdftoppm -v 2>&1 | head -1

# Run the OCR script
python3 sherlock_ocr.py

echo "Job complete at $(date)"
echo "Output file: odpc_ocr_progress.json"
