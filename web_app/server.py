from __future__ import annotations
import logging
from torchvision import models, transforms
import torch.nn as nn
import torch
from PIL import Image
import pandas as pd
import numpy as np
import joblib

import json
import math
import os
from dotenv import load_dotenv

import re
import sys
import time
import uuid
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import ssl
import certifi
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen
SSL_CONTEXT = ssl.create_default_context(
    cafile=certifi.where()
)


# ── Blockchain integration (additive — does not change ML logic) ──────────────
try:
    from blockchain_utils import BlockchainClient
    _BC_CLIENT: "BlockchainClient | None" = None
    _BC_ERROR = ""

    def _get_blockchain() -> "BlockchainClient | None":
        global _BC_CLIENT, _BC_ERROR
        if _BC_CLIENT is not None:
            return _BC_CLIENT
        try:
            rpc = os.environ.get("BLOCKCHAIN_RPC", "http://127.0.0.1:7545")
            pinata_jwt = os.environ.get("PINATA_JWT", "").strip() or None
            _BC_CLIENT = BlockchainClient(
                rpc_url=rpc,
                pinata_jwt=pinata_jwt,
            )
            logging.info("Blockchain connected: " +
                         _BC_CLIENT.contract.address)
            logging.info("Pinata IPFS: " +
                         ("configured" if pinata_jwt else "not configured"))
        except Exception as e:
            _BC_ERROR = str(e)
            logging.warning("Blockchain not available: " + str(e))
            _BC_CLIENT = None
        return _BC_CLIENT

except ImportError:
    def _get_blockchain():
        return None

# ── Chainlink integration ─────────────────────────────────────────────────────
try:
    from chainlink_utils import ChainlinkPriceFeed
    _CHAINLINK: "ChainlinkPriceFeed | None" = None

    def _get_chainlink() -> "ChainlinkPriceFeed | None":
        global _CHAINLINK
        if _CHAINLINK is not None:
            return _CHAINLINK
        bc = _get_blockchain()
        if bc:
            try:
                _CHAINLINK = ChainlinkPriceFeed(bc.w3)
            except Exception as e:
                logging.warning("Chainlink init failed: " + str(e))
        return _CHAINLINK

except ImportError:
    def _get_chainlink():
        return None

# ─────────────────────────────────────────────────────────────────────────────

warnings.filterwarnings(
    "ignore",
    message="enable_nested_tensor is True, but self.use_nested_tensor is False.*",
    category=UserWarning,
)


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
STATIC_DIR = ROOT / "static"
SATELLITE_DIR = ROOT / "satellite_cache"
ARTIFACT_DIR = PROJECT_ROOT / "notebooks" / "model_artifacts_cross_attention"

# Explicitly load the .env file from the project root.
ENV_FILE = PROJECT_ROOT / ".env"

if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE, override=True)
    print(f"[ENV] Loaded .env from: {ENV_FILE}")
else:
    print(f"[ENV] WARNING: .env not found at: {ENV_FILE}")

HOST = "127.0.0.1"
PORT = 8000

GOOGLE_MAPS_API_KEY = os.environ.get(
    "GOOGLE_MAPS_API_KEY",
    ""
).strip()

print(
    f"[ENV] GOOGLE_MAPS_API_KEY loaded: "
    f"{bool(GOOGLE_MAPS_API_KEY)}"
)

print(
    f"[ENV] PINATA_JWT loaded: "
    f"{bool(os.environ.get('PINATA_JWT', '').strip())}"
)


def rupees(value: float) -> str:
    if not math.isfinite(value):
        return "Unavailable"
    if value >= 10_000_000:
        return f"Rs. {value / 10_000_000:.2f} Cr"
    return f"Rs. {value / 100_000:.2f} L"


def parse_float(value: object, fallback: float) -> float:
    try:
        if value in {"", None}:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def require_google_key() -> str:
    if not GOOGLE_MAPS_API_KEY:
        raise RuntimeError(
            "Google Maps API key missing. Set GOOGLE_MAPS_API_KEY before starting the server.")
    return GOOGLE_MAPS_API_KEY


def geocode_location(location: str) -> tuple[float, float]:
    key = require_google_key()
    params = urlencode({"address": location, "key": key})
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"
    try:
        with urlopen(
            url,
            timeout=20,
            context=SSL_CONTEXT
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Google Geocoding HTTP {exc.code}: {detail[:240]}") from exc

    if payload.get("status") != "OK" or not payload.get("results"):
        raise RuntimeError(
            f"Google Geocoding failed: {payload.get('status', 'UNKNOWN')}")

    point = payload["results"][0]["geometry"]["location"]
    return float(point["lat"]), float(point["lng"])


def normalized_zoom(value: object) -> int:
    try:
        zoom = int(float(value))
    except (TypeError, ValueError):
        zoom = 19
    return max(17, min(21, zoom))


def fetch_google_satellite(lat: float, lng: float, zoom: int = 19) -> Path:
    key = require_google_key()
    SATELLITE_DIR.mkdir(exist_ok=True)
    file_path = SATELLITE_DIR / \
        f"satellite-{int(time.time())}-{uuid.uuid4().hex}.png"
    params = urlencode(
        {
            "center": f"{lat},{lng}",
            "zoom": str(normalized_zoom(zoom)),
            "size": "640x640",
            "scale": "2",
            "maptype": "satellite",
            "key": key,
        }
    )
    url = f"https://maps.googleapis.com/maps/api/staticmap?{params}"
    try:
        with urlopen(
            url,
            timeout=30,
            context=SSL_CONTEXT
        ) as response:
            data = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Google Static Maps HTTP {exc.code}: {detail[:240]}") from exc

    file_path.write_bytes(data)
    with Image.open(file_path) as img:
        img.verify()
    return file_path


class CrossAttentionBlock(nn.Module):
    def __init__(self, hidden_size: int, num_heads: int = 8, dropout: float = 0.25):
        super().__init__()
        self.query_norm = nn.LayerNorm(hidden_size)
        self.context_norm = nn.LayerNorm(hidden_size)
        self.attn = nn.MultiheadAttention(
            embed_dim=hidden_size,
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True,
        )
        self.dropout = nn.Dropout(dropout)
        self.ff_norm = nn.LayerNorm(hidden_size)
        self.ff = nn.Sequential(
            nn.Linear(hidden_size, hidden_size * 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size * 2, hidden_size),
        )

    def forward(self, query_token, context_tokens):
        context = self.context_norm(context_tokens)
        attn_out, _ = self.attn(self.query_norm(
            query_token), context, context, need_weights=False)
        token = query_token + self.dropout(attn_out)
        token = token + self.dropout(self.ff(self.ff_norm(token)))
        return token


class FusionModel(nn.Module):
    def __init__(self, tab_size: int, text_size: int, hidden_size: int = 256, dropout: float = 0.35, num_heads: int = 8):
        super().__init__()

        self.cnn = models.resnet18(weights=None)
        cnn_features = self.cnn.fc.in_features
        self.cnn.fc = nn.Identity()

        self.image_head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(cnn_features, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size, hidden_size),
            nn.LayerNorm(hidden_size),
        )

        self.tab_head = nn.Sequential(
            nn.Linear(tab_size, 128),
            nn.BatchNorm1d(128),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(128, hidden_size),
            nn.BatchNorm1d(hidden_size),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size, hidden_size),
            nn.LayerNorm(hidden_size),
        )

        self.text_head = nn.Sequential(
            nn.Linear(text_size, 192),
            nn.BatchNorm1d(192),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(192, hidden_size),
            nn.BatchNorm1d(hidden_size),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size, hidden_size),
            nn.LayerNorm(hidden_size),
        )

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_size,
            nhead=num_heads,
            dim_feedforward=hidden_size * 3,
            dropout=dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.self_attention = nn.TransformerEncoder(
            encoder_layer, num_layers=2)

        self.image_cross = CrossAttentionBlock(
            hidden_size, num_heads=num_heads, dropout=dropout)
        self.tab_cross = CrossAttentionBlock(
            hidden_size, num_heads=num_heads, dropout=dropout)
        self.text_cross = CrossAttentionBlock(
            hidden_size, num_heads=num_heads, dropout=dropout)

        self.gate = nn.Sequential(
            nn.Linear(hidden_size * 3, hidden_size),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size, 3),
            nn.Softmax(dim=1),
        )

        self.regressor = nn.Sequential(
            nn.Linear(hidden_size * 4, 512),
            nn.BatchNorm1d(512),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(512, 256),
            nn.LayerNorm(256),
            nn.GELU(),
            nn.Dropout(dropout / 2),
            nn.Linear(256, 64),
            nn.GELU(),
            nn.Linear(64, 1),
        )

    def forward(self, img, tab, text):
        img_token = self.image_head(self.cnn(img)).unsqueeze(1)
        tab_token = self.tab_head(tab).unsqueeze(1)
        text_token = self.text_head(text).unsqueeze(1)

        tokens = torch.cat([img_token, tab_token, text_token], dim=1)
        tokens = self.self_attention(tokens)

        img_token = self.image_cross(tokens[:, 0:1, :], tokens[:, 1:3, :])
        tab_token = self.tab_cross(tokens[:, 1:2, :], torch.cat(
            [tokens[:, 0:1, :], tokens[:, 2:3, :]], dim=1))
        text_token = self.text_cross(tokens[:, 2:3, :], tokens[:, 0:2, :])

        fused_tokens = torch.cat([img_token, tab_token, text_token], dim=1)
        flat_tokens = fused_tokens.flatten(start_dim=1)
        gate_weights = self.gate(flat_tokens).unsqueeze(-1)
        weighted_summary = (fused_tokens * gate_weights).sum(dim=1)
        final_features = torch.cat([flat_tokens, weighted_summary], dim=1)
        return self.regressor(final_features)


class CrossAttentionPricePredictor:
    def __init__(self) -> None:
        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu")
        checkpoint_path = ARTIFACT_DIR / "fusion2_cross_attention_best_model.pth"
        if not checkpoint_path.exists():
            raise FileNotFoundError(
                f"Model checkpoint not found: {checkpoint_path}")

        self.checkpoint = torch.load(checkpoint_path, map_location=self.device)
        self.features = list(self.checkpoint["features"])
        self.scaler = joblib.load(ARTIFACT_DIR / "scaler.joblib")
        self.tfidf = joblib.load(ARTIFACT_DIR / "tfidf.joblib")
        self.kmeans = joblib.load(ARTIFACT_DIR / "kmeans.joblib")
        self.calibration = joblib.load(
            ARTIFACT_DIR / "confidence_calibration.joblib")
        self.metrics = joblib.load(ARTIFACT_DIR / "final_metrics.joblib")

        self.model = FusionModel(
            tab_size=int(self.checkpoint["tab_size"]),
            text_size=int(self.checkpoint["text_size"]),
            hidden_size=int(self.checkpoint.get("hidden_size", 256)),
            dropout=float(self.checkpoint.get("dropout", 0.35)),
            num_heads=int(self.checkpoint.get("num_heads", 8)),
        ).to(self.device)
        self.model.load_state_dict(self.checkpoint["model_state_dict"])
        self.model.eval()

        self.image_transform = transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )

    def _build_feature_row(self, form: dict[str, object], lat: float, lng: float) -> dict[str, float]:
        bhk = parse_float(form.get("bhk"), 2.0)
        baths = parse_float(form.get("baths"), max(1.0, bhk))
        area = max(parse_float(form.get("area"), 1000.0), 100.0)
        balcony = 1.0 if str(form.get("balcony", "yes")
                             ).lower() == "yes" else 0.0
        coords = pd.DataFrame([[lat, lng]], columns=["latitude", "longitude"])
        location_cluster = int(self.kmeans.predict(coords)[0])

        row = {
            "BHK": bhk,
            "Baths": baths,
            "Balcony": balcony,
            "Total_Area": area,
            "latitude": lat,
            "longitude": lng,
            "bhk_density": bhk / (area + 1.0),
            "location_cluster": float(location_cluster),
            "bath_per_bhk": baths / (bhk + 1.0),
            "area_per_bhk": area / (bhk + 1.0),
        }
        return row

    def _build_text(self, form: dict[str, object], lat: float, lng: float) -> str:
        bhk = parse_float(form.get("bhk"), 2.0)
        baths = parse_float(form.get("baths"), max(1.0, bhk))
        area = parse_float(form.get("area"), 1000.0)
        balcony = str(form.get("balcony") or "Yes")
        location = str(form.get("location") or "")
        context = str(form.get("context") or "")
        return (
            f"{int(bhk)} BHK property with {int(baths)} baths, {int(area)} square feet, "
            f"balcony {balcony}, located near {location}. {context}. "
            f"Coordinates {lat:.6f}, {lng:.6f}."
        )

    def predict(self, form: dict[str, object], satellite_path: Path, lat: float, lng: float) -> dict[str, object]:
        feature_row = self._build_feature_row(form, lat, lng)
        tab_values = pd.DataFrame(
            [[feature_row[name] for name in self.features]], columns=self.features)
        tab_tensor = torch.tensor(self.scaler.transform(tab_values).astype(
            np.float32), dtype=torch.float32, device=self.device)

        text = self._build_text(form, lat, lng)
        text_values = self.tfidf.transform([text]).toarray().astype(np.float32)
        text_tensor = torch.tensor(
            text_values, dtype=torch.float32, device=self.device)

        with Image.open(satellite_path) as img:
            image_tensor = self.image_transform(
                img.convert("RGB")).unsqueeze(0).to(self.device)

        with torch.no_grad():
            predicted_log_price = float(self.model(
                image_tensor, tab_tensor, text_tensor).cpu().numpy().flatten()[0])

        predicted_price = max(float(np.expm1(predicted_log_price)), 0.0)
        p50 = float(self.calibration.get("p50_abs_pct_error", 26.0)) / 100.0
        p75 = float(self.calibration.get("p75_abs_pct_error", 47.0)) / 100.0
        p90 = float(self.calibration.get("p90_abs_pct_error", 75.0)) / 100.0
        low = predicted_price * max(0.0, 1.0 - p75)
        high = predicted_price * (1.0 + p75)
        confidence = round(max(35.0, min(86.0, 100.0 - (p50 * 100.0 * 1.25))))
        test_metrics = self.metrics.get("test", {})

        return {
            "prediction": rupees(predicted_price),
            "range": f"{rupees(low)} - {rupees(high)}",
            "confidence": confidence,
            "model_status": "Cross-attention Fusion-2 model active. Satellite image, property details, and text context were fused for prediction.",
            "satellite_image": f"/satellite/{satellite_path.name}",
            "model": {
                "name": "Fusion-2 Cross Attention",
                "r2": round(float(test_metrics.get("r2", 0.0)), 3),
                "mape": round(float(test_metrics.get("mape", 0.0)), 2),
                "p50_error": round(p50 * 100.0, 2),
                "p75_error": round(p75 * 100.0, 2),
                "p90_error": round(p90 * 100.0, 2),
            },
        }


PREDICTOR = CrossAttentionPricePredictor()


class AppHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict[str, object]) -> None:
        self._send(status, json.dumps(payload).encode(
            "utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._serve_file(STATIC_DIR / "index.html",
                             "text/html; charset=utf-8")
        elif path == "/static/app.css":
            self._serve_file(STATIC_DIR / "app.css", "text/css; charset=utf-8")
        elif path == "/static/app.js":
            self._serve_file(STATIC_DIR / "app.js",
                             "application/javascript; charset=utf-8")
        elif path.startswith("/satellite/"):
            image_path = SATELLITE_DIR / Path(path).name
            if image_path.exists() and image_path.suffix.lower() == ".png":
                self._serve_file(image_path, "image/png")
            else:
                self._json(404, {"error": "Satellite image not found"})
        elif path == "/api/model-info":
            self._json(200, {"model": PREDICTOR.metrics.get(
                "test", {}), "calibration": PREDICTOR.calibration})
        elif path == "/api/blockchain-history":
            self._handle_blockchain_history()
        else:
            self._json(404, {"error": "Route not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/geocode":
            self._handle_geocode()
        elif parsed.path == "/api/satellite-preview":
            self._handle_satellite_preview()
        elif parsed.path == "/api/predict":
            self._handle_predict()
        elif parsed.path == "/api/blockchain-verify":
            self._handle_blockchain_verify()
        else:
            self._json(404, {"error": "Route not found"})

    def _read_json(self) -> dict[str, object]:
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length).decode("utf-8")
        return json.loads(body or "{}")

    def _resolve_coordinates(self, payload: dict[str, object]) -> tuple[float, float]:
        lat_value = payload.get("latitude")
        lng_value = payload.get("longitude")

        if lat_value in {"", None} or lng_value in {"", None}:
            location = str(payload.get("location") or "").strip()
            if not location:
                raise RuntimeError(
                    "Enter a location or click the location icon first.")
            lat, lng = geocode_location(location)
            payload["latitude"] = lat
            payload["longitude"] = lng
            return lat, lng

        return float(lat_value), float(lng_value)

    def _handle_blockchain_history(self) -> None:
        """Return all prediction records from the blockchain."""
        bc = _get_blockchain()
        if not bc:
            self._json(
                503, {"success": False, "error": "Blockchain not connected"})
            return
        try:
            n = bc.contract.functions.getPredictionCount().call()
            preds = []
            for i in range(n):
                p = bc.get_prediction(i)
                preds.append({
                    "index": p.index,
                    "image_hash": p.input_hash,
                    "report_hash": p.output_hash,
                    "report_cid": p.result_cid,
                    "model_index": p.model_version_index,
                    "dataset_idx": p.dataset_index,
                    "requested_by": p.requested_by,
                    "timestamp": p.timestamp,
                    "verified": p.verified,
                })
            self._json(
                200, {"success": True, "count": n, "predictions": preds})
        except Exception as e:
            self._json(500, {"success": False, "error": str(e)})

    def _handle_blockchain_verify(self) -> None:
        """Mark one prediction as verified on-chain."""
        bc = _get_blockchain()
        if not bc:
            self._json(
                503, {"success": False, "error": "Blockchain not connected"})
            return
        try:
            payload = self._read_json()
            index = int(payload.get("index"))
            tx_hash = bc.verify_prediction(index)
            self._json(200, {
                "success": True,
                "index": index,
                "tx_hash": tx_hash,
            })
        except (TypeError, ValueError):
            self._json(400, {
                "success": False,
                "error": "A valid prediction index is required",
            })
        except Exception as exc:
            self._json(500, {"success": False, "error": str(exc)})

    def _handle_geocode(self) -> None:
        try:
            payload = self._read_json()
            location = str(payload.get("location") or "").strip()
            if not location:
                raise RuntimeError("Enter a location before geocoding.")
            lat, lng = geocode_location(location)
            self._json(200, {"latitude": lat, "longitude": lng})
        except Exception as exc:
            self._json(400, {"error": str(exc)})

    def _handle_satellite_preview(self) -> None:
        try:
            payload = self._read_json()
            lat, lng = self._resolve_coordinates(payload)
            zoom = normalized_zoom(payload.get("zoom"))
            satellite_path = fetch_google_satellite(lat, lng, zoom)
            self._json(
                200,
                {
                    "satellite_image": f"/satellite/{satellite_path.name}",
                    "latitude": lat,
                    "longitude": lng,
                    "zoom": zoom,
                },
            )
        except Exception as exc:
            self._json(400, {"error": str(exc)})

    def _handle_predict(self) -> None:
        try:
            payload = self._read_json()
            lat, lng = self._resolve_coordinates(payload)
            zoom = normalized_zoom(payload.get("zoom"))
            satellite_path = fetch_google_satellite(lat, lng, zoom)
            result = PREDICTOR.predict(payload, satellite_path, lat, lng)
            result["latitude"] = lat
            result["longitude"] = lng
            result["zoom"] = zoom

            # ── Blockchain proof (additive — does not affect ML result) ───────
            result["blockchain"] = {"stored": False, "error": ""}
            try:
                import hashlib
                import json as _json
                import datetime as _dt
                import time as _time

                bc = _get_blockchain()
                if bc:
                    # ── Step 1: Auto-register dataset if none exist ───────────
                    n_datasets = bc.contract.functions.getDatasetCount().call()
                    if n_datasets == 0:
                        _ds_hash = hashlib.sha256(
                            b"PropertyDataset-v1").hexdigest()
                        bc.store_dataset(
                            data_hash=_ds_hash,
                            ipfs_cid="NO_IPFS_CONFIGURED",
                            prev=9999,
                            label="PropertyDataset-v1",
                        )
                        n_datasets = 1

                    # ── Step 2: Auto-register model if none exist ─────────────
                    n_models = bc.contract.functions.getModelVersionCount().call()
                    if n_models == 0:
                        _model_path = ARTIFACT_DIR / "fusion2_cross_attention_best_model.pth"
                        if _model_path.exists():
                            _mh = bc.hash_bytes(_model_path.read_bytes())
                        else:
                            _mh = hashlib.sha256(
                                b"FusionModel-CrossAttention-v1").hexdigest()
                        bc.store_model_version(
                            model_hash=_mh,
                            ipfs_cid="NO_IPFS_CONFIGURED",
                            algorithm_tag="FusionModel-CrossAttention-v1",
                            trained_on_dataset=0,
                        )
                        n_models = 1

                    # ── Step 3: Hash the satellite image ──────────────────────
                    with open(satellite_path, "rb") as _f:
                        img_bytes = _f.read()
                    image_hash = hashlib.sha256(img_bytes).hexdigest()

                    # ── Step 4: Build valuation report ────────────────────────
                    report = {
                        "generated_at": _dt.datetime.utcnow().isoformat() + "Z",
                        "property": {"latitude": lat, "longitude": lng, "zoom": zoom},
                        "valuation": {
                            "prediction": result["prediction"],
                            "range": result["range"],
                            "confidence": result["confidence"],
                        },
                        "model": result.get("model", {}),
                        "image_sha256": image_hash,
                    }
                    report_json = _json.dumps(
                        report, sort_keys=True, separators=(",", ":"))
                    report_hash = hashlib.sha256(
                        report_json.encode()).hexdigest()

                    # ── Step 5: Pin report to IPFS (if Pinata configured) ─────
                    report_cid = bc.pin_json_to_ipfs(
                        report, name="valuation_report")
                    if report_cid == "NO_IPFS_CONFIGURED":
                        print(
                            "[IPFS] Pinata is not configured; report was not pinned.")
                    else:
                        report_url = f"https://gateway.pinata.cloud/ipfs/{report_cid}"
                        print(f"[IPFS] Report CID: {report_cid}")
                        print(f"[IPFS] Report URL: {report_url}")

                    # ── Step 6: Store prediction on-chain ─────────────────────
                    bc_result = bc.store_prediction(
                        input_hash=image_hash,
                        output_hash=report_hash,
                        result_cid=report_cid,
                        model_version_index=n_models - 1,
                        dataset_index=n_datasets - 1,
                    )
                    result["blockchain"] = {
                        "stored": True,
                        "tx_hash": bc_result["tx"],
                        "chain_index": bc_result["index"],
                        "image_hash": image_hash,
                        "report_hash": report_hash,
                        "report_cid": report_cid,
                        "contract": bc.contract.address,
                        "error": "",
                    }
                else:
                    result["blockchain"]["error"] = _BC_ERROR or "Blockchain not connected — run: ganache --port 7545"
            except Exception as _bc_exc:
                import traceback as _tb
                result["blockchain"]["error"] = str(_bc_exc)
                print("[BLOCKCHAIN ERROR]", _tb.format_exc())
            # ─────────────────────────────────────────────────────────────────

            self._json(200, result)
        except Exception as exc:
            self._json(400, {"error": str(exc)})

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self._json(404, {"error": "File not found"})
            return
        with path.open("rb") as handle:
            self._send(200, handle.read(), content_type)


def main() -> None:
    print(f"Property AI demo running at http://{HOST}:{PORT}")
    print("Cross-attention Fusion-2 model loaded from:", ARTIFACT_DIR)
    print("Press Ctrl+C to stop the server.")
    ThreadingHTTPServer((HOST, PORT), AppHandler).serve_forever()


if __name__ == "__main__":
    main()
