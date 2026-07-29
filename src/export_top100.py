import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent

SOURCES = {
    "h2_by_field": ROOT / "results" / "h2_by_field",
    "h2_by_subfield": ROOT / "results" / "h2_by_subfield",
    "h3_by_field": ROOT / "data" / "interim" / "h3_by_field",
    "h3_by_subfield": ROOT / "data" / "interim" / "h3_by_subfield",
}

EXPORT_ROOT = ROOT / "export"

for folder_name, src_dir in SOURCES.items():
    dest_dir = EXPORT_ROOT / folder_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    for csv_path in sorted(src_dir.glob("*.csv")):
        df = pd.read_csv(csv_path, nrows=101)
        df.to_csv(dest_dir / csv_path.name, index=False)

FULL_COPIES = [
    ROOT / "data" / "interim" / "h2_by_institution.csv",
    ROOT / "data" / "interim" / "h3_by_country.csv",
]

for src in FULL_COPIES:
    shutil.copy(src, EXPORT_ROOT / src.name)

print(f"Exported to {EXPORT_ROOT}")
