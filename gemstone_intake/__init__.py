"""
gemstone_intake — automate gemstone purchase intake into EZ JEMS.

Pipeline
--------
    [Report#, Password, Unit Price]   (manager's intake Excel)
            │
            ▼
    AGL Report Fetcher                (existing Flask app, Fly.io)
            │   returns raw AGL HTML per row
            ▼
    extract.extract_from_html         ← Step 1
            │   returns AGLReport JSON
            ▼
    mapping.ag l_to_erp_row           ← Step 3
            │   applies glossaries + constants
            ▼
    item_code.build_gemstone_item_code← Step 4 (ports BULK PI logic)
            │   generates Item #
            ▼
    pipeline.build_output_workbook    ← Step 5
            │   writes 29-col GS_BULK_IMPORT shape
            ▼
    EZ JEMS import file (.xlsx)

Entry points
------------
- CLI:    python -m gemstone_intake.cli <intake.xlsx> <agl_dir> <out.xlsx>
- Flask:  gemstone_intake.flask_blueprint:bp
- Lib:    from gemstone_intake import run_pipeline
"""
from .extract import AGLReport, Dimensions, extract_from_html
from .mapping import agl_to_erp_row, MappingResult
from .item_code import build_gemstone_item_code
from .pipeline import run_pipeline, run_pipeline_live, PipelineResult

__all__ = [
    "AGLReport", "Dimensions", "extract_from_html",
    "agl_to_erp_row", "MappingResult",
    "build_gemstone_item_code",
    "run_pipeline", "run_pipeline_live", "PipelineResult",
]
