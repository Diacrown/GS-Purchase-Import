# GS Purchase Import

Automate gemstone purchase intake into **EZ JEMS** ERP.

Manager drops a short Excel (Report No + Password + Unit Price + per-stone FWD LOC / FWD SSP). The server fetches each cert image from `aglthai.com`, reads the fields off the image with Google Gemini, applies glossaries, generates Item# codes using BULK PI's convention, and emits a 29-column file matching EZ JEMS's `GS_BULK_IMPORT.xlsx` template. Manager imports the output file directly into EZ JEMS.

**One file in, one file out.** Replaces hand-typing ~10 fields per stone off every certificate.

---

## Status

~90% complete. End-to-end pipeline runs green on the bulk demo (15 stones, 14 ok + 1 amber). Three stubs remain, each replaceable in one file without touching callers — see [docs/ERP_FIELD_MAPPING.md](docs/ERP_FIELD_MAPPING.md).

| Stub | Replace with |
|------|--------------|
| AGL HTML selectors (`gemstone_intake/extract.py`) | one captured real AGL Thai response HTML |
| Measurement-code rule (`gemstone_intake/item_code.py`) | exact rule from BULK PI GENERATOR's `buildGemstoneCode` |
| Glossary entries marked "confirm" (`gemstone_intake/glossaries.py`) | ERP stock export joined with AGL fetcher output |

---

## Pipeline

```
Manager's intake Excel
[Report No | Password | Unit Price | FWD LOC | FWD SSP | Lot No?]
          │
          ▼
gemstone_intake.fetch.fetch_report_image(report_no, password)
    • POSTs to aglthai.com/report_check.php (ports Certificate-Scrapper logic)
    • returns raw cert image bytes per row
          │
          ▼
gemstone_intake.vision.extract_from_image(image_bytes)
    • sends the image to Google Gemini (requires GEMINI_API_KEY)
    • returns AGLReport JSON {variety, weight_ct, shape, colour, dimensions, treatment, origin}
          │
          ▼
glossaries + constants layer
    • AGL variety → ERP ST + Item# prefix (3-letter short code)
    • AGL shape   → ERP 3-letter + 2-digit code (OCT → EME override)
    • AGL colour  → ERP 3-letter code (collapses Cornflower Blue → BLU etc.)
    • attach constants (Clarity=EC0, SBK=A, IT=PP, Inv Effect=1, Lab=AGL)
          │
          ▼
item_code.build_gemstone_item_code()
    • generates Item # (e.g. RUB10RED55)
          │
          ▼
pipeline.write_output()
    • 29-col GS_BULK_IMPORT.xlsx-shaped file
    • side columns (__Status, __Warnings, __Raw AGL *)
    • amber-tinted partials; red rows skipped
          │
          ▼
Manager imports into EZ JEMS
```

Rate-limited to one AGL call every 2 seconds (matches Certificate-Scrapper's convention). Expect ~3 s per row end-to-end.

---

## Install (local)

```bash
pip install -r requirements.txt
pytest tests/ -q                          # 64 tests, all green
PYTHONPATH=. python demo/build_bulk_demo.py   # offline 15-stone demo (file-based)
```

## Run (web app, locally)

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="your-gemini-key"   # from https://aistudio.google.com
export INTAKE_API_KEY="dev"               # optional; locks /run behind X-API-Key
python -m app.app
# UI at http://localhost:8080
```

## Required / optional env vars

| Var | Required | Purpose |
|-----|----------|---------|
| `GEMINI_API_KEY`   | **yes** for `/run` | Google Gemini key for the vision extractor |
| `INTAKE_API_KEY`   | optional | if set, every `/run` request must carry a matching `X-API-Key` header |
| `GEMINI_MODEL`     | optional | default `gemini-2.0-flash`; override to e.g. `gemini-1.5-pro` for higher accuracy |
| `AGL_LOOKUP_DELAY` | optional | seconds between AGL calls, default `2.0` |

## Deploy to Fly.io

Mirrors `Diacrown/Certificate-Scrapper`'s deployment — same provider, same region.

```bash
fly launch --no-deploy
fly secrets set GEMINI_API_KEY="your-gemini-key"
fly secrets set INTAKE_API_KEY="$(openssl rand -hex 24)"
fly deploy
fly open
```

Full deploy guide: [docs/DEPLOY.md](docs/DEPLOY.md).

---

## Repo layout

```
.
├── gemstone_intake/            # Python package
│   ├── fetch.py                # AGL cert fetcher (ports Certificate-Scrapper)
│   ├── vision.py               # Gemini-based cert-image → AGLReport extractor
│   ├── extract.py              # HTML → AGLReport (used by offline file-based path)
│   ├── constants.py            # ERP constants + 29-column template order
│   ├── glossaries.py           # 5 mapping tables (variety/shape/colour/treatment/origin)
│   ├── item_code.py            # Item# generator (ports BULK PI logic)
│   ├── mapping.py              # AGLReport + intake row → ERP row dict
│   ├── pipeline.py             # run_pipeline_live (live) + run_pipeline (offline)
│   ├── cli.py                  # command-line wrapper
│   └── flask_blueprint.py      # drop-in blueprint for existing Flask apps
├── app/                        # Flask web app for hosted use
│   ├── app.py                  # Flask entry; POST /run live pipeline
│   └── templates/index.html    # VS Code-themed single-upload UI
├── tests/                      # 64 unit tests
├── demo/                       # offline file-based demos
├── docs/
│   ├── DEPLOY.md               # Fly.io deployment walkthrough
│   └── ERP_FIELD_MAPPING.md    # Full 29-column mapping + Sonesh answers
├── Dockerfile                  # python:3.11-slim + gunicorn (600s timeout)
├── fly.toml                    # Fly.io app config (bom region)
├── requirements.txt            # pinned deps
└── .dockerignore / .gitignore
```

---

## Related internal tools

- **[Diacrown/Certificate-Scrapper](https://github.com/Diacrown/Certificate-Scrapper)** — AGL / IGI / HRD / GIA lab-report fetcher. Upstream of this tool; same hosting pattern.
- **BULK PI GENERATOR** — colored-stone + diamond PP-code generator (single-file HTML). Source of the Item# generation convention this tool reuses.
