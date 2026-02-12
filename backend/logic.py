import os
import re
import json
import statistics
from typing import List, Dict, Any
from urllib.parse import urlparse

from dotenv import load_dotenv
from textblob import TextBlob
import Levenshtein

# DistilBERT sentiment (Hugging Face transformers)
try:
    from transformers import pipeline

    hf_sentiment = pipeline(
        "sentiment-analysis",
        model="distilbert-base-uncased-finetuned-sst-2-english",
    )
except Exception:
    hf_sentiment = None

# Try to import Gemini; handle failure gracefully if not installed
try:
    import google.generativeai as genai
except ImportError:
    genai = None

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Domain whitelist for phishing detection
WHITELIST_DOMAINS = [
    "amazon.com",
    "flipkart.com",
    "ebay.com",
    "walmart.com",
    "amazon.in",
    "meesho.com",
]

def clean_json_string(text: str) -> str:
    """
    Cleans the raw response from Gemini to ensure it can be parsed as JSON.
    Removes markdown code blocks (```json ... ```).
    """
    # Remove code block markers
    text = re.sub(r"```[a-zA-Z]*\n", "", text) # Remove ```json or ```
    text = re.sub(r"```", "", text) # Remove closing ```
    
    # Strip whitespace
    text = text.strip()
    
    return text

def check_phishing(url: str) -> str:
    """
    Checks if the URL is a known safe domain, a potential typosquatting attempt, or unknown.
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove port if present
        if ":" in domain:
            domain = domain.split(":")[0]
            
        # Handle "www." and subdomains to get the base domain (e.g., "amazon.in")
        parts = domain.split(".")
        if len(parts) >= 2:
            base_domain = ".".join(parts[-2:])
        else:
            base_domain = domain
            
        if base_domain in WHITELIST_DOMAINS or domain in WHITELIST_DOMAINS:
            return "Safe"
            
        for safe in WHITELIST_DOMAINS:
            # If the domain is very close (1-2 chars different) to a safe one, flag it.
            if Levenshtein.distance(base_domain, safe) <= 2:
                return "Phishing Warning"
        
        return "Suspicious" # Default for unknown/unverified domains
    except:
        return "Unknown"

def analyze_reviews(reviews_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyzes a list of structured review objects:
    [{ 'text': '...', 'rating': 5, 'date': '...', 'verified': True }, ...]
    """
    
    # 1. EXTRACT DATA VECTORS
    texts = [r.get('text', '') for r in reviews_data]
    ratings = [r.get('rating', 0) for r in reviews_data]
    
    # Safety check for empty reviews
    if not texts:
        return {
            "trust_score": 0, 
            "sentiment_score": 0.0,
            "bot_probability": 0,
            "safety_label": "Unknown",
            "pros": [], 
            "cons": [], 
            "verdict": "No reviews found to analyze."
        }

    # 2. SENTIMENT ANALYSIS
    # Prefer DistilBERT (Hugging Face) when available, fall back to TextBlob.
    polarities: List[float] = []

    if hf_sentiment is not None and texts:
        try:
            results = hf_sentiment(texts, truncation=True, max_length=256)
            for res in results:
                label = (res.get("label") or "").upper()
                score = float(res.get("score", 0.5))
                # Map POSITIVE/NEGATIVE into [-1, 1]
                if "POSITIVE" in label:
                    polarity = (2 * score) - 1  # 0..1 -> -1..1
                else:
                    polarity = 1 - (2 * score)
                polarities.append(polarity)
        except Exception:
            polarities = []

    if not polarities:
        for text in texts:
            try:
                blob = TextBlob(text)
                polarities.append(blob.sentiment.polarity)
            except Exception:
                polarities.append(0.0)

    avg_sentiment = statistics.mean(polarities) if polarities else 0.0
    avg_rating = statistics.mean(ratings) if ratings else 0.0

    # 3. SENTIMENT REALITY CHECK
    # Check if high stars (5.0) match high sentiment (>0.5).
    # Normalized rating: 0-5 stars -> -1.0 to 1.0 range
    normalized_rating = (avg_rating - 2.5) / 2.5 
    discrepancy = abs(normalized_rating - avg_sentiment)

    # 4. GEMINI ANALYSIS (for pros/cons + verdict only)
    gemini_output = {
        "pros": [],
        "cons": [],
        "verdict": "Analysis unavailable",
    }

    if genai and GEMINI_API_KEY:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            
            # Use a fast, cost-effective Gemini model
            model = genai.GenerativeModel("models/gemini-2.5-flash")
            
            # Prepare a simplified version of reviews for the prompt to save tokens
            reviews_for_prompt = reviews_data[:15]

            prompt = f"""
            Act as an E-Commerce Fraud Detection Expert. Analyze these reviews:
            {json.dumps(reviews_for_prompt, indent=2)}

            Your Tasks:
            1. Summarize the main pros buyers mention.
            2. Summarize the main cons / complaints buyers mention.
            3. Give a one-sentence buying advice verdict.

            Do NOT estimate bot probability. Focus only on pros, cons, and verdict.

            Output strictly VALID JSON with this structure and nothing else:
            {{
                "pros": ["short point 1", "short point 2"],
                "cons": ["short point 1", "short point 2"],
                "verdict": "<one sentence buying advice>"
            }}
            """
            
            response = model.generate_content(prompt)
            
            if response.text:
                cleaned_json = clean_json_string(response.text)
                parsed_result = json.loads(cleaned_json)
                
                # Update gemini_output with valid keys from response
                gemini_output["pros"] = parsed_result.get("pros", [])
                gemini_output["cons"] = parsed_result.get("cons", [])
                gemini_output["verdict"] = parsed_result.get("verdict", "No verdict provided.")

        except Exception as e:
            print(f"Gemini Analysis Error: {e}")
            gemini_output["verdict"] = "AI Analysis failed (Statistical mode only)."

    # 5. TRUST SCORE CALCULATION (TRADITIONAL ONLY)
    #
    # Goals:
    # - DistilBERT sentiment + star ratings + review volume form the base trust.
    # - Traditional heuristics (duplicates, short texts, sentiment/rating mismatch)
    #   estimate a bot / fake-review probability.
    # - Gemini is used ONLY for pros/cons + verdict, never for the score.

    # A. Base components
    # Sentiment: [-1, 1] -> [0, 100]
    sentiment_component = (avg_sentiment + 1) / 2 * 100
    # Rating: [0, 5] -> [0, 100]
    rating_component = (avg_rating / 5.0) * 100 if avg_rating > 0 else 50

    # Volume component (how many reviews)
    review_count = len(texts)
    if review_count == 0:
        volume_component = 20
    elif review_count < 5:
        volume_component = 45
    elif review_count < 20:
        volume_component = 70
    elif review_count < 50:
        volume_component = 85
    else:
        volume_component = 92

    # Combine into an initial trust score
    score = (
        0.45 * sentiment_component
        + 0.35 * rating_component
        + 0.20 * volume_component
    )

    # B. Heuristic bot probability (no GenAI)
    unique_texts = set(texts)
    duplicates_count = max(0, len(texts) - len(unique_texts))
    duplicate_fraction = (duplicates_count / review_count) if review_count > 0 else 0.0

    short_texts = [t for t in texts if len(t) < 30]
    short_fraction = (len(short_texts) / review_count) if review_count > 0 else 0.0

    try:
        rating_std = statistics.pstdev(ratings) if len(ratings) > 1 else 0.0
    except statistics.StatisticsError:
        rating_std = 0.0

    bot_prob = 0.0
    # Many duplicates → likely templated / copy-paste reviews
    bot_prob += duplicate_fraction * 60.0
    # Mostly ultra-short reviews
    bot_prob += short_fraction * 30.0
    # Big mismatch between stars and text sentiment
    if discrepancy > 0.6:
        bot_prob += min(20.0, (discrepancy - 0.6) * 50.0)
    # All 5-star with almost no variance and enough reviews → light suspicion
    if review_count >= 20 and rating_std < 0.2 and avg_rating > 4.7:
        bot_prob += 10.0

    bot_prob = max(0, min(100, int(round(bot_prob))))

    # C. Discrepancy penalty (Text vs stars)
    if discrepancy > 0.5:
        score -= (discrepancy - 0.5) * 30

    # D. Repetitive text penalty (duplicate detection)
    if duplicates_count > 0:
        score -= min(duplicates_count * 4, 16)

    # E. Short review penalty (low-effort reviews)
    avg_len = statistics.mean([len(t) for t in texts]) if texts else 0
    if avg_len < 15:
        score -= 8

    # F. Low volume uncertainty
    if review_count < 5:
        score -= 5

    # Clamp Score between 0 and 100
    final_score = max(0, min(100, int(round(score))))

    # Safety label tuned for a "very safe" UX on genuine products
    if final_score >= 80:
        label = "Likely Authentic"
    elif final_score >= 50:
        label = "Moderate Risk"
    else:
        label = "High Risk / Caution"

    return {
        "trust_score": final_score,
        "sentiment_score": round(avg_sentiment, 2),
        "bot_probability": bot_prob,
        "pros": gemini_output.get("pros", []),
        "cons": gemini_output.get("cons", []),
        "verdict": gemini_output.get("verdict", ""),
        "safety_label": label,
    }