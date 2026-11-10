# ML training guide

Read [DATASETS.md](DATASETS.md) first for licensing and limitations.

## 1. Get the data (once)

```powershell
.\scripts\download_ham10000.ps1     # ~2.8 GB from Harvard Dataverse, MD5-verified
```

## 2. Run the pipeline

```powershell
.\.venv\Scripts\python.exe -m ml.src.eda                 # stats + plots -> ml/artifacts/reports/eda/
.\.venv\Scripts\python.exe -m ml.src.dataset             # grouped split -> ml/artifacts/splits/
.\.venv\Scripts\python.exe -m ml.src.run_pipeline        # train both models, evaluate, select, export
.\.venv\Scripts\python.exe -m ml.src.run_pipeline --models efficientnetb0   # just one model
```

Each step reads `ml/configs/train.yaml`. Use `--override my.yaml` to change values without
editing the main config.

## 3. Use the model

```powershell
$v = Get-Content ml\artifacts\models\LATEST
.\.venv\Scripts\python.exe -m skinai_ml.prediction --model-dir "ml\artifacts\models\$v" some_lesion.jpg
```

## What the pipeline does and why

| Step | Implementation | Reason |
|---|---|---|
| Inspect | `dataset.load_metadata` checks the columns, that every image file exists, and that the class codes are known | Fail loudly. Never train on partial or invented data |
| EDA | `eda.py`: class counts and %, imbalance ratio, images per lesion, `dx_type`, age/sex/site, image sizes, sample grid | Every number is computed from your copy of the data |
| Preprocess | `skinai_ml/preprocess.py`: center-square crop, then a 224 px antialiased bilinear resize, uint8 RGB | The same TF ops are used for training and inference, so there's no train/serve skew |
| Normalize | Inside the model: MobileNetV2 maps to [-1, 1]; EfficientNetB0 has its own normalization layers | The saved model works with the documented 0–255 input, whatever the architecture |
| Augment | Train split only: flips, ±180° rotation, ±15% zoom, contrast and brightness | Dermoscopy images have no canonical orientation, and lighting varies between devices |
| Split | `StratifiedGroupKFold` grouped by `lesion_id`, 70/15/15, seed 42, saved to CSV and reused | No lesion appears in two splits, and every model sees identical splits |
| Imbalance | Class weights = inverse frequency^0.5 (configurable) | Full inverse weights (around 60:1 on HAM10000) destabilize training; the square root is a common compromise |
| Models | MobileNetV2 and EfficientNetB0, ImageNet weights. Stage 1 trains the head; stage 2 fine-tunes the top layers with BatchNorm frozen | Light CPU-friendly backbones; two-stage training avoids destroying the pretrained features |
| Select | Best checkpoint by **validation macro-F1**; across models, tie-break on melanoma sensitivity | Accuracy is misleading at a 67% majority class. The test set is never used to choose |
| Evaluate | Precision, recall/sensitivity, specificity, F1 and one-vs-rest AUC per class; confusion matrix; balanced accuracy; malignant-vs-benign sensitivity/specificity; coverage vs threshold | Everything the requirements list, plus the numbers needed to pick the "Inconclusive" threshold |
| Export | `ml/artifacts/models/<version>/`: `model.keras`, `labels.json`, `preprocess_config.json`, `metrics.json`, `manifest.json` (SHA-256, config, environment, split fingerprint), `MODEL_CARD.md` | Reproducible and self-describing. The predictor refuses a model whose checksum doesn't match |

**Reproducibility:** fixed seeds (Python, NumPy, TF), TF op determinism, a persisted split CSV with
a fingerprint, the full config and its hash, library versions and the git commit, all recorded in `manifest.json`.

## Training time on this laptop (CPU only)

There's no NVIDIA GPU here, so training runs on the i5-1335U CPU. Expect several hours for both models
with the default epoch counts. Options:

- Train one model at a time with `--models efficientnetb0`.
- Run the same code on Google Colab or Kaggle with a free GPU. Clone the repo there, put HAM10000 under
  `ml/data/raw/HAM10000`, `pip install -r requirements.txt`, then run `python -m ml.src.run_pipeline`.
  Copy `ml/artifacts/models/<version>/` back afterwards.

## Interpreting results

Reported numbers are **retrospective agreement with HAM10000 labels on held-out lesions**.
They are not clinical diagnostic accuracy, and they don't carry over to smartphone photos or other populations.
