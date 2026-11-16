# DermaCareAI: AI-Based Skin Disease Detection and Classification System

> ⚠️ Educational / screening aid only. Not a medical device and not a diagnosis. Always consult a doctor or dermatologist.

Upload a photo of your skin and choose what you're checking. DermaCareAI has **two AI checkers**:

| Checker | Learned from | Conditions | Test balanced accuracy |
|---|---|---|---|
| **Mole or spot** | HAM10000 (10,015 dermoscopic photos) | 7: melanoma, basal cell carcinoma, sun-damage patch, age spot, firm bump, common mole, blood-vessel spot | 55.4% |
| **Rash or other skin problem** | Supplied rash/acne photos + SCIN subset + 2 Roboflow Universe sets (2,421 photos), CLIP image features | 8: acne, skin irritation, eczema, ringworm, dark spots, redness, scratches & cuts, healthy skin, plus "not a skin problem" | 84% (74% on the supplied photos; 89% when ≥60% sure), 5-fold grouped cross-validation |

Each result shows every score, alternatives, a Grad-CAM heatmap and plain-English advice, and says **"not sure"**
when the AI isn't confident. Results are stored in MySQL with private per-user history, Chart.js analytics,
Excel and Power BI-ready CSV downloads, optional "Continue with Google" sign-in, a face-photo warning for the
mole checker, and light and dark themes. Full numbers and limits: [Testing report](docs/TESTING_REPORT.md).

Docs: [Architecture](docs/ARCHITECTURE.md) · [Datasets & licensing](docs/DATASETS.md) ·
[ML training](docs/ML_TRAINING.md) · [Testing report](docs/TESTING_REPORT.md) · [Google sign-in](docs/GOOGLE_SIGNIN.md)

## Stack
Flask 3 · Jinja2 · Tailwind CSS 3.4 · Chart.js 4.4.7 (vendored) · Waitress · TensorFlow/Keras · OpenCV · Pillow ·
Pandas · NumPy · scikit-learn · SQLAlchemy + Alembic · MySQL 8 · Python 3.12

## First-time setup (everything project-local)
```powershell
.\scripts\setup_venv.ps1              # .venv with Python 3.12 + dependencies
.\scripts\db_setup.ps1                # creates skin_ai_db + 2 least-privilege users (asks for YOUR MySQL root password)
.\scripts\db_upgrade.ps1              # applies migrations, seeds all 20 answers
.\.venv\Scripts\flask.exe --app wsgi create-admin   # prompts for the admin password
```

## Train and install the models
```powershell
# Mole or spot checker (HAM10000, ~2.8 GB)
.\scripts\download_ham10000.ps1
.\.venv\Scripts\python.exe -m ml.src.run_pipeline --config ml/configs/train.yaml
.\.venv\Scripts\flask.exe --app wsgi register-model "ml\artifacts\models\$(Get-Content ml\artifacts\models\LATEST)" --activate

# Rash or other skin problem checker (the supplied rash photo zips in Downloads)
.\.venv\Scripts\python.exe -m ml.src.face_prepare
.\.venv\Scripts\python.exe -m ml.src.rash_clip_train          # CLIP features, 5-fold estimate + export
.\.venv\Scripts\flask.exe --app wsgi register-model "ml\artifacts\face\models\$(Get-Content ml\artifacts\face\models\LATEST)" --activate
# Older option with more conditions but much weaker results (SCIN, 10 conditions, 26% balanced accuracy):
# ml.src.scin_prepare + ml/configs/train_scin.yaml
```
Faster, more accurate training on a free GPU: see [docs/ML_TRAINING.md](docs/ML_TRAINING.md#train-on-a-free-gpu-google-colab).

## Try the model on your own photos
```powershell
.\.venv\Scripts\python.exe scripts\check_photos.py my_photo1.jpg my_photo2.png
```

## Edit the home-care tips and medicines
The safe home-care tips and over-the-counter medicines on the result page live in [`app/data/care.json`](app/data/care.json), one entry per
condition (3–5 short tips each). Skin cancer and pre-cancer (`mel`, `bcc`, `akiec`) are marked `"urgent": true`:
they never get home remedies or medicines, only a "see a dermatologist as soon as possible" message.
Medicines: generic names only, no strengths or doses, nothing prescription-only (the tests check a list of
prescription medicines), and the safety note is always shown with them. Edits show on the next page
load. Run `.\.venv\Scripts\python.exe -m pytest tests/unit/test_care.py` afterwards to check the rules.

## Run commands
| Action  | Command                    |
|---------|----------------------------|
| START   | `.\scripts\start.ps1`      |
| STOP    | `.\scripts\stop.ps1`       |
| STATUS  | `.\scripts\status.ps1`     |
| RESTART | `.\scripts\restart.ps1`    |

**Temporary public link** (Cloudflare quick tunnel, works while this laptop is on): `.\scripts\public_start.ps1`,
`.\scripts\public_status.ps1`, `.\scripts\public_stop.ps1`. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

App: http://127.0.0.1:8010 · logs: `run/app.err.log`. The scripts act only on the PID in `run/app.pid`,
after verifying that it is this project's `.venv` interpreter with a matching start time.

## Styling (Tailwind CSS)
`app/static/css/app.css` is built by Tailwind and committed, so Node is only needed when you change styles:
```powershell
npm install                 # once
npm run build:css           # rebuild from app/static/src/tailwind.css
npm run watch:css           # rebuild automatically while editing
```

## Tests
```powershell
.\.venv\Scripts\python.exe -m pytest                 # full suite
.\.venv\Scripts\python.exe -m pytest -m "not slow"   # skip the end-to-end ML pipeline test
```

## Data & licences
- HAM10000 © ViDIR Group, Department of Dermatology, Medical University of Vienna, CC BY-NC 4.0 (non-commercial).
- SCIN dataset, Google Research & Stanford Medicine, SCIN Data Use License (re-identifying contributors is prohibited).
- Roboflow Universe: "Skin analysis" (image-classification-q4nkn) and "basic-wound-classify" (clinicvision), CC BY 4.0.
  Some acne photos in "Skin analysis" originate from DermNet (dermnetnz.org). Download with `python -m ml.src.roboflow_download`
  (needs your own free `ROBOFLOW_API_KEY` in `.env`).

Datasets and trained weights are never committed. Because of the HAM10000 licence, this project is non-commercial.
