"""csv_io.py - read lab CSVs as raw strings, never silently coerced.

The historical corruption mechanism was pandas turning an Excel-time cell like
"4:48" into a float/NaN. Every intake path must therefore read strings first and
convert deliberately.
"""
import numpy as np
import pandas as pd


def read_raw_csv(path):
    """Read a CSV with all columns as object/str; blanks become NaN, no downcast."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    out = df.astype(object)
    for col in out.columns:
        out[col] = (out[col].str.strip()
                    .map(lambda v: np.nan if v == "" else v)
                    .astype(object))
    return out
