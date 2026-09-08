const form = document.querySelector("#predictionForm");
const prediction = document.querySelector("#prediction");
const range = document.querySelector("#range");
const confidenceMeter = document.querySelector("#confidenceMeter");
const confidenceText = document.querySelector("#confidenceText");
const modelStatus = document.querySelector("#modelStatus");
const satellitePreview = document.querySelector("#satellitePreview");
const satelliteEmpty = document.querySelector("#satelliteEmpty");
const formStatus = document.querySelector("#formStatus");
const geocodeButton = document.querySelector("#geocodeButton");
const currentLocationButton = document.querySelector("#currentLocationButton");
const previewSatelliteButton = document.querySelector("#previewSatelliteButton");
const nudgeStep = document.querySelector("#nudgeStep");
const metricR2 = document.querySelector("#metricR2");
const metricMape = document.querySelector("#metricMape");
const metricP50 = document.querySelector("#metricP50");

// ── Blockchain panel elements ─────────────────────────────────────────────────
const blockchainPanel = document.querySelector("#blockchainPanel");
const bcStatus = document.querySelector("#bcStatus");
const bcStored = document.querySelector("#bcStored");
const bcStoredCard = document.querySelector("#bcStoredCard");
const bcIndex = document.querySelector("#bcIndex");
const bcContract = document.querySelector("#bcContract");
const bcTxHash = document.querySelector("#bcTxHash");
const bcImageHash = document.querySelector("#bcImageHash");
const bcReportHash = document.querySelector("#bcReportHash");
const bcIpfsCid = document.querySelector("#bcIpfsCid");

function formPayload() {
  return Object.fromEntries(new FormData(form).entries());
}

function setStatus(message) {
  formStatus.textContent = message || "";
}

function setSatelliteImage(url) {
  satellitePreview.src = `${url}?t=${Date.now()}`;
  satellitePreview.style.display = "block";
  satelliteEmpty.style.display = "none";
  satellitePreview.closest(".satellite-preview").classList.add("has-image");
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Request failed");
  return result;
}

function applyCoordinates(result) {
  form.elements.latitude.value = Number(result.latitude).toFixed(6);
  form.elements.longitude.value = Number(result.longitude).toFixed(6);
  if (result.zoom !== undefined) form.elements.zoom.value = result.zoom;
}

function coordinatesReady() {
  return form.elements.latitude.value !== "" && form.elements.longitude.value !== "";
}

async function refreshSatellitePreview(message = "Fetching satellite preview...") {
  setStatus(message);
  const result = await postJson("/api/satellite-preview", formPayload());
  applyCoordinates(result);
  setSatelliteImage(result.satellite_image);
  setStatus(`Preview centered at ${Number(result.latitude).toFixed(6)}, ${Number(result.longitude).toFixed(6)}.`);
  return result;
}

function nudgeCoordinates(direction) {
  if (!coordinatesReady()) {
    setStatus("Fill latitude and longitude before nudging.");
    return false;
  }

  const meters = Number(nudgeStep.value || 50);
  const lat = Number(form.elements.latitude.value);
  const lng = Number(form.elements.longitude.value);
  const latDelta = meters / 111320;
  const lngDelta = meters / (111320 * Math.cos((lat * Math.PI) / 180));

  if (direction === "north") form.elements.latitude.value = (lat + latDelta).toFixed(6);
  if (direction === "south") form.elements.latitude.value = (lat - latDelta).toFixed(6);
  if (direction === "east") form.elements.longitude.value = (lng + lngDelta).toFixed(6);
  if (direction === "west") form.elements.longitude.value = (lng - lngDelta).toFixed(6);
  return true;
}

function updateModelMetrics(model) {
  if (!model) return;
  metricR2.textContent = model.r2 ?? "--";
  metricMape.textContent = model.mape !== undefined ? `${model.mape}%` : "--";
  metricP50.textContent = model.p50_error !== undefined ? `${model.p50_error}%` : "--";
}

// ── Blockchain proof renderer ─────────────────────────────────────────────────

// ── Chainlink panel elements ─────────────────────────────────────────────────
const chainlinkPanel = document.querySelector("#chainlinkPanel");
const clInr = document.querySelector("#clInr");
const clUsd = document.querySelector("#clUsd");
const clRate = document.querySelector("#clRate");
const clLive = document.querySelector("#clLive");
const clSource = document.querySelector("#clSource");
const clNote = document.querySelector("#clNote");

function renderChainlink(cl) {
  if (!cl) return;
  chainlinkPanel.style.display = "block";

  if (cl.available) {
    const inrFmt = new Intl.NumberFormat("en-IN", {
      style: "currency", currency: "INR", maximumFractionDigits: 0,
    }).format(cl.inr);
    clInr.textContent = inrFmt;
    clUsd.textContent = cl.usd_fmt || `$${cl.usd?.toLocaleString()}`;
    clRate.textContent = `1 USD = ₹${cl.rate?.toFixed(2)}`;
    clLive.textContent = cl.live ? "Live Oracle ✓" : "Simulated (Ganache)";
    clLive.style.color = cl.live ? "var(--accent)" : "#f59e0b";
    clSource.textContent = cl.rate_source || "Chainlink oracle";
    clNote.textContent = cl.live
      ? "Exchange rate sourced live from Chainlink decentralised oracle on Sepolia."
      : "Running on Ganache — deploy to Sepolia for live Chainlink rates. Rate simulated at ₹83.50/USD.";
  } else {
    clInr.textContent = "—";
    clUsd.textContent = "—";
    clRate.textContent = "Unavailable";
    clLive.textContent = "Offline";
    clSource.textContent = cl.source || "Chainlink not available";
  }
}

function shortHash(h) {
  if (!h || h.length < 20) return h || "—";
  return h.slice(0, 14) + "…" + h.slice(-8);
}

function renderBlockchainProof(bc) {
  if (!bc) return;
  blockchainPanel.style.display = "block";
  setTimeout(() => blockchainPanel.scrollIntoView({ behavior: "smooth", block: "nearest" }), 100);

  if (bc.stored) {
    bcStored.textContent = "Stored ✓";
    bcStoredCard.classList.add("bc-card--green");
    bcStatus.textContent = "Valuation stored immutably on the Ethereum blockchain.";
    bcIndex.textContent = bc.chain_index ?? "—";
    bcContract.textContent = shortHash(bc.contract);
    bcContract.title = bc.contract || "";
    bcTxHash.textContent = bc.tx_hash || "—";
    bcTxHash.title = bc.tx_hash || "";
    bcImageHash.textContent = bc.image_hash || "—";
    bcImageHash.title = bc.image_hash || "";
    bcReportHash.textContent = bc.report_hash || "—";
    bcReportHash.title = bc.report_hash || "";
    bcIpfsCid.textContent = bc.report_cid || "—";
    bcIpfsCid.title = bc.report_cid || "";
  } else {
    bcStored.textContent = "Not stored";
    bcStoredCard.classList.remove("bc-card--green");
    const errMsg = bc.error || "Blockchain unavailable.";
    bcStatus.innerHTML = `<span style="color:var(--amber)">⚠ ${errMsg}</span>`;
    [bcIndex, bcContract, bcTxHash, bcImageHash, bcReportHash, bcIpfsCid]
      .forEach(el => { el.textContent = "—"; el.title = ""; });
  }
}

// ─────────────────────────────────────────────────────────────────────────────

geocodeButton.addEventListener("click", async () => {
  geocodeButton.disabled = true;
  try {
    setStatus("Finding coordinates from Google Geocoding...");
    const result = await postJson("/api/geocode", { location: form.elements.location.value });
    applyCoordinates(result);
    setStatus("Coordinates filled. Preview satellite and nudge if needed.");
  } catch (error) {
    setStatus(error.message);
  } finally {
    geocodeButton.disabled = false;
  }
});

currentLocationButton.addEventListener("click", () => {
  if (!navigator.geolocation) {
    setStatus("Your browser does not support GPS location.");
    return;
  }

  setStatus("Waiting for browser location permission...");
  navigator.geolocation.getCurrentPosition(
    (position) => {
      form.elements.latitude.value = position.coords.latitude.toFixed(6);
      form.elements.longitude.value = position.coords.longitude.toFixed(6);
      setStatus("GPS coordinates filled. Preview satellite and nudge if needed.");
    },
    () => setStatus("Location permission was denied or unavailable."),
    { enableHighAccuracy: true, timeout: 12000 }
  );
});

previewSatelliteButton.addEventListener("click", async () => {
  previewSatelliteButton.disabled = true;
  try {
    await refreshSatellitePreview();
  } catch (error) {
    setStatus(error.message);
  } finally {
    previewSatelliteButton.disabled = false;
  }
});

document.querySelectorAll("[data-nudge]").forEach((button) => {
  button.addEventListener("click", async () => {
    if (!nudgeCoordinates(button.dataset.nudge)) return;
    button.disabled = true;
    try {
      await refreshSatellitePreview(`Moved ${button.dataset.nudge} by ${nudgeStep.value || 50} meters...`);
    } catch (error) {
      setStatus(error.message);
    } finally {
      button.disabled = false;
    }
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button[type='submit']");
  button.disabled = true;
  button.textContent = "Running model...";
  setStatus("Fetching satellite crop and running Fusion-2 cross-attention inference...");

  // Hide panels while running
  blockchainPanel.style.display = "none";
  if (chainlinkPanel) chainlinkPanel.style.display = "none";
  if (reportPanel) reportPanel.style.display = "none";

  try {
    const result = await postJson("/api/predict", formPayload());
    prediction.textContent = result.prediction;
    range.textContent = `Calibrated range: ${result.range}`;
    confidenceMeter.value = result.confidence;
    confidenceText.textContent = `${result.confidence}%`;
    modelStatus.textContent = result.model_status;
    applyCoordinates(result);
    setSatelliteImage(result.satellite_image);
    updateModelMetrics(result.model);
    setStatus("Prediction complete.");

    // ── Show Chainlink USD conversion ────────────────────────────────────
    if (result.chainlink !== undefined) {
      renderChainlink(result.chainlink);
    }
    // ── Show blockchain proof ─────────────────────────────────────────────
    if (result.blockchain !== undefined) {
      renderBlockchainProof(result.blockchain);
    }
    // ── Show valuation report ─────────────────────────────────────────────
    renderReport(result);
    // ── Refresh blockchain history ────────────────────────────────────────
    loadHistory();
    // ─────────────────────────────────────────────────────────────────────

  } catch (error) {
    prediction.textContent = "Could not predict";
    range.textContent = error.message;
    confidenceMeter.value = 0;
    confidenceText.textContent = "0%";
    setStatus(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Run Cross-Attention Estimate";
  }
});


/* ═══════════════════════════════════════════════════
   Valuation Report Panel
   ═══════════════════════════════════════════════════ */

const reportPanel = document.querySelector("#reportPanel");
const reportGrid = document.querySelector("#reportGrid");
let _lastReport = null;   // store full report for download

function shortStr(s, n = 16) {
  if (!s || s.length <= n) return s || "—";
  return s.slice(0, n) + "…";
}

function rcCard(label, value, cls = "") {
  return `
    <div class="report-card ${cls}">
      <span class="rc-label">${label}</span>
      <span class="rc-value ${cls.includes("highlight") ? "rc-price" : ""}">${value}</span>
    </div>`;
}

function rcHashCard(label, value) {
  return `
    <div class="report-card">
      <span class="rc-label">${label}</span>
      <span class="rc-value rc-hash" title="${value}">${value}</span>
    </div>`;
}

function sectionTitle(label) {
  return `<div class="report-section-title">${label}</div>`;
}

function renderReport(result) {
  if (!result) return;
  reportPanel.style.display = "block";
  _lastReport = result;

  const bc = result.blockchain || {};
  const cl = result.chainlink || {};
  const now = new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });

  // Format INR nicely
  let inrDisplay = result.prediction || "—";

  // USD conversion
  const usdPart = cl.available
    ? `<div class="report-card">
         <span class="rc-label">Equivalent (USD)</span>
         <span class="rc-value">${cl.usd_fmt || "—"}</span>
       </div>
       <div class="report-card">
         <span class="rc-label">Exchange Rate</span>
         <span class="rc-value">1 USD = ₹${cl.rate?.toFixed(2) || "—"}</span>
       </div>`
    : "";

  // Blockchain part
  const bcPart = bc.stored
    ? rcHashCard("Transaction Hash", bc.tx_hash || "—") +
    rcHashCard("Image SHA-256", bc.image_hash || "—") +
    rcHashCard("Report SHA-256", bc.report_hash || "—") +
    rcHashCard("IPFS CID", bc.report_cid || "NO_IPFS_CONFIGURED") +
    rcCard("Prediction #", bc.chain_index ?? "—") +
    rcCard("Contract", shortStr(bc.contract, 20))
    : `<div class="report-card" style="grid-column:1/-1">
         <span class="rc-label">Blockchain</span>
         <span class="rc-value" style="color:#c97c21">
           ${bc.error || "Not stored — Ganache may not be running"}
         </span>
       </div>`;

  reportGrid.innerHTML =
    sectionTitle("Valuation") +
    rcCard("Predicted Price", inrDisplay, "report-card--highlight") +
    rcCard("Calibrated Range", result.range || "—") +
    rcCard("Confidence", (result.confidence || "0") + "%") +
    rcCard("Generated At", now) +
    usdPart +

    sectionTitle("Property") +
    rcCard("Latitude", result.latitude || "—") +
    rcCard("Longitude", result.longitude || "—") +
    rcCard("Zoom Level", result.zoom || "—") +

    sectionTitle("Model") +
    rcCard("Architecture", "Fusion-2 Cross-Attention") +
    rcCard("R² Score", result.model?.r2 || "—") +
    rcCard("MAPE", result.model?.mape ? result.model.mape + "%" : "—") +
    rcCard("P50 Error", result.model?.p50_error ? result.model.p50_error + "%" : "—") +

    sectionTitle("Blockchain Proof") +
    bcPart;
}

function downloadReport(format) {
  if (!_lastReport) {
    alert("Run a valuation first.");
    return;
  }

  const bc = _lastReport.blockchain || {};
  const cl = _lastReport.chainlink || {};
  const now = new Date().toISOString();

  const report = {
    generated_at: now,
    valuation: {
      predicted_price: _lastReport.prediction,
      range: _lastReport.range,
      confidence_pct: _lastReport.confidence + "%",
    },
    usd_conversion: cl.available ? {
      usd: cl.usd_fmt,
      rate: `1 USD = ₹${cl.rate}`,
      source: cl.rate_source,
    } : null,
    property: {
      latitude: _lastReport.latitude,
      longitude: _lastReport.longitude,
      zoom: _lastReport.zoom,
    },
    model: {
      architecture: "Fusion-2 Cross-Attention",
      r2: _lastReport.model?.r2,
      mape: _lastReport.model?.mape,
    },
    blockchain_proof: bc.stored ? {
      tx_hash: bc.tx_hash,
      prediction_index: bc.chain_index,
      image_sha256: bc.image_hash,
      report_sha256: bc.report_hash,
      ipfs_cid: bc.report_cid,
      contract: bc.contract,
    } : { stored: false, error: bc.error },
  };

  if (format === "json") {
    const blob = new Blob([JSON.stringify(report, null, 2)],
      { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `valuation_report_${Date.now()}.json`;
    a.click();
  } else {
    // PDF — generate printable HTML and trigger browser print
    const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Valuation Report — PropChain</title>
<style>
  body { font-family: Georgia, serif; max-width: 700px; margin: 40px auto; color: #1a1a1a; }
  h1   { color: #047857; font-size: 24px; margin-bottom: 4px; }
  h2   { font-size: 15px; color: #333; border-bottom: 1px solid #ddd;
         padding-bottom: 5px; margin: 20px 0 10px; }
  .price { font-size: 32px; font-weight: 700; color: #047857; }
  .row   { display: flex; justify-content: space-between; padding: 6px 0;
           border-bottom: 1px solid #eee; font-size: 13px; }
  .row span:first-child { color: #666; }
  .hash  { font-family: monospace; font-size: 11px; color: #444;
           word-break: break-all; }
  .badge { background: #d1fae5; color: #047857; padding: 2px 10px;
           border-radius: 10px; font-size: 12px; font-weight: 600; }
  @media print { body { margin: 20px; } }
</style>
</head>
<body>
<h1>&#127968; PropChain — Valuation Report</h1>
<p style="color:#666;font-size:13px">Generated: ${now}</p>

<h2>Valuation</h2>
<div class="price">${report.valuation.predicted_price}</div>
<div class="row"><span>Range</span><span>${report.valuation.range}</span></div>
<div class="row"><span>Confidence</span><span>${report.valuation.confidence_pct}</span></div>
${report.usd_conversion ? `
<div class="row"><span>USD Equivalent</span><span>${report.usd_conversion.usd}</span></div>
<div class="row"><span>Exchange Rate</span><span>${report.usd_conversion.rate}</span></div>
<div class="row"><span>Rate Source</span><span>${report.usd_conversion.source}</span></div>
` : ""}

<h2>Property</h2>
<div class="row"><span>Latitude</span><span>${report.property.latitude}</span></div>
<div class="row"><span>Longitude</span><span>${report.property.longitude}</span></div>
<div class="row"><span>Zoom Level</span><span>${report.property.zoom}</span></div>

<h2>Model</h2>
<div class="row"><span>Architecture</span><span>${report.model.architecture}</span></div>
<div class="row"><span>R² Score</span><span>${report.model.r2 ?? "—"}</span></div>
<div class="row"><span>MAPE</span><span>${report.model.mape ?? "—"}%</span></div>

<h2>Blockchain Proof</h2>
${report.blockchain_proof.stored === false
        ? `<p style="color:#c97c21">${report.blockchain_proof.error || "Not stored"}</p>`
        : `
<div class="row"><span>Prediction #</span><span>${report.blockchain_proof.prediction_index}</span></div>
<div class="row"><span>Transaction Hash</span><span class="hash">${report.blockchain_proof.tx_hash}</span></div>
<div class="row"><span>Image SHA-256</span><span class="hash">${report.blockchain_proof.image_sha256}</span></div>
<div class="row"><span>Report SHA-256</span><span class="hash">${report.blockchain_proof.report_sha256}</span></div>
<div class="row"><span>IPFS CID</span><span class="hash">${report.blockchain_proof.ipfs_cid}</span></div>
<div class="row"><span>Contract</span><span class="hash">${report.blockchain_proof.contract}</span></div>
<p style="font-size:12px;color:#666;margin-top:16px;border-left:3px solid #047857;padding-left:10px">
  These hashes are stored permanently on the Ethereum blockchain.
  Anyone can verify this report is authentic by re-hashing it
  and comparing with the on-chain value.
</p>`}

</body>
</html>`;
    const win = window.open("", "_blank");
    win.document.write(html);
    win.document.close();
    win.print();
  }
}


/* ═══════════════════════════════════════════════════
   Blockchain History Panel
   ═══════════════════════════════════════════════════ */

const historyContent = document.querySelector("#historyContent");

function tsToStr(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });
}

async function verifyPrediction(index) {
  try {
    const result = await postJson("/api/blockchain-verify", { index });
    if (!result.success) throw new Error(result.error || "Verification failed");
    await loadHistory();
  } catch (error) {
    historyContent.innerHTML = `<div class="history-error">⚠ ${error.message}</div>`;
  }
}

async function loadHistory() {
  const btn = document.querySelector("#refreshHistoryBtn");
  if (btn) { btn.disabled = true; btn.textContent = "Loading…"; }
  historyContent.innerHTML = '<p class="history-empty">Fetching records from blockchain…</p>';

  try {
    const resp = await fetch("/api/blockchain-history");
    const data = await resp.json();

    if (!data.success) {
      historyContent.innerHTML = `
        <div class="history-error">
          ⚠ ${data.error || "Could not load history"}
          — make sure Ganache is running and deploy.py has been run.
        </div>`;
      return;
    }

    if (data.count === 0) {
      historyContent.innerHTML =
        '<p class="history-empty">No records on-chain yet. Run a valuation first.</p>';
      return;
    }

    const rows = data.predictions.map(p => `
      <tr>
        <td><strong>#${p.index}</strong></td>
        <td class="mono" title="${p.tx_hash || ''}">${shortStr(p.image_hash, 18)}</td>
        <td class="mono" title="${p.report_hash || ''}">${shortStr(p.report_hash, 18)}</td>
        <td class="mono">${shortStr(p.report_cid === "NO_IPFS_CONFIGURED" ? "—" : p.report_cid, 16)}</td>
        <td>${p.model_index}</td>
        <td class="mono" title="${p.requested_by}">${shortStr(p.requested_by, 14)}</td>
        <td>${tsToStr(p.timestamp)}</td>
        <td>
          <span class="badge ${p.verified ? "badge--green" : "badge--amber"}">
            ${p.verified ? "✓ Verified" : "Pending"}
          </span>
          ${p.verified ? "" : `<button class="small-button" onclick="verifyPrediction(${p.index})">Verify</button>`}
        </td>
      </tr>`).join("");

    historyContent.innerHTML = `
      <p class="history-count">${data.count} record${data.count !== 1 ? "s" : ""} stored on-chain</p>
      <div class="overflow-wrap">
        <table class="history-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Image Hash</th>
              <th>Report Hash</th>
              <th>IPFS CID</th>
              <th>Model</th>
              <th>Wallet</th>
              <th>Timestamp (IST)</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;

  } catch (e) {
    historyContent.innerHTML = `<div class="history-error">⚠ ${e.message}</div>`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "⟳ Refresh"; }
  }
}

// Auto-load history on page load
window.addEventListener("DOMContentLoaded", () => {
  loadHistory();
});
