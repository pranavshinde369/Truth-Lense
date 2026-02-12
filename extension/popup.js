document.addEventListener('DOMContentLoaded', function() {
  const analyzeBtn = document.getElementById('analyzeBtn');
  const statusDiv = document.getElementById('status');
  const resultsArea = document.getElementById('resultsArea');
  
  // UI Elements
  const scoreValue = document.getElementById('scoreValue');
  const safetyBadge = document.getElementById('safetyBadge');
  const verdictText = document.getElementById('verdictText');
  const prosList = document.getElementById('prosList');
  const consList = document.getElementById('consList');
  const botProb = document.getElementById('botProb');
  const footerDot = document.getElementById('footerDot');

  analyzeBtn.addEventListener('click', async () => {
    // 1. Reset UI
    resultsArea.classList.add('hidden');
    statusDiv.textContent = "Connecting to page...";
    analyzeBtn.disabled = true;

    try {
      // 2. Get Active Tab
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab) throw new Error("No active tab found");

      // 3. Try to Scrape (with Auto-Injection fallback)
      let response;
      try {
        response = await sendMessagePromise(tab.id, { type: "TRUTHLENS_SCRAPE_PAGE" });
      } catch (err) {
        // If script is missing, inject it and try again
        console.log("Script missing, injecting now...");
        statusDiv.textContent = "Injecting script...";
        
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ['content.js']
        });
        
        // Wait 100ms for script to initialize
        await new Promise(r => setTimeout(r, 100));
        
        // Retry scrape
        response = await sendMessagePromise(tab.id, { type: "TRUTHLENS_SCRAPE_PAGE" });
      }
      
      if (!response || !response.reviews || response.reviews.length === 0) {
        statusDiv.textContent = "❌ No reviews found. Are you on a product page?";
        analyzeBtn.disabled = false;
        return;
      }

      statusDiv.textContent = `Analyzing ${response.reviews.length} reviews...`;

      // 4. Send to Backend
      const apiRes = await fetch('http://127.0.0.1:8000/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(response)
      });

      if (!apiRes.ok) throw new Error(`Server Error: ${apiRes.status}`);
      const data = await apiRes.json();

      // 5. Render Results
      renderUI(data);
      statusDiv.textContent = "✅ Analysis Complete";

    } catch (err) {
      console.error(err);
      statusDiv.textContent = "Error: " + err.message;
    } finally {
      analyzeBtn.disabled = false;
      analyzeBtn.innerHTML = "Analyze Page";
    }
  });

  // Helper: Wrapper for chrome.tabs.sendMessage
  function sendMessagePromise(tabId, message) {
    return new Promise((resolve, reject) => {
      chrome.tabs.sendMessage(tabId, message, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(response);
        }
      });
    });
  }

  function renderUI(data) {
    resultsArea.classList.remove('hidden');

    // Score & Color
    scoreValue.textContent = data.trust_score;
    scoreValue.className = 'tl-score-value';
    if (data.trust_score >= 80) scoreValue.classList.add('tl-score-safe');
    else if (data.trust_score >= 50) scoreValue.classList.add('tl-score-medium');
    else scoreValue.classList.add('tl-score-low');

    // Badge
    safetyBadge.textContent = data.safety_label;
    safetyBadge.className = 'tl-badge';
    if (data.trust_score >= 80) safetyBadge.classList.add('tl-badge-safe');
    else if (data.trust_score >= 50) safetyBadge.classList.add('tl-badge-warn');
    else safetyBadge.classList.add('tl-badge-risk');

    // Footer Dot
    footerDot.className = 'tl-dot';
    if (data.trust_score >= 80) footerDot.classList.add('tl-dot-safe');
    else footerDot.style.backgroundColor = data.trust_score >= 50 ? '#f97316' : '#dc2626';

    // Text Content
    verdictText.textContent = data.verdict;
    botProb.textContent = data.bot_probability;

    // Lists
    fillList(prosList, data.pros);
    fillList(consList, data.cons);
  }

  function fillList(element, items) {
    element.innerHTML = '';
    (items || ["None found"]).forEach(item => {
      const li = document.createElement('li');
      li.textContent = item;
      element.appendChild(li);
    });
  }
});