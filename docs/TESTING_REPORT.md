# Testing & security review report

**Last updated:** 2026-11-16 · **Scope:** Flask backend, Tailwind frontend, both ML checkers, ML pipelines, MySQL ·
**Environment:** Windows 11, Python 3.12.10, TensorFlow 2.21.0 (CPU), Flask 3.1.3, MySQL 8.0.46

## 1. Result summary

| Run | How | Result |
|---|---|---|
| Full automated suite | `.\.venv\Scripts\python.exe -m pytest tests` | **192 passed, 0 failed, 0 skipped** |
| Lint (errors, bugbear) | `ruff check app skinai_ml ml tests --select F,E9,B` | clean |
| Migrations | `flask db upgrade` on fresh SQLite + `flask db check`; applied to the real MySQL database | 4 revisions applied (adds `users.google_sub`), no drift |
| Real MySQL | app account `skin_ai_app` (SELECT/INSERT/UPDATE/DELETE only) | pages served from MySQL; DDL correctly refused |
| Control scripts | start → status → start → restart → stop | all as designed (restart race fixed, §3) |
| End-to-end with the **real** trained models | throwaway SQLite sandbox: upload → quality check → consent → inference → result page → heatmap, both checkers | works; see §5 for what it showed |
| Browser pass | desktop 1280 px and phone 375 px, light and dark, Tailwind build | no horizontal overflow; sidebar menu checked on desktop and phone; UI bugs fixed (§3) |

## 2. What is covered

| Area | Tests | What is verified |
|---|---|---|
| Registration & login | `test_auth.py` | Argon2id hashing; email normalisation; weak/common/mismatched passwords; consent; generic login errors; lockout after 5 failures; inactive accounts; POST-only logout; open-redirect blocking; password change signs out other sessions; profile validation; account deletion; CLI `create-admin` |
| Authorization | `test_isolation_and_admin.py` | protected pages redirect; API returns 401; non-admins get 403 on all admin pages, APIs and actions |
| **Record isolation** | `test_isolation_and_admin.py` | another user gets 404 on result, photo, heatmap, preview, analyse, delete and feedback; their history, stats and CSV stay empty; admins can't open user photos |
| Admin | `test_isolation_and_admin.py`, `test_two_checkers.py` | no self-deactivation/demotion; last admin protected; deactivation ends sessions; model activation is **per checker**; category edits; audit log |
| Upload safety | `test_upload.py` | private storage, random names, path traversal ignored, **EXIF/GPS removed**, PHP/SVG/GIF/EXE/truncated/empty/tiny files rejected, decompression bomb, >8 MB → 413, blank photo rejected, greyscale warned, polyglot payload removed |
| ML inference | `test_prediction_flow.py` | consent required; stored scores equal an independent run of the exported model (nothing hard-coded); "not sure" path; deterministic; heatmap; tampered model refused |
| **Home care tips** | `test_care.py`, `test_home_care.py` | every condition has an entry; 3–5 tips each; skin cancers get no remedies, only "see a dermatologist as soon as possible"; no doses; tips only shown when the AI is sure; cancer message shown even when unsure |
| **Two checkers** | `test_two_checkers.py` | all 24 conditions seeded; rash photos use only the rash model and its conditions; mole photos use the mole model; a checker with no model is reported, never faked; invalid checker rejected; rash results carry the limits warning |
| **Google sign-in, Excel, face photos** | `test_google_excel_switch.py` | Google button hidden unless configured; new account without password; linking by verified email only; unverified email and switched-off accounts refused; cancel handled; Google-only users can add a password and delete their account; user Excel has only their own rows; admin workbook has all 5 sheets with real numbers; Excel formula-injection guard; face warning only for the mole checker; one-click switch to the rash checker (owner only) |
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
| 15 | A face photo with acne sent to the mole checker came back as "Common mole" | user report | face detection (OpenCV YuNet) warns and offers a one-click switch to the rash checker |
| 16 | Dashboard chart cut off category names | user report | only categories you have results for are shown |
| 17 | Stray `t` printed at the top of the My account page | review | removed |
| 24 | "Not sure" mode showed two answers side by side (acne from the rash checker, skin cancer from the mole checker) | user report | a photo sorter (CLIP features, 99.9% in grouped cross-validation) picks one checker; the mole checker is added only for "dark spots" or "not a skin problem" answers |
| 23 | "Find dermatologists" showed nothing: the OpenStreetMap Overpass servers timed out (45 s+) | real site | clinic search moved to OpenStreetMap Nominatim (about 5 s); "Searching…" shown while it runs |
| 22 | Every Delete / confirm button did nothing in browsers that block pop-ups (window.confirm silently returned "no") | user report | the site's own confirmation box (`<dialog>`) instead of the browser pop-up; checked in the browser |
| 21 | A forehead photo with many small acne bumps comes back as "ringworm 82%" | user report | **not fixed**: three fixes tried (CLIP text blend, extra acne-type photos, zoomed-crop training), none fixed it without making other results worse; listed under known limitations |
| 20 | "About the AI" page crashed (500) when a model answer has no measured results ("not a skin problem") | real site | such rows are left out; regression test added |
| 19 | New "dark spots" photos made a side-view acne photo come back as dark spots (79%) — the pigmentation set is mostly side-view cheeks | spot check on real uploads | DermNet-sourced acne close-ups (also side-view cheeks) kept in training → acne 68% |
| 18 | Rash checker forced one of 3 answers for any photo (selfie → ringworm 99%, acne → eczema) | user report | acne added; CLIP model; "not a skin problem" answer |

## 4. Model results (held-out test sets, never used for training or selection)

**Mole or spot checker** — EfficientNetB0, HAM10000, 1,431 test photos:
balanced accuracy **55.4%**, macro-F1 0.545, macro AUC 0.926; malignant/pre-malignant sensitivity **59.1%**
(specificity 90.6%); **melanoma sensitivity 42%**. When ≥70% sure (59% of photos) it is right 92.8% of the time.
Training was interrupted at round 16 of 30 and finished from the best saved checkpoint (documented in the model card).

**Rash or other skin problem checker (v4, current)** — same CLIP method as v3 with two Roboflow Universe sets added
(CC BY 4.0). 2,421 photos, 8 conditions: acne, skin irritation, eczema, ringworm, dark spots, redness, scratches & cuts,
healthy skin. 5-fold cross-validation grouped by person/case/original photo: accuracy **83.6%** (balanced 79.5%),
**74.3% on the supplied photos** (v3: 77.2%), **88.6% when at least 60% sure** (88% of photos). Per condition:
healthy 98%, scratches & cuts 96%, dark spots 89%, acne 88%, redness 85%, ringworm 66%, skin irritation 61%, eczema 53%.
The photo check turns away 5% of genuine photos. Dry skin was **not** added: the dry/normal/oily set scored 39% (33% =
guessing). On the 4 real uploads: selfie → not a skin problem (99%), acne → acne (90%, 68%, 92%).

**Rash checker v3 (previous)** — CLIP ViT-B/16 image features + logistic regression, with a
"not a skin problem" photo check. 880 photos: the supplied rash/acne photos (202) plus a capped SCIN subset (678), 4 conditions
(acne, skin irritation, eczema, ringworm). 5-fold cross-validation grouped by person/case: accuracy **66.4%** (balanced 66.9%),
**77.2% on the supplied photos**, and **72.2% when it is at least 60% sure** (79% of photos). The photo check wrongly turns
away 5% of genuine skin photos.

Why this replaced v2 (EfficientNetB3, 3 conditions, 76% in cross-validation): v2 failed on real uploads. It had no acne class
and no way to say "not a skin problem", so a selfie came back as "ringworm 99%" and acne as "eczema 97%". On those same 4 real
uploads v3 answers: selfie → not a skin problem (90%), acne → acne (95%, 94%), faint marks → acne (69%). Four photos are a
spot check, not a measurement. The 98% that was asked for is not reachable honestly with this data.

## 5. Not verified / known limitations (stated plainly)

- **Rash checker mistakes acne for ringworm on some photos.** A real forehead photo with many small skin-coloured
  acne bumps (brown skin) comes back as ringworm 82%. More acne photos and crop training did not fix it.

- **Accuracy is limited.** In the real end-to-end check a melanoma test photo was reported as "Common mole, 58%"
  (melanoma 25% as runner-up). The site always shows all scores and recommends a doctor, but this is a real weakness.
- **Not a medical device;** no clinical validation. Metrics are retrospective agreement with dataset labels.
- The automated suite runs on SQLite; MySQL was exercised by migrations, seeding and live pages, not by the full suite.
- Rate limiting uses in-memory storage (fine for one process). HTTPS is not configured (local use).
- Not done: penetration testing with external tools, load testing, dependency CVE scan, screen-reader testing.
