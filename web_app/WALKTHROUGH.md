# Property Price AI Website Walkthrough

## Intended User Flow

1. User enters BHK, baths, total area, balcony, and the property location.
2. User can click the current-location icon to fill latitude and longitude from the browser.
3. User can also click the geocode icon to convert the typed location into latitude and longitude using Google Geocoding.
4. The backend calls Google Static Maps with `maptype=satellite`.
5. The fetched satellite image is shown in the website at zoom `19`, matching the current Fusion-2 training setup.
6. If the house is not centered, the user nudges the latitude/longitude north, south, east, or west by a selected meter step.
7. The app runs the trained cross-attention Fusion-2 model and returns price, calibrated range, confidence, and model metrics.

## Google Cloud Setup

Enable these APIs in Google Cloud:

- Maps Static API
- Geocoding API, only if you want typed addresses converted to coordinates

Create an API key, then start the server with the key:

```cmd
cd C:\Users\mrvin\anaconda3\Capstone
set GOOGLE_MAPS_API_KEY=YOUR_API_KEY_HERE
C:\Users\mrvin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe web_app\server.py
```

Then open:

```text
http://127.0.0.1:8000
```

## Current Implementation

- `web_app/server.py` fetches Google satellite imagery and runs the trained cross-attention model from `notebooks/model_artifacts_cross_attention`.
- `web_app/static/index.html` contains the property-detail form.
- `web_app/static/app.js` handles current location, geocoding, satellite preview, meter-based nudging, and prediction.
- `web_app/static/app.css` styles the interface.

Keep `Satellite zoom` at `19` while using the model trained on zoom-19 images. If geocoding is off by a few hundred meters, use `Preview satellite only`, then nudge the center by 50-100 meters until the target house is under the crosshair.

The old comparable-record demo predictor has been replaced. The live prediction path now uses:

- `fusion2_cross_attention_best_model.pth`
- `scaler.joblib`
- `tfidf.joblib`
- `kmeans.joblib`
- `confidence_calibration.joblib`

## Later Fusion-2 Integration

If you retrain the notebook later, rerun it until the `model_artifacts_cross_attention` folder is updated, then restart the web server. The frontend does not need to change as long as the saved checkpoint keeps the same architecture metadata.
