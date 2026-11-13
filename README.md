# DermaCareAI: AI-Based Skin Disease Detection and Classification System

> ⚠️ Educational / screening aid only. Not a medical device and not a diagnosis. Always consult a doctor or dermatologist.

Upload a photo of your skin and choose what you're checking. DermaCareAI has **two AI checkers**:

| Checker | Learned from | Conditions | Test balanced accuracy |
|---|---|---|---|
| **Mole or spot** | HAM10000 (10,015 dermoscopic photos) | 7: melanoma, basal cell carcinoma, sun-damage patch, age spot, firm bump, common mole, blood-vessel spot | 55.4% |
| **Rash or other skin problem** *(early version)* | SCIN, Google Research (3,168 phone photos) | 10: eczema, contact dermatitis, hives, insect bite, folliculitis, fungal infection, acne/rosacea, psoriasis, shingles, cold sores | 26.2% |

Each result shows every score, alternatives, a Grad-CAM heatmap and plain-English advice, and says **"not sure"**
when the AI isn't confident. Results are stored in MySQL with private per-user history, Chart.js analytics,
Power BI-ready CSV exports, and light and dark themes. Full numbers and limits: [Testing report](docs/TESTING_REPORT.md).

Docs: [Architecture](docs/ARCHITECTURE.md) · [Datasets & licensing](docs/DATASETS.md) ·
[ML training](docs/ML_TRAINING.md) · [Testing report](docs/TESTING_REPORT.md)

## Stack
Flask 3 · Jinja2 · Tailwind CSS 3.4 · Chart.js 4.4.7 (vendored) · Waitress · TensorFlow/Keras · OpenCV · Pillow ·
Pandas · NumPy · scikit-learn · SQLAlchemy + Alembic · MySQL 8 · Python 3.12

## First-time setup (everything project-local)
```powershell
.\scripts\setup_venv.ps1              # .venv with Python 3.12 + dependencies
.\scripts\db_setup.ps1                # creates skin_ai_db + 2 least-privilege users (asks for YOUR MySQL root password)
.\scripts\db_upgrade.ps1              # applies migrations, seeds all 17 conditions
.\.venv\Scripts\flask.exe --app wsgi create-admin   # prompts for the admin password
```

## Train and install the models
```powershell
# Mole or spot checker (HAM10000, ~2.8 GB)
.\scripts\download_ham10000.ps1
.\.venv\Scripts\python.exe -m ml.src.run_pipeline --config ml/configs/train.yaml
.\.venv\Scripts\flask.exe --app wsgi register-model "ml\artifacts\models\$(Get-Content ml\artifacts\models\LATEST)" --activate

# Rash or other skin problem checker (SCIN, ~3.9 GB of selected photos)
.\.venv\Scripts\python.exe -m ml.src.scin_prepare
.\.venv\Scripts\python.exe -m ml.src.run_pipeline --config ml/configs/train_scin.yaml
.\.venv\Scripts\flask.exe --app wsgi register-model "ml\artifacts\scin\models\$(Get-Content ml\artifacts\scin\models\LATEST)" --activate
```
Faster, more accurate training on a free GPU: see [docs/ML_TRAINING.md](docs/ML_TRAINING.md#train-on-a-free-gpu-google-colab).

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

Datasets and trained weights are never committed. Because of the HAM10000 licence, this project is non-commercial.
