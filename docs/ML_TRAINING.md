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

**Reproducibility:** fixed seeds (Python, NumPy, TF), a persisted split CSV with a fingerprint, the full
config and its hash, library versions and the git commit, all recorded in `manifest.json`.
TF op determinism (`deterministic: true` in the config) gives bit-exact reruns, but on this CPU it made
augmentation about 11× slower (0.33 vs 0.03 s per batch, measured with `python -m ml.src.profile_pipeline`).
It is therefore **off** by default, so reruns can differ by small floating-point amounts.

## Training time on this laptop (CPU only)

There's no NVIDIA GPU here, so training runs on the i5-1335U CPU: about 2.5 min per round for MobileNetV2 and
4–6 min for EfficientNetB0 at 224 px. If training is interrupted, finish from the saved best checkpoints instead of
starting over:

```powershell
.\.venv\Scripts\python.exe -m ml.src.finalize_runs --config ml/configs/train.yaml --runs ml/artifacts/runs/<run1> ml/artifacts/runs/<run2>
```

## Train on a free GPU (Google Colab)

The GPU configs aim mainly at **catching more melanomas**:

| | CPU config (`train.yaml`) | GPU config (`train_gpu.yaml`) |
|---|---|---|
| Photo size | 224 px | **300 px** |
| Models | MobileNetV2, EfficientNetB0 | **EfficientNetB3**, EfficientNetB0 |
| Training rounds | up to 30 | up to 52 |
| Extra weight | none | **melanoma ×2**, BCC and sun-damage patch ×1.3 |
| Test-time augmentation | none | original + horizontal + vertical flip, averaged (also used by the website) |
| Mixed precision | no | yes (about 2× faster on GPU) |

The rash checker has its own `train_scin_gpu.yaml`. Steps:

1. Commit your work, then run `.\scripts\make_colab_bundle.ps1`. This creates `run\dermacare_colab_bundle.zip`,
   which holds code only, with no data, models or `.env`.
2. Open `notebooks/train_on_colab.ipynb` in Google Colab (File → Upload notebook) and choose a **T4 GPU** runtime.
3. Run the cells. The notebook uploads the bundle, installs the same TensorFlow/Keras versions as your laptop,
   downloads the data from the official sources, trains, shows the test results and downloads the model.
4. Unzip the model into `ml\artifacts\models\` (mole) or `ml\artifacts\scin\models\` (rash), then:
   `.\.venv\Scripts\flask.exe --app wsgi register-model <folder> --activate` and `.\scripts\restart.ps1`.

The split uses the same seed and grouping, so the new model is tested on exactly the same held-out photos as the
current one, and the results are directly comparable.

## Interpreting results

Reported numbers are **retrospective agreement with HAM10000 labels on held-out lesions**.
They are not clinical diagnostic accuracy, and they don't carry over to smartphone photos or other populations.
