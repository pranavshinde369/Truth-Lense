# TruthLens – Chrome Extension Prototype

TruthLens is a hackathon‑ready Chrome extension + local FastAPI backend that helps users decide **whether to trust an e‑commerce product or site**.

It works in two modes:

- **Marketplace review mode (Amazon / Flipkart)**:  
  Analyzes product reviews to detect fake/botted patterns, estimate trust, and summarize pros/cons.
- **Site‑level risk mode (any other site, e.g. Meesho or random shops)**:  
  Analyzes the domain and visible page text (and price vs Amazon.in) to estimate whether the **website itself** looks risky or scammy.

Everything runs locally except:

- Optional **Gemini** calls for pros/cons/verdict text.
- A lightweight HTML request to **Amazon.in search** for price sanity checking.

There is **no database** and no persistence; it’s a vertical slice meant to demo end‑to‑end AI + browser integration.

---

## 1. Project Structure

```text
TruthLens/
├── backend/
│   ├── venv/                   # (You create this virtualenv)
│   ├── main.py                 # FastAPI server entry point
│   ├── logic.py                # Core analysis logic
│   ├── requirements.txt        # Python dependencies
│   └── .env                    # Stores GEMINI_API_KEY (optional)
├── extension/
│   ├── manifest.json           # Chrome extension manifest (MV3)
│   ├── popup.html              # UI shown when clicking the extension
│   ├── popup.css               # Popup styling
│   ├── popup.js                # Popup logic (talks to backend)
│   ├── content.js              # Scraper + page text collector
│   └── icons/                  # Placeholder icons
│       ├── icon16.png
│       ├── icon48.png
│       └── icon128.png
└── README.md                   # This file
```

---

## 2. Backend Setup (FastAPI + DistilBERT + Gemini)

### 2.1. Prerequisites

- **Python 3.9+**
- `pip` on your PATH

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

This installs (among others):

- **fastapi**, **uvicorn**
- **transformers**, **torch** (DistilBERT sentiment)
- **textblob** (fallback sentiment)
- **google-generativeai** (Gemini, optional)
- **python-levenshtein** (phishing + duplicate detection)
- **requests** (price sanity check vs Amazon.in)

### 2.4. Configure your Gemini API key (optional)

Edit the `.env` file in `backend/`:

```text
GEMINI_API_KEY=your_gemini_api_key_here
```

- If this value is **valid**, the backend uses Gemini to generate pros/cons + verdict.
- If the key is **missing** or the call **fails**, the backend still works using:
  - DistilBERT + heuristics for scoring.
  - Simple fallback pros/cons/verdict.

### 2.5. Run the backend server

From `backend/` with the virtual environment active:

```bash
python main.py
```

This starts the FastAPI app using Uvicorn on:

- `http://127.0.0.1:8000`

You can verify it’s running by visiting:

- `http://127.0.0.1:8000/`

You should see a small JSON response similar to:

```json
{"status": "TruthLens Backend is Running"}
```

---

## 3. Chrome Extension Setup

### 3.1. Load the extension in Chrome

1. Open Chrome.
2. Go to `chrome://extensions`.
3. Turn on **Developer mode** (top‑right toggle).
4. Click **“Load unpacked”**.
5. Select the `TruthLens/extension` folder.

Chrome should now show the **TruthLens** extension with its icon.

### 3.2. What the extension does

When you click the TruthLens icon:

- The popup shows a big **“Analyze Page”** button and a status line.
- On click:
  1. It injects or talks to `content.js` on the active tab.
  2. The content script:
     - If the URL contains **`amazon`**:
       - Scrapes product title (`#productTitle`).
       - Scrapes up to 15 review blocks with:
         - Review text
         - Star rating
         - Review date
         - Verified purchase flag
     - If the URL contains **`flipkart`**:
       - Scrapes product title (`.B_NuCI` / `.mEh187`).
       - Scrapes review cards (`div.col.EPCmJX`) with text, rating, date (verified assumed `true`).
     - For **all sites**:
       - Collects compacted `page_text` from the DOM for site‑level risk analysis.
  3. The popup sends a POST request to `http://127.0.0.1:8000/analyze` with:
     - `url`, `title`
     - `reviews`: array of structured review objects (Amazon/Flipkart) **or** an empty list on other sites.
     - `page_text`: visible page text.
  4. The backend analyzes either:
     - **Review trust** (Amazon/Flipkart mode), or
     - **Site‑level risk** (any other site, including Meesho).
  5. The popup displays:
     - **Trust Score** (big colored number).
     - **Safety badge** (“Likely Authentic”, “Moderate Risk”, “High Risk / Possible Scam”, etc.).
     - **“Why this score?” strip** with 3–5 bullet signals.
     - **Pros & Cons** lists.
     - **Verdict** text.
     - **Bot Probability** in the footer.

---

## 4. How the analysis works

### 4.1. Marketplace review mode (Amazon / Flipkart)

Triggered when structured reviews are scraped.

- **Sentiment (DistilBERT)**
  - Model: `distilbert-base-uncased-finetuned-sst-2-english`.
  - Each review → POSITIVE/NEGATIVE + confidence → mapped to a continuous score in \[-1, 1\].
  - Average sentiment → mapped to 0–100.

- **Traditional bot / fake‑review heuristics**
  - Duplicate review texts → possible copy‑paste/bot.
  - Very short reviews → low effort.
  - Rating vs sentiment mismatch:
    - 5★ but text is negative → suspicious.
  - Rating variance:
    - All 5★ with almost no variance → mildly suspicious if enough reviews.
  - Combined into a numeric **`bot_probability` 0–100** (shown in the footer and “Why this score?” strip).

- **Trust score (0–100)**
  - Combines:
    - Sentiment component
    - Rating component
    - Review volume component (few reviews → lower confidence)
  - Applies small penalties for:
    - Sentiment/rating mismatch
    - Duplicate texts
    - Ultra‑short reviews
    - Very low review count
  - Final label:
    - `>= 80` → **“Likely Authentic”**
    - `>= 50` → **“Moderate Risk”**
    - `< 50` → **“High Risk / Caution”**

- **Gemini summarization (optional)**
  - Model: e.g. `gemini-1.5-flash` / `gemini-2.5-flash` via `google-generativeai`.
  - Input: a small batch of structured reviews.
  - Output (JSON only):
    - `pros`: bullet points.
    - `cons`: bullet points.
    - `verdict`: one‑sentence buying advice.
  - **Important**: Gemini does **not** influence the numeric trust score; it only generates text.

- **Explainability (“Why this score?”)**
  - Example bullets for a product on Amazon:
    - `Sentiment: 0.82 (DistilBERT)`
    - `Bot probability: 15% (duplicates/short-review heuristics)`
    - `Reviews analyzed: 120 (Amazon)`
    - `Domain: amazon.in (Safe)`

### 4.2. Site‑level risk mode (any other site)

Triggered when **no structured reviews** are scraped (e.g. Meesho product page, random D2C shop).

- **Phishing / typosquatting (Levenshtein)**
  - Whitelist domains: `amazon.com`, `amazon.in`, `flipkart.com`, `ebay.com`, `walmart.com`, `meesho.com`, etc.
  - Exact match → **Safe**.
  - Distance ≤ 2 from a whitelist domain (e.g. `amaz0n.in`) → **Phishing Warning**.
  - Anything else → **Suspicious / Unverified**.

- **Page‑content risk heuristics**
  - Flags aggressive scam signals:
    - “80–100% OFF”, “only today”, “limited stock”, “win big”, etc.
  - Flags payment oddities:
    - “UPI only”, “Paytm only”, “Bitcoin”.
  - Flags dangerous policies:
    - “No refund”, “no returns”, “non‑refundable”.
  - Adds positive signals if it sees:
    - “Return policy”, “refund policy”, “contact us”, “privacy policy”, “terms & conditions”.

- **Price sanity check vs Amazon.in**
  - Extracts a **local price** from the current page (`₹2,999`, `Rs. 1,499`, etc.).
  - Searches `amazon.in` with the product title and extracts a **reference price** from search results HTML.
  - If local price is more than **50% cheaper** than the reference:
    - Lowers the site score.
    - Adds a clear con:
      - “Price appears much lower than on major marketplaces (local ≈ ₹X vs reference ≈ ₹Y).”
  - If prices are similar:
    - Adds a small pro:
      - “Price appears broadly in line with major marketplaces.”

- **Site‑level trust & label**
  - Score and label depend on:
    - Domain status (Safe / Phishing Warning / Suspicious).
    - Scammy language.
    - Payment/refund wording.
    - Price sanity.
  - Labels:
    - `>= 75` → **“Likely Legitimate (Site‑level)”**
    - `>= 45` → **“Unverified Site / Use Caution”**
    - `< 45` → **“High Risk / Possible Scam”**

- **Explainability (“Why this score?”)**
  - Example bullets for a random store:
    - `Mode: Site-level risk (no product reviews scraped)`
    - `Domain: example-shop.com (Suspicious)`
    - `Price sanity: Possible anomaly vs major marketplaces (could be counterfeit/scam).`

---

## 5. Demo Instructions (Hackathon Workflow)

1. **Start backend**
   - Open a terminal.
   - Navigate to `TruthLens/backend`.
   - Activate the virtualenv.
   - Run `python main.py`.
2. **Load extension**
   - In Chrome, load the unpacked extension from `TruthLens/extension`.
3. **Demo 1 – Amazon / Flipkart (review trust)**
   - Open a popular product on Amazon.in or Flipkart.
   - Click the TruthLens icon → **Analyze Page**.
   - Talk through:
     - Trust Score + Safety badge.
     - Pros/Cons + verdict.
     - “Why this score?” bullets (sentiment, bot probability, reviews analyzed, domain).
4. **Demo 2 – Meesho or unknown shop (site risk + price sanity)**
   - Open a product page on Meesho or a random store with a strong discount.
   - Click **Analyze Page**.
   - Show:
     - Site‑level Trust Score and label.
     - Pros/Cons mentioning scam language, policies, and price anomaly (if any).
     - “Why this score?” bullets highlighting **Site‑level risk** mode and domain status.

---

## 6. Notes & Limitations

- This is **not** production‑ready; it’s a **vertical slice** for demo purposes.
- No database, no auth, minimal error handling.
- Gemini usage is **optional** and does not affect the numeric scores.
- DistilBERT + heuristics are tuned to be:
  - **Conservative about calling genuine products “fake”** on official marketplaces.
  - **Cautious** on unknown sites, especially with typosquatting or extreme discounts.

You can extend TruthLens by adding more marketplaces, richer UI (e.g. highlighting suspicious reviews directly on the page), or deeper OSINT / reputation checks for domains.


