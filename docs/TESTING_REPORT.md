# Testing & security review report

**Last updated:** 2026-11-13 · **Scope:** Flask backend, Tailwind frontend, both ML checkers, ML pipelines, MySQL ·
**Environment:** Windows 11, Python 3.12.10, TensorFlow 2.21.0 (CPU), Flask 3.1.3, MySQL 8.0.46

## 1. Result summary

| Run | How | Result |
|---|---|---|
| Full automated suite | `.\.venv\Scripts\python.exe -m pytest tests` | **104 passed, 0 failed, 0 skipped** |
| Lint (errors, bugbear) | `ruff check app skinai_ml ml tests --select F,E9,B` | clean |
| Migrations | `flask db upgrade` on fresh SQLite + `flask db check`; applied to the real MySQL database | 3 revisions applied, no drift |
| Real MySQL | app account `skin_ai_app` (SELECT/INSERT/UPDATE/DELETE only) | pages served from MySQL; DDL correctly refused |
| Control scripts | start → status → start → restart → stop | all as designed (restart race fixed, §3) |
| End-to-end with the **real** trained models | throwaway SQLite sandbox: upload → quality check → consent → inference → result page → heatmap, both checkers | works; see §5 for what it showed |
| Browser pass | desktop 1280 px and phone 375 px, light and dark, Tailwind build | no horizontal overflow; UI bugs fixed (§3) |

## 2. What is covered

| Area | Tests | What is verified |
|---|---|---|
| Registration & login | `test_auth.py` | Argon2id hashing; email normalisation; weak/common/mismatched passwords; consent; generic login errors; lockout after 5 failures; inactive accounts; POST-only logout; open-redirect blocking; password change signs out other sessions; profile validation; account deletion; CLI `create-admin` |
| Authorization | `test_isolation_and_admin.py` | protected pages redirect; API returns 401; non-admins get 403 on all admin pages, APIs and actions |
| **Record isolation** | `test_isolation_and_admin.py` | another user gets 404 on result, photo, heatmap, preview, analyse, delete and feedback; their history, stats and CSV stay empty; admins can't open user photos |
| Admin | `test_isolation_and_admin.py`, `test_two_checkers.py` | no self-deactivation/demotion; last admin protected; deactivation ends sessions; model activation is **per checker**; category edits; audit log |
| Upload safety | `test_upload.py` | private storage, random names, path traversal ignored, **EXIF/GPS removed**, PHP/SVG/GIF/EXE/truncated/empty/tiny files rejected, decompression bomb, >8 MB → 413, blank photo rejected, greyscale warned, polyglot payload removed |
| ML inference | `test_prediction_flow.py` | consent required; stored scores equal an independent run of the exported model (nothing hard-coded); "not sure" path; deterministic; heatmap; tampered model refused |
| **Two checkers** | `test_two_checkers.py` | all 17 conditions seeded; rash photos use only the rash model and its 10 conditions; mole photos use the mole model; a checker with no model is reported, never faked; invalid checker rejected; rash results carry the early-version warning |
| History & analytics | `test_prediction_flow.py`, `test_isolation_and_admin.py` | filters, pagination, delete removes files, feedback, CSV without personal data; dashboard and analytics equal the database |
| Security | `test_security.py` | CSRF on every state-changing form; SQL-injection payloads harmless; CSP without `unsafe-inline`, nosniff, frame and referrer headers; HttpOnly/SameSite cookies; no-store on private pages; no inline scripts/styles; hashes never rendered; no tracebacks on 500; login rate limit; SECRET_KEY not in any file; `.env`, uploads, data and models git-ignored |
| ML pipeline | `tests/ml/*` | preprocessing contract, grouped split without leakage, class weights, augmentation, metric maths, full pipeline smoke test |

## 3. Bugs found and fixed

| # | Bug | Found by | Fix |
|---|---|---|---|
| 1 | Decompression bombs rejected with a misleading message | pytest | dedicated "too large" message |
| 2 | Upload error hidden when no model installed | pytest | error shown in that state |
| 3–6 | Invisible header button text; missing side gutter; `<figure>` indent; inconsistent rounding of scores | browser | CSS and template fixes |
| 7 | `*.keras` model files not git-ignored outside `ml/artifacts` | review | added to `.gitignore` |
| 8 | Test harness shared login state between test clients | pytest | per-request reset in `conftest.py` |
| 9 | TF op determinism made augmentation 11× slower | profiling | determinism off by default (documented) |
| 10 | HAM10000 download gave up after one connection drop | real download | automatic resume with retries |
| 11 | Condition `code` column too short (16) for `contact_dermatitis` — invisible on SQLite | **real MySQL** | widened to 32 + migration |
| 12 | `db_upgrade.ps1` treated Alembic's normal stderr logging as failure | real MySQL | judged by exit codes |
| 13 | SCIN contains identical photos in different cases → possible train/test leakage | data check | conflicting duplicates dropped, cases sharing a photo kept in one split |
| 14 | `restart.ps1` mistook Windows' leftover PID-0 port entry for another program | real restart | PID 0 ignored; stop waits for the port |

## 4. Model results (held-out test sets, never used for training or selection)

**Mole or spot checker** — EfficientNetB0, HAM10000, 1,431 test photos:
balanced accuracy **55.4%**, macro-F1 0.545, macro AUC 0.926; malignant/pre-malignant sensitivity **59.1%**
(specificity 90.6%); **melanoma sensitivity 42%**. When ≥70% sure (59% of photos) it is right 92.8% of the time.
Training was interrupted at round 16 of 30 and finished from the best saved checkpoint (documented in the model card).

**Rash or other skin problem checker** — EfficientNetB0, SCIN, 453 test photos (218 cases):
balanced accuracy **26.2%** (chance 10%), macro-F1 0.26, macro AUC 0.708. Reasonable on acne (F1 0.63) and eczema (0.50);
very poor on fungal infection, psoriasis and cold sores (F1 ≤ 0.07). Enabled at the owner's request and clearly labelled
**"Early version: often unsure"** on every page where it appears.

## 5. Not verified / known limitations (stated plainly)

- **Accuracy is limited.** In the real end-to-end check a melanoma test photo was reported as "Common mole, 58%"
  (melanoma 25% as runner-up). The site always shows all scores and recommends a doctor, but this is a real weakness.
- **Not a medical device;** no clinical validation. Metrics are retrospective agreement with dataset labels.
- The automated suite runs on SQLite; MySQL was exercised by migrations, seeding and live pages, not by the full suite.
- Rate limiting uses in-memory storage (fine for one process). HTTPS is not configured (local use).
- Not done: penetration testing with external tools, load testing, dependency CVE scan, screen-reader testing.
