import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware

# Import logic functions
from logic import analyze_reviews, check_phishing

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
        
        # Convert Pydantic models to dicts
        review_dicts = []
        for r in payload.reviews:
            if hasattr(r, 'model_dump'):
                review_dicts.append(r.model_dump())
            else:
                review_dicts.append(r.dict())

        analysis_result = analyze_reviews(review_dicts)

        return AnalysisResponse(
            trust_score=analysis_result.get("trust_score", 0),
            sentiment_score=analysis_result.get("sentiment_score", 0.0),
            bot_probability=analysis_result.get("bot_probability", 0),
            safety_label=analysis_result.get("safety_label", "Unknown"),
            pros=analysis_result.get("pros", []),
            cons=analysis_result.get("cons", []),
            verdict=analysis_result.get("verdict", "No verdict available"),
            phishing_status=domain_status
        )

    except Exception as e:
        print(f"🔥 SERVER ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)