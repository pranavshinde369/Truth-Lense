// extension/content.js

// Helper: Extract text from a selector safely
const getText = (parent, selector) => {
  const el = parent.querySelector(selector);
  return el ? el.innerText.trim() : "";
};

// 1. AMAZON SCRAPER
function scrapeAmazon() {
  const title = getText(document, "#productTitle");
  const reviewNodes = document.querySelectorAll('[data-hook="review"]');

  const reviews = Array.from(reviewNodes).slice(0, 15).map(node => {
    // Extract Star Rating (e.g., "5.0 out of 5 stars")
    const starEl = node.querySelector('[data-hook="review-star-rating"]');
    const starText = starEl ? starEl.innerText : "0";
    const rating = parseFloat(starText.split(" ")[0]) || 0;

    // Extract Date (e.g., "Reviewed in India on 12 March 2024")
    const dateText = getText(node, '[data-hook="review-date"]');
    
    // Check Verified Purchase
    const isVerified = !!node.querySelector('[data-hook="avp-badge"]');

    return {
      text: getText(node, '[data-hook="review-body"]'),
      rating: rating,
      date: dateText,
      verified: isVerified,
      platform: "Amazon"
    };
  }).filter(r => r.text.length > 0);

  return { title, url: window.location.href, reviews };
}

// 2. FLIPKART SCRAPER
function scrapeFlipkart() {
  const title = getText(document, ".B_NuCI") || getText(document, ".mEh187"); // Mobile/Desktop classes
  const reviewNodes = document.querySelectorAll("div.col.EPCmJX"); // Common container

  const reviews = Array.from(reviewNodes).slice(0, 15).map(node => {
    // Flipkart ratings are often in a div like <div class="_3LWZlK _1BLPMq">5<img/></div>
    const starEl = node.querySelector("div._3LWZlK"); 
    const rating = starEl ? parseFloat(starEl.innerText) : 0;
    
    // Flipkart keeps text in "div.t-ZTKy" -> "div > div"
    const textEl = node.querySelector("div.t-ZTKy div > div");
    const text = textEl ? textEl.innerText : "";

    // Flipkart dates are usually in "p._2sc7ZR"
    const dateText = getText(node, "p._2sc7ZR");

    return {
      text: text,
      rating: rating,
      date: dateText,
      verified: true, // Flipkart usually only allows reviews from buyers
      platform: "Flipkart"
    };
  }).filter(r => r.text.length > 0);

  return { title, url: window.location.href, reviews };
}

// Main Logic
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "TRUTHLENS_SCRAPE_PAGE") {
    try {
      const url = window.location.href;
      let data;
      
      if (url.includes("amazon")) {
        data = scrapeAmazon();
      } else if (url.includes("flipkart")) {
        data = scrapeFlipkart();
      } else {
        // Fallback for unsupported sites
        data = { title: document.title, url, reviews: [] };
      }
      
      sendResponse(data);
    } catch (err) {
      console.error("TruthLens Scraper Error:", err);
      sendResponse({ error: err.message });
    }
  }
  return true;
});