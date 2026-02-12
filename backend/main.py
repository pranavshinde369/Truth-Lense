import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware

# Import logic functions
from logic import analyze_reviews, analyze_site_risk, check_phishing

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ROBUST DATA MODELS ---
class ReviewItem(BaseModel):
    text: str
    rating: float = 0.0
    date: str = ""
    verified: bool = False
    platform: str = "Unknown"

class ScrapeRequest(BaseModel):
    url: str
    # FIX: Default value added so it never fails if title is missing
    title: str = "Unknown Product"
    reviews: List[ReviewItem] = []
    # Optional raw page text for generic site-risk analysis (non-Amazon/Flipkart)
    page_text: Optional[str] = ""

class AnalysisResponse(BaseModel):
    trust_score: int
    sentiment_score: float
    bot_probability: int
    safety_label: str
    pros: List[str]
    cons: List[str]
    verdict: str
    phishing_status: str

# --- ERROR HANDLER ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(f"❌ VALIDATION ERROR: {exc}")
    return JSONResponse(status_code=422, content={"detail": str(exc)})

# --- ENDPOINTS ---
@app.get("/")
def home():
    return {"status": "TruthLens Backend is Running"}

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_product(payload: ScrapeRequest):
    print(f"📥 Analyzing: {payload.title} ({len(payload.reviews)} reviews)")

    try:
        domain_status = check_phishing(payload.url)
        page_text = payload.page_text or ""

        # Convert Pydantic models to dicts
        review_dicts = []
        for r in payload.reviews:
            if hasattr(r, "model_dump"):
                review_dicts.append(r.model_dump())
            else:
                review_dicts.append(r.dict())

        # If no reviews were scraped (unsupported site, or rating summary only),
        # fall back to a domain + page-text safety assessment so TruthLens still "works".
        if not review_dicts:
            site_result = analyze_site_risk(domain_status, page_text)

            return AnalysisResponse(
                trust_score=int(site_result.get("site_score", 0)),
                sentiment_score=0.0,
                bot_probability=0,
                safety_label=site_result.get("site_label", "Unknown"),
                pros=site_result.get("pros", []),
                cons=site_result.get("cons", []),
                verdict=site_result.get("verdict", ""),
                phishing_status=domain_status,
            )

        # Normal path: we have structured reviews (Amazon / Flipkart / others we support)
        analysis_result = analyze_reviews(review_dicts)

        base_trust = int(analysis_result.get("trust_score", 0))
        sentiment_score = float(analysis_result.get("sentiment_score", 0.0))
        bot_prob = int(analysis_result.get("bot_probability", 0))
        review_count = len(review_dicts)

        # Final calibration step: on clearly official, safe domains with good sentiment,
        # avoid overly harsh scores. This matches the "very_safe" UX you want.
        calibrated_trust = base_trust
        if domain_status == "Safe":
            if review_count >= 50 and sentiment_score > 0.4 and bot_prob <= 60:
                calibrated_trust = max(calibrated_trust, 80)
            elif review_count >= 20 and sentiment_score > 0.3 and bot_prob <= 70:
                calibrated_trust = max(calibrated_trust, 70)

        return AnalysisResponse(
            trust_score=calibrated_trust,
            sentiment_score=round(sentiment_score, 2),
            bot_probability=bot_prob,
            safety_label=analysis_result.get("safety_label", "Unknown"),
            pros=analysis_result.get("pros", []),
            cons=analysis_result.get("cons", []),
            verdict=analysis_result.get("verdict", "No verdict available"),
            phishing_status=domain_status,
        )

    except Exception as e:
        print(f"🔥 SERVER ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)