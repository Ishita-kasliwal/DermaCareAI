# Datasets: licensing, categories, sources, limitations, intended use

Last verified: 2026-11-10, against the official Harvard Dataverse record and the ISIC challenge data page
(links below). No dataset files are stored in this repository.

## Summary

| Dataset | Images | Classes | Grouping IDs | License | Used here |
|---|---|---|---|---|---|
| **HAM10000** (= ISIC 2018 Task 3 training set) | 10,015 dermoscopic | 7 | `lesion_id` (no patient ID) | CC BY-NC 4.0 | ✅ primary |
| ISIC 2019 training | 25,331 dermoscopic | 8 (adds SCC); test set adds an "unknown" class | lesion identifier | CC BY-NC 4.0 | Planned extension |
| ISIC 2020 (SIIM-ISIC) | 33,126 dermoscopic | Binary (melanoma vs benign) + diagnosis column | **patient ID**, lesion ID (v2 CSV) | CC BY-NC 4.0 | Not used (binary, ~1.8% melanoma, 23 GB) |

## HAM10000 (primary dataset)

- **Title:** "The HAM10000 dataset, a large collection of multi-source dermatoscopic images of common pigmented skin lesions"
- **Record:** Harvard Dataverse, doi:[10.7910/DVN/DBW86T](https://doi.org/10.7910/DVN/DBW86T). Files are public (not restricted) and no login is needed.
- **Paper:** Tschandl P., Rosendahl C., Kittler H. *Scientific Data* 5, 180161 (2018). doi:[10.1038/sdata.2018.161](https://doi.org/10.1038/sdata.2018.161)
- **License:** Creative Commons **Attribution-NonCommercial 4.0 International** (CC BY-NC 4.0).
  - Allowed: academic, research and portfolio use, sharing and adapting, all **with attribution**.
  - Not allowed: **commercial use**, including selling the app, paid SaaS, or bundling the trained model in a commercial product, unless you get separate permission from the rights holders.
  - Required credit: "(c) by ViDIR Group, Department of Dermatology, Medical University of Vienna; https://doi.org/10.1038/sdata.2018.161". Also cite the paper above.
- **Image sources:** dermatoscopic images collected over 20 years from two sites: the Department of Dermatology at the Medical University of Vienna (Austria), and the skin cancer practice of Cliff Rosendahl in Queensland (Australia). They were acquired with different dermatoscopes and imaging modalities, and include digitized slides.
- **Files we need** (sizes and MD5 come from the Dataverse API):

  | File | Dataverse file ID | Size | MD5 |
  |---|---|---|---|
  | `HAM10000_images_part_1.zip` | 3172585 | 1,366,522,108 B (~1.37 GB) | `4639bfa73ab251610530a97c898e6e46` |
  | `HAM10000_images_part_2.zip` | 3172584 | 1,403,566,547 B (~1.40 GB) | `da43d6cc50f6613013be07e8986b384b` |
  | `HAM10000_metadata` (CSV, "original" format) | 4338392 | ~0.8 MB | checked by row and column count |

- **Metadata columns:** `lesion_id`, `image_id`, `dx` (diagnosis), `dx_type` (how the diagnosis was confirmed), `age`, `sex`, `localization`.
- **Diagnosis confirmation (`dx_type`):** `histo` (histopathology), `follow_up`, `consensus` (expert consensus), `confocal` (in-vivo confocal microscopy). About half of the labels are histopathology-confirmed. The rest rely on follow-up or consensus, so **some label noise is expected**.

### Supported categories (exactly the 7 HAM10000 `dx` codes)

| Code | Category | Notes |
|---|---|---|
| `akiec` | Actinic keratoses and intraepithelial carcinoma / Bowen's disease | Pre-malignant / in-situ |
| `bcc` | Basal cell carcinoma | Malignant |
| `bkl` | Benign keratosis-like lesions (solar lentigo, seborrheic keratosis, lichen-planus-like keratosis) | Benign |
| `df` | Dermatofibroma | Benign |
| `mel` | Melanoma | Malignant |
| `nv` | Melanocytic nevi | Benign. **The majority class**, about two-thirds of the images |
| `vasc` | Vascular lesions (angiomas, angiokeratomas, pyogenic granulomas, hemorrhage) | Benign |

The exact counts per class are **computed from your downloaded copy** by `ml/src/eda.py`. They aren't hard-coded anywhere.

### Known limitations (these affect how results may be interpreted)

1. **Dermoscopic images only.** The model learns from images taken through a dermatoscope. Ordinary smartphone photos look very different, so expect a large drop in accuracy on them.
2. **Population bias.** The sources are Austria and Australia, mostly lighter skin types (Fitzpatrick I–III). Performance on darker skin is **unknown and likely worse**.
3. **Closed set.** Only 7 categories exist. Any other condition (SCC, eczema, psoriasis, infections, non-skin images) is forced into one of the 7 classes. The app mitigates this with an "Inconclusive" confidence threshold, but it **cannot reliably detect out-of-scope images**.
4. **Class imbalance.** `nv` dominates and `df` and `vasc` are rare (around 1% each). Plain accuracy is therefore misleading; we report balanced accuracy, macro-F1 and per-class sensitivity/specificity.
5. **Multiple images per lesion.** Many lesions were photographed more than once. Splitting by image would leak near-duplicates into the test set, so we **group by `lesion_id`**.
6. **No patient ID.** HAM10000 doesn't publish patient identifiers. True patient-level splitting is impossible, and **lesion-level grouping is the strictest split the public metadata allows**. Two different lesions from the same patient may still land in different splits. This is a documented, unavoidable limitation. ISIC 2020 does include patient IDs, and the split code supports `group_column: patient_id` for datasets that have one.
7. **Label noise** from non-histopathology confirmations (see `dx_type`).
8. **Retrospective benchmark.** Test-set metrics measure agreement with HAM10000 labels on held-out HAM10000 lesions. They are **not** clinical sensitivity or specificity, and they don't predict real-world performance.

### Intended use (and non-use)

- ✅ **Intended:** education, research, a software-engineering portfolio, and a demo of an ML-backed web system for **non-commercial** use, with a visible disclaimer.
- ❌ **Not intended:** diagnosis, triage, treatment decisions, use without a clinician, or commercial deployment.
  The trained model is **not a medical device** and makes **no claim of clinical diagnostic accuracy**.

## SCIN — Skin Condition Image Network (used for the "rash or other skin problem" checker)

- **Source:** Google Research & Stanford Medicine, https://github.com/google-research-datasets/scin ·
  public bucket `gs://dx-scin-public-data` · paper arXiv:2402.18545.
- **Licence:** SCIN Data Use License, a Creative Commons-style licence: sharing and adapting are allowed with
  attribution, and commercial use isn't restricted. **Re-identifying or re-linking contributors is strictly
  prohibited.** The licence text doesn't mention ML training explicitly. The authors' FAQ describes use for research and
  development. We store no contributor data beyond condition, skin type and shot type.
- **Content:** 5,033 cases / 10,407 smartphone photos from US internet users (2023). 3,061 cases have dermatologist
  condition labels (up to 3 dermatologists, each giving up to 3 conditions, merged into weighted labels).
- **What we used** (`ml/src/scin_label_analysis.py`, `ml/configs/scin_groups.yaml`, `ml/src/scin_prepare.py`):
  only cases where one condition holds **≥ 50%** of the dermatologists' weight. Closely related labels were grouped
  into 10 everyday conditions, and only groups with ≥ 40 cases were kept:
  eczema (461 cases), contact dermatitis (290), hives (182), insect bite (144), folliculitis (101), fungal infection (93),
  acne/rosacea (88), psoriasis (65), shingles (54), cold sores (51).
  Only those photos were downloaded (~3.9 GB of 12.6 GB, each MD5-verified).
- **Duplicates:** SCIN contains a few identical photos in different cases. Photos whose cases disagree on the
  condition were dropped (2). Other repeats are kept once, and cases sharing a photo are kept in the same split.
  Final set: **3,168 photos, 1,521 split groups**.
- **Limitations:** small classes (tests of 14–139 cases per condition), labels that reflect dermatologist disagreement,
  everyday photos of varying quality, and a US-only, female/younger-skewed contributor group. It does cover more skin tones
  than HAM10000, although darker skin is still under-represented.

## Not usable

- **DermNet** (often re-shared on Kaggle): DermNet's terms state that its free watermarked images **may not be used for AI
  training**. A paid licence is required.
- **Fitzpatrick17k** (114 conditions): annotations are CC BY-NC-SA 3.0. The images must be fetched from two third-party
  atlases (many links may be dead), or requested from the authors. It's a possible future addition for the rash checker.

## ISIC 2019 (planned extension)

- 25,331 training images in 8 categories (MEL, NV, BCC, AK, BKL, DF, VASC, **SCC**). The challenge test set adds an outlier "UNK" class.
- Combines HAM10000, BCN_20000 (Hospital Clínic Barcelona) and MSK datasets. **It contains HAM10000**, so never train on one and test on the other without de-duplicating first.
- License CC BY-NC 4.0. Attribution must cite BCN_20000, HAM10000 and MSK.
- Images: `ISIC_2019_Training_Input.zip` (9.1 GB). Ground truth and metadata are CSVs (~1 MB each), from https://challenge.isic-archive.com/data/
- Adding it would require a new metadata adapter in `ml/src/dataset.py`. The rest of the pipeline is dataset-agnostic.

## ISIC 2020 (not used)

- 33,126 images from 2,000+ patients, with patient IDs. CC BY-NC 4.0. doi:10.34970/2020-ds01. 23 GB of JPEGs.
- The task is binary melanoma detection with heavy imbalance, so it doesn't fit the 7-class design. It's useful later as an external melanoma test set.

## How to obtain HAM10000

Option A, the script (verifies MD5 and extracts):

```powershell
.\scripts\download_ham10000.ps1
```

Option B, by hand: open https://doi.org/10.7910/DVN/DBW86T, download the two image zips and
`HAM10000_metadata` (choose **Original File Format**, CSV), then arrange them like this:

```
ml/data/raw/HAM10000/
├── HAM10000_metadata.csv
├── HAM10000_images_part_1/   (*.jpg)
└── HAM10000_images_part_2/   (*.jpg)
```

`ml/data/` is git-ignored, so the dataset is never committed.

## Sources

- Harvard Dataverse HAM10000 record: https://doi.org/10.7910/DVN/DBW86T
- ISIC challenge data page (2018/2019/2020 files, licenses, attributions): https://challenge.isic-archive.com/data/
- SIIM-ISIC 2020 dataset: https://doi.org/10.34970/2020-DS01
