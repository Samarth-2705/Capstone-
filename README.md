# PropChain Capstone: Satellite + Multimodal Property Valuation

This project predicts residential property prices by combining:

- Structured property inputs (BHK, baths, area, balcony)
- Text context (location + description)
- Satellite imagery from Google Static Maps

Predictions are produced by a trained Fusion-2 cross-attention PyTorch model. The web app can also optionally write prediction provenance to an Ethereum smart contract and add optional Chainlink-based currency context.

## Highlights

- Multimodal inference with cross-attention fusion
- Live satellite-image preview (zoom-aware, map center nudging)
- Geocoding support for typed locations
- Confidence/range output using saved calibration artifacts
- Optional on-chain provenance logging for each prediction

## Repository Layout

```text
capstone_final/
├── notebooks/
│   ├── Baseline.ipynb
│   ├── Fusion-2-cross-attention.ipynb
│   ├── Imageonly.ipynb
│   ├── new_data.ipynb
│   └── model_artifacts_cross_attention/
│       ├── fusion2_cross_attention_best_model.pth
│       ├── scaler.joblib
│       ├── tfidf.joblib
│       ├── kmeans.joblib
│       ├── confidence_calibration.joblib
│       └── final_metrics.joblib
├── web_app/
│   ├── server.py
│   ├── deploy.py
│   ├── DataProvenancePro.sol
│   ├── blockchain_utils.py
│   ├── chainlink_utils.py
│   └── static/
│       ├── index.html
│       ├── app.css
│       └── app.js
└── requirements.txt
```

## Tech Stack

- Python 3.11+
- PyTorch + torchvision
- scikit-learn, pandas, numpy, joblib
- Web3.py + py-solc-x (optional blockchain flow)
- Google Maps Static API + Geocoding API

## Quick Start

Run from the `capstone_final` folder.

1. Create and activate a virtual environment.

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Set environment variables.

Required for map fetch + geocoding:

```bash
export GOOGLE_MAPS_API_KEY="YOUR_API_KEY"
```

Optional blockchain RPC override:

```bash
export BLOCKCHAIN_RPC="http://127.0.0.1:7545"
```

Optional IPFS pinning via Pinata (only if you extend runtime wiring to pass this token into the blockchain client):

```bash
export PINATA_JWT="YOUR_PINATA_JWT"
```

4. Start the app.

```bash
python web_app/server.py
```

5. Open in browser.

```text
http://127.0.0.1:8000
```

## Model Artifacts Required at Runtime

The server expects these files in `notebooks/model_artifacts_cross_attention/`:

- `fusion2_cross_attention_best_model.pth`
- `scaler.joblib`
- `tfidf.joblib`
- `kmeans.joblib`
- `confidence_calibration.joblib`
- `final_metrics.joblib`

If any file is missing, startup or inference will fail.

## Web API Endpoints

- `GET /api/model-info`
	- Returns model test metrics and calibration info
- `POST /api/geocode`
	- Body: `{ "location": "..." }`
	- Returns latitude/longitude from Google Geocoding
- `POST /api/satellite-preview`
	- Body: coordinates or location + optional zoom
	- Fetches and returns a cached satellite preview path
- `POST /api/predict`
	- Runs end-to-end prediction (features + satellite + model)
	- Returns valuation, confidence/range, model summary, and optional blockchain proof payload
- `GET /api/blockchain-history`
	- Returns stored prediction records if blockchain is connected

## Optional Blockchain Setup (Ganache/Sepolia)

The ML pipeline works without blockchain. Blockchain integration is additive.

### Local Ganache

1. Start Ganache on `http://127.0.0.1:7545`.
2. Deploy the contract once:

```bash
cd web_app
python deploy.py
cd ..
```

This generates:

- `web_app/abi.json`
- `web_app/contract_address.txt`

Then run `python web_app/server.py` normally.

### Sepolia

```bash
cd web_app
python deploy.py --network sepolia --rpc "https://eth-sepolia.g.alchemy.com/v2/YOUR_KEY" --owner-key "0xYOUR_PRIVATE_KEY"
cd ..
```

Set `BLOCKCHAIN_RPC` to the same Sepolia RPC before launching the server.

## Notebook Workflow

Use notebooks under `notebooks/` for training/experiments. If you retrain the Fusion-2 model, overwrite artifacts in `notebooks/model_artifacts_cross_attention/` and restart the server.

## Troubleshooting

- `Google Maps API key missing`
	- Set `GOOGLE_MAPS_API_KEY` before starting the server.
- Satellite preview/prediction fails with HTTP errors
	- Ensure Maps Static API is enabled for your key.
- Geocoding fails
	- Ensure Geocoding API is enabled and billing/quota are valid.
- Contract files missing (`abi.json` / `contract_address.txt`)
	- Run `python web_app/deploy.py` once.
- PyTorch install mismatch
	- Install matching `torch`/`torchvision` wheels for your OS/Python version, then reinstall requirements.

## Notes

- Satellite cache images are generated at runtime in `web_app/satellite_cache/`.
- Keep satellite zoom near 19 for consistency with the current trained model behavior.

## License

Add your preferred license file (for example, MIT) and update this section accordingly.
