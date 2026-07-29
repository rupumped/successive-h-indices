import json
from pathlib import Path

import pandas as pd
import pycountry

ROOT = Path(__file__).parent.parent
INTERIM = ROOT / "data" / "interim"
RESULTS = ROOT / "results"


def country_name(code):
    try:
        c = pycountry.countries.get(alpha_2=code)
        return c.name if c else code
    except LookupError:
        return code


def stem_to_name(stem):
    return stem.replace("__", ", ").replace("_", " ")


def load_institutions(csv_path, nrows=None):
    df = pd.read_csv(csv_path, nrows=nrows)
    return [{"name": r.institution_name, "h2": int(r.h2)} for r in df.itertuples()]


def load_countries(csv_path, nrows=None):
    df = pd.read_csv(csv_path, nrows=nrows)
    return [{"name": country_name(r.country_code), "h3": int(r.h3)} for r in df.itertuples()]


output = {
    "institutions": load_institutions(INTERIM / "h2_by_institution.csv"),
    "countries": load_countries(INTERIM / "h3_by_country.csv"),
    "fields": {},
    "subfields": {},
}

for csv_path in sorted((RESULTS / "h2_by_field").glob("*.csv")):
    output["fields"].setdefault(stem_to_name(csv_path.stem), {})["institutions"] = load_institutions(csv_path, nrows=100)

for csv_path in sorted((INTERIM / "h3_by_field").glob("*.csv")):
    output["fields"].setdefault(stem_to_name(csv_path.stem), {})["countries"] = load_countries(csv_path, nrows=100)

for csv_path in sorted((RESULTS / "h2_by_subfield").glob("*.csv")):
    output["subfields"].setdefault(stem_to_name(csv_path.stem), {})["institutions"] = load_institutions(csv_path, nrows=100)

for csv_path in sorted((INTERIM / "h3_by_subfield").glob("*.csv")):
    output["subfields"].setdefault(stem_to_name(csv_path.stem), {})["countries"] = load_countries(csv_path, nrows=100)

out_path = ROOT / "rankings.json"
out_path.write_text(json.dumps(output))
print(f"Wrote {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")
