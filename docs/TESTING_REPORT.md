# Testing & security review report

**Date:** 2026-11-10 · **Scope:** Flask backend, frontend, ML integration, ML pipeline · **Environment:** Windows 11, Python 3.12.10, TensorFlow 2.21.0 (CPU), Flask 3.1.3

## 1. Result summary

| Run | Command | Result |
|---|---|---|
| Full automated suite | `.\.venv\Scripts\python.exe -m pytest tests` | **98 passed, 1 skipped, 0 failed** (86.8 s) |
| Lint (errors, bugbear) | `ruff check app skinai_ml ml tests --select F,E9,B` | clean |
| Migration | `flask db upgrade` on a fresh SQLite file + `flask db check` | applied, no drift |
| MySQL DDL | `flask db upgrade --sql` (offline, MySQL dialect) | rendered (ENUM, JSON, BIGINT AUTO_INCREMENT) |
| Control scripts | start → status → start → restart → stop → status | all behaved as designed; port freed; MySQL801 untouched |
| Manual browser pass | preview sandbox on :8011, desktop 1280 px and mobile 375 px, light and dark | flows worked; 5 UI bugs found and fixed (§3) |

**Skipped (1):** `test_env_and_private_dirs_are_git_ignored` uses `git check-ignore`, and the project isn't a Git repository yet. The `.gitignore` *contents* are asserted in the same test before the skip.

## 2. What is covered

| Area | Tests (file) | What is verified |
|---|---|---|
| Registration & login | `test_auth.py` | Argon2id hashing; email normalisation; duplicate, weak, common and mismatched passwords; missing consent; invalid email; markup in names; generic login errors; lockout after 5 failures; inactive accounts; POST-only logout; open-redirect blocking; password change signs out other sessions; profile validation; account deletion (password + "DELETE" confirmation); CLI `create-admin` |
| Authorization | `test_isolation_and_admin.py` | 14 protected pages redirect anonymous users; API returns 401; non-admin gets 403 on 9 admin pages, 2 admin APIs and 4 admin POST actions |
| **User record isolation** | `test_isolation_and_admin.py` | Another user gets **404** on result, image, heatmap, preview, analyse, delete and feedback; their history, stats and CSV contain none of the owner's rows; admins can't open user images |
| Admin | `test_isolation_and_admin.py` | No self-deactivation or self-demotion; last admin protected; deactivation ends sessions immediately; invalid role rejected; model activation; category edit validation; audit entries written |
| Image upload | `test_upload.py` | Stored outside `/static`, UUID name, path-traversal filename ignored; **EXIF/GPS stripped**; PNG with alpha; rejects PHP-in-JPG, SVG, GIF, `.exe`, truncated and empty files, too-small images; **decompression bomb**; >8 MB → 413; blank image rejected; greyscale warned; duplicate reuse; polyglot payload removed by re-encoding |
| ML inference | `test_prediction_flow.py` | Consent required; **stored scores equal an independent run of the exported model** on the stored image (no hard-coding); 7 scores sum to 1; "inconclusive" path; threshold/margin rule; identical scores for an identical image; Grad-CAM produced and served privately; tampered model refused (500 with a friendly message, nothing stored) |
| History | `test_prediction_flow.py` | Filters (category, status, risk, dates), invalid filter handling, pagination, delete removes image and heatmap files, feedback validation, CSV export without PII |
| Analytics | `test_prediction_flow.py`, `test_isolation_and_admin.py` | Dashboard figures, `/api/v1/me/stats`, `/api/v1/admin/analytics` and `/admin/overview` equal the database contents |
| Security | `test_security.py` | **CSRF** enforced on login, register, logout, profile, password, delete account, upload and delete; **SQL-injection** payloads in login, filters, URLs and admin search are harmless (users table intact); CSP without `unsafe-inline`, nosniff, X-Frame-Options, Referrer-Policy; HttpOnly + SameSite cookies; `no-store` on private pages; no inline scripts, styles or handlers in any template; password hashes never rendered; 500 pages don't leak tracebacks; login rate limit (6th attempt → 429); **SECRET_KEY value not present in any project file** |
| Services | `tests/unit/test_services.py` | Hashing round-trip and salting, password policy, safe redirects, OpenCV quality checks (blank, dark, overexposed, blurry, greyscale) |
| ML pipeline | `tests/ml/*` | Preprocessing contract, grouped split with **no lesion leakage**, reproducible splits, class weights, augmentation randomness, metric maths against a hand-computed example, **end-to-end pipeline** (EDA → split → train both architectures → evaluate → export → predictor → tamper rejection) |
| Theme & brand | `test_health.py` | DermaCareAI branding; `theme.js` loads before CSS; dark-mode CSS present |

## 3. Bugs found and fixed during this review

| # | Bug | Found by | Fix |
|---|---|---|---|
| 1 | Decompression-bomb images were rejected with a misleading "not a valid image" message | pytest | Catch Pillow bomb errors separately → "The image dimensions are too large." |
| 2 | When no model is installed, the upload POST error wasn't shown (only the generic empty state) | pytest | Error alert now rendered in the no-model state |
| 3 | Header "Create account" button had invisible text (nav link colour overrode the button) | browser | Specific `.nav a.btn` rule |
| 4 | Page content had no side gutter on narrow screens (`.page` reset the container padding) | browser | `.page` and `.error-page` set only vertical padding |
| 5 | Default `<figure>` margins indented image frames | browser | `figure { margin: 0 }` |
| 6 | Result headline (99%) and score list (98.5%) rounded differently; alternatives at 0.2% shown as "0%" | browser | One decimal place everywhere; alternatives shown only if ≥ 5%, otherwise an explicit sentence |
| 7 | `.gitignore` didn't cover `*.keras` model files outside `ml/artifacts/` | review | Added `*.keras` |
| 8 | Test-harness flaw: a shared app context leaked the logged-in user between test clients, hiding session bugs | pytest | Per-request reset in `tests/conftest.py`. The app itself was not affected |

## 4. Not verified, and known limitations (stated plainly)

- **No real model has been trained.** HAM10000 hasn't been downloaded (`scripts/download_ham10000.ps1`, about 2.8 GB). No accuracy or other metrics exist yet, and none are shown anywhere. End-to-end tests use a **tiny CNN trained on nothing**, whose outputs are real Keras inference but meaningless as diagnoses.
- **MySQL has not been exercised live.** The database and users need your MySQL root password, which you enter yourself via `scripts/db_setup.ps1`. Tests ran on SQLite. The migration's MySQL DDL was rendered offline but not executed. After setup, run the same suite on MySQL with `TEST_DATABASE_URL` (use a separate test database).
- **Rate limiting uses in-memory storage**, which is fine for one Waitress process. Multiple processes would need Redis.
- **HTTPS** isn't configured (local development). `ProductionConfig` enables Secure cookies, HSTS and HTTPS redirects once it runs behind TLS.
- **Live OS theme switching** (changing the OS theme while a page is open) is coded but couldn't be confirmed in the embedded browser. Saved choices, OS default on load, and reload persistence were confirmed.
- Manual browser checks covered all page types at 1280 px and 375 px, but not screen readers or other browsers (Firefox, Safari).
- Not done: penetration testing with external tools, load testing, dependency CVE scanning (`pip-audit` isn't installed).
