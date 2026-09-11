# Virtual Game Odds Analyzer

A Flask application that uploads football betting screenshots, runs OCR and image preprocessing, extracts match rows and odds, calculates totals, and displays the results in a table.

## Features

- Upload JPG, JPEG, PNG, and WEBP screenshots
- Show an image preview before analysis
- Use OpenCV preprocessing and Tesseract OCR for row and odds detection
- Extract team names and five odds per match row
- Calculate the total for each match
- Allow users to manually adjust extracted values and recalculate
- Export results to CSV

## Project Structure

```text
virtual-odds-analyzer/
├── app.py
├── requirements.txt
├── README.md
├── templates/
│   └── index.html
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── script.js
├── uploads/
└── processing/
    └── ocr.py
```

## Windows Setup

1. Install Python 3.11+ from https://www.python.org/downloads/windows/
2. Open a Command Prompt and create a virtual environment:

```powershell
cd path\to\virtual-odds-analyzer
py -m venv .venv
.venv\Scripts\activate
```

3. Install project dependencies:

```powershell
pip install -r requirements.txt
```

4. Install Tesseract OCR for Windows:

- Download the installer from: https://github.com/UB-Mannheim/tesseract/wiki
- Install it to a directory such as:

```text
C:\Program Files\Tesseract-OCR\
```

5. If Tesseract is not automatically found, configure the path in Python by editing `processing/ocr.py` and adding:

```python
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

6. Start the app:

```powershell
python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

## Linux/macOS Setup

```bash
cd virtual-odds-analyzer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo apt-get update
sudo apt-get install -y tesseract-ocr
python app.py
```

## Notes

- The image extractor is tailored for screenshots with match rows like the example provided.
- You can modify the calculation logic in `processing/ocr.py` by updating `calculate_result()`.
- If OCR struggles with a row, the UI lets you manually correct the values and recalculate the total.
