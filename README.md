# TruthLens – Chrome Extension Prototype

TruthLens is a simple, end-to-end prototype for a Chrome Extension that analyzes Amazon product pages to:

- Detect potentially fake / botted reviews
- Summarize key **pros** and **cons** using GenAI (Google Gemini)
- Check whether the site looks **safe** or potentially **phishy**

This project is intentionally lightweight and hackathon-friendly. There is no database or persistence; everything runs locally.

---

## 1. Project Structure

```text
TruthLens/
├── backend/
│   ├── venv/                   # (You create this virtualenv)
│   ├── main.py                 # FastAPI server entry point
│   ├── logic.py                # Core analysis logic
│   ├── requirements.txt        # Python dependencies
│   └── .env                    # Stores GEMINI_API_KEY
├── extension/
│   ├── manifest.json           # Chrome extension manifest (MV3)
│   ├── popup.html              # UI shown when clicking the extension
│   ├── popup.css               # Popup styling
│   ├── popup.js                # Popup logic (talks to backend)
│   ├── content.js              # Scrapes Amazon product pages
│   └── icons/                  # Placeholder icons
│       ├── icon16.png
│       ├── icon48.png
│       └── icon128.png
└── README.md                   # This file
```

---

## 2. Backend Setup (FastAPI + Gemini + DistilBERT)

### 2.1. Prerequisites

- Python 3.9+ installed
- `pip` available on your PATH

### 2.2. Create and activate a virtual environment

From the `TruthLens/backend` folder:

```bash
cd backend
python -m venv venv
```

On **Windows (PowerShell)**:

```bash
venv\Scripts\Activate.ps1
```

On **macOS / Linux**:

```bash
source venv/bin/activate
```

### 2.3. Install dependencies (includes Transformers)

From inside the virtual environment:

```bash
pip install -r requirements.txt
```

### 2.4. Configure your Gemini API key (optional)

Edit the `.env` file in `backend/`:

```text
GEMINI_API_KEY=your_gemini_api_key_here
```

- If this value is **valid**, the backend will call the real Google Gemini API for review summarization and bot-score estimation.
- If the key is **missing** or the call **fails**, the backend automatically falls back to **mock data** (fixed pros/cons/verdict). This is perfect for quickly demoing the UI with no external dependencies.

### 2.5. Run the backend server

From `backend/` with the virtual environment active:

```bash
python main.py
```

This starts the FastAPI app using Uvicorn on:

- `http://127.0.0.1:8000`

You can verify it’s running by visiting:

- `http://127.0.0.1:8000/health`

You should see a small JSON response: `{"status": "ok"}`.

---

## 3. Chrome Extension Setup

### 3.1. Load the extension in Chrome

1. Open Chrome.
2. Go to `chrome://extensions`.
3. Turn on **Developer mode** (top-right toggle).
4. Click **“Load unpacked”**.
5. Select the `TruthLens/extension` folder.

Chrome should now show the **TruthLens** extension in the list, with a small icon.

### 3.2. What the extension does

- The popup shows an **“Analyze Page”** button.
- When you click it on an Amazon product page:
  1. It injects `content.js` into the active tab.
  2. The content script scrapes:
     - Product title (`#productTitle`)
     - Up to **10** top reviews (`[data-hook="review-body"]` text content)
  3. The popup sends a POST request to `http://127.0.0.1:8000/analyze` with:
     - `url` – the current page URL
     - `reviews` – array of review strings
  4. The backend:
     - Checks for **phishing/typosquatting** using Levenshtein distance against a whitelist (`amazon.com`, `flipkart.com`).
     - Runs **TextBlob** sentiment analysis across all reviews.
     - Calls **Google Gemini** (or uses mock data) to get:
       - `pros` (3 bullet points)
       - `cons` (3 bullet points)
       - `bot_score` (0–100 likelihood of reviews being botted)
       - `verdict` (short textual summary)
     - Combines everything into a single **trust score (0–100)**.
  5. The popup displays:
     - **Trust Score** (big colored number)
     - **Safety badge** (e.g. “Likely Safe”, “Caution Advised”, “High Risk (Possible Phishing)”)
     - **Pros & Cons** lists
     - **Verdict** text

---

## 4. Demo Instructions (Hackathon Workflow)

1. **Start backend**
   - Open a terminal.
   - Navigate to `TruthLens/backend`.
   - Activate the virtualenv.
   - Run `python main.py`.
2. **Load extension**
   - In Chrome, load the unpacked extension from `TruthLens/extension`.
3. **Open an Amazon product page**
   - For example, any product on `https://www.amazon.com/...`.
4. **Run TruthLens**
   - Click the TruthLens icon in the Chrome toolbar.
   - Click **“Analyze Page”**.
   - Wait a couple of seconds for the results to appear.

You should now see the Trust Score, safety label, pros/cons, and overall verdict. If Gemini is not configured, the values will still populate using the built-in mock response.

---

## 5. Model Stack (for judges / explainability)

- **Sentiment Analysis – DistilBERT**
  - Model: `distilbert-base-uncased-finetuned-sst-2-english` (via `transformers`).
  - Used to convert each review into a continuous sentiment score in \[-1, 1\], then averaged.
  - Fast, lightweight, and widely used for Positive/Negative sentiment.

- **Fake Review / Bot Detection – Google Gemini**
  - Model: `gemini-1.5-flash` (via `google-generativeai`).
  - Given a small batch of structured reviews (text, rating, date, verified), it returns:
    - `pros`, `cons`
    - `bot_probability` (0–100)
    - `verdict` (one-sentence buying advice)
  - The backend treats Gemini as **advisory**: it can lower the trust score, but cannot by itself drive clearly good products on official sites down to 0.

- **Phishing / Scam Detection – Levenshtein Distance**
  - Library: `python-levenshtein`.
  - Compares the current domain to a whitelist (`amazon.com`, `amazon.in`, `flipkart.com`, etc.).
  - If the domain is 1–2 characters away from a known-good domain (e.g. `amaz0n.com`), it flags `"Phishing Warning"`.

## 6. Notes & Limitations

- This is **not** production-ready; it’s a **vertical slice** designed for demo purposes.
- No database, no user accounts, and minimal error handling by design.
- Gemini usage is **optional** – if the API key is missing, the system still works with DistilBERT + heuristics (you just lose GenAI pros/cons).
- The scoring is intentionally tuned to be **conservative about calling genuine products “fake”**, especially on official marketplaces.

Feel free to extend this prototype with richer UI, more marketplaces, or additional models as part of your hackathon work.

