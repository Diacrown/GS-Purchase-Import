# GS Purchase Import

Automate gemstone purchase intake into **EZ JEMS** ERP.

Manager drops a short Excel (Report No + Password + Unit Price + per-stone FWD LOC/FWD SSP) → the existing [AGL Report Fetcher](https://github.com/Diacrown/Certificate-Scrapper) pulls each cert → this tool extracts the fields, applies glossaries, generates Item# codes using BULK PI's convention, and emits a 29-column file matching EZ JEMS's `GS_BULK_IMPORT.xlsx` template. Manager imports the output file directly into EZ JEMS.

Replaces hand-typing ~10 fields per stone off every certificate.

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
AGL Report Fetcher   (existing — Diacrown/Certificate-Scrapper, Fly.io)
    • fetches each cert from aglthai.com
    • returns raw AGL HTML + cert image per row
          │
          ▼
gemstone_intake.extract.extract_from_html(html)
    • returns AGLReport JSON
          │
          ▼
glossaries + constants layer
    • AGL variety → ERP ST + Item# prefix
    • AGL shape   → ERP 3-letter + 2-digit code
    • AGL colour  → ERP 3-letter code
    • attach constants (Clarity=EC0, SBK=A, IT=PP, …)
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

---

## Install (local)

```bash
pip install -r requirements.txt
pytest tests/ -q                          # 45 tests, all green
PYTHONPATH=. python demo/build_bulk_demo.py   # 15-stone end-to-end
```

## Run (CLI)

```bash
PYTHONPATH=. python -m gemstone_intake.cli \
    intake.xlsx  agl_responses/  out_ezjems_import.xlsx
```

## Run (web app, locally)

```bash
pip install -r requirements.txt
INTAKE_API_KEY=dev python -m app.app
# UI at http://localhost:8080 — API key field accepts "dev"
```

## Deploy to Fly.io

Mirrors `Diacrown/Certificate-Scrapper`'s deployment — same provider, same region.

```bash
fly launch --no-deploy
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
│   ├── extract.py              # AGL HTML → AGLReport JSON
│   ├── constants.py            # ERP constants + 29-column template order
│   ├── glossaries.py           # 5 mapping tables (variety/shape/colour/treatment/origin)
│   ├── item_code.py            # Item# generator (ports BULK PI logic)
│   ├── mapping.py              # AGLReport + intake row → ERP row dict
│   ├── pipeline.py             # Excel in → Excel out, 3-tier flagging
│   ├── cli.py                  # command-line wrapper
│   └── flask_blueprint.py      # drop-in blueprint for the fetcher app
├── app/                        # Flask web app for hosted use
│   ├── app.py                  # Flask entry; POST /run endpoint
│   └── templates/index.html    # VS Code-themed upload UI
├── tests/                      # 45 unit tests
├── demo/
│   ├── build_demo.py           # small 3-stone demo
│   └── build_bulk_demo.py      # 15-stone glossary-coverage demo
├── docs/
│   ├── DEPLOY.md               # Fly.io deployment walkthrough
│   └── ERP_FIELD_MAPPING.md    # Full 29-column mapping + Sonesh answers
├── Dockerfile                  # python:3.11-slim + gunicorn
├── fly.toml                    # Fly.io app config (bom region)
├── requirements.txt            # pinned deps
└── .dockerignore / .gitignore
```

---

## Related internal tools

- **[Diacrown/Certificate-Scrapper](https://github.com/Diacrown/Certificate-Scrapper)** — AGL / IGI / HRD / GIA lab-report fetcher. Upstream of this tool; same hosting pattern.
- **BULK PI GENERATOR** — colored-stone + diamond PP-code generator (single-file HTML). Source of the Item# generation convention this tool reuses.
