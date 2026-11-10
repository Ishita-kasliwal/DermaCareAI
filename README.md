# DermaCareAI: AI-Based Skin Disease Detection and Classification System

> ⚠️ Educational / screening aid only. Not a medical device and not a diagnosis. Always consult a dermatologist.

Upload a dermoscopic skin-lesion image. A TensorFlow/Keras model (MobileNetV2 or EfficientNetB0
transfer learning on HAM10000) scores it against 7 lesion categories, shows the alternatives, explains
itself with Grad-CAM, and reports **"inconclusive"** when it isn't sure. Results are stored in MySQL,
with per-user history, Chart.js analytics, Power BI-ready CSV exports, and light and dark themes.

Docs: [Architecture](docs/ARCHITECTURE.md) · [Datasets & licensing](docs/DATASETS.md) ·
[ML training](docs/ML_TRAINING.md) · [Testing report](docs/TESTING_REPORT.md)

## Stack
Flask 3 · Jinja2 · custom CSS (light/dark) · Chart.js 4.4.7 (vendored) · Waitress · TensorFlow/Keras (CPU) ·
OpenCV · Pillow · Pandas · NumPy · scikit-learn · SQLAlchemy + Alembic · MySQL 8 · Python 3.12

## First-time setup (everything project-local)
```powershell
.\scripts\setup_venv.ps1              # .venv with Python 3.12 + dependencies
.\scripts\db_setup.ps1                # creates skin_ai_db + 2 least-privilege users (asks for YOUR MySQL root password)
.\scripts\db_upgrade.ps1              # applies migrations, seeds the 7 categories
.\.venv\Scripts\flask.exe --app wsgi create-admin   # prompts for the admin password
```

## Train and install a model
```powershell
.\scripts\download_ham10000.ps1       # ~2.8 GB, CC BY-NC 4.0, MD5-verified
.\.venv\Scripts\python.exe -m ml.src.run_pipeline
$v = Get-Content ml\artifacts\models\LATEST
.\.venv\Scripts\flask.exe --app wsgi register-model "ml\artifacts\models\$v" --activate
```

## Run commands
| Action  | Command                    |
|---------|----------------------------|
| START   | `.\scripts\start.ps1`      |
| STOP    | `.\scripts\stop.ps1`       |
| STATUS  | `.\scripts\status.ps1`     |
| RESTART | `.\scripts\restart.ps1`    |

App: http://127.0.0.1:8010 · logs: `run/app.err.log`. The scripts act only on the PID in `run/app.pid`,
after verifying that it is this project's `.venv` interpreter with a matching start time.

## Styling (Tailwind CSS)
The UI is styled with **Tailwind CSS 3.4** (class-based dark mode, follows the OS until you pick a theme).
The compiled file `app/static/css/app.css` is committed, so Node is only needed when you change styles:
```powershell
npm install                 # once
npm run build:css           # rebuild app/static/css/app.css from app/static/src/tailwind.css
npm run watch:css           # rebuild automatically while editing
```

## Tests
```powershell
.\.venv\Scripts\python.exe -m pytest                 # full suite (~1.5 min)
.\.venv\Scripts\python.exe -m pytest -m "not slow"   # skip the end-to-end ML pipeline test
```

## Data & licence
HAM10000 © ViDIR Group, Department of Dermatology, Medical University of Vienna, CC BY-NC 4.0
(non-commercial). The dataset and trained weights are never committed.
