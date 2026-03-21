import os
import time
import warnings
from multiprocessing import Pool, cpu_count
from pathlib import Path

import pandas as pd
from astropy.io import fits
from astropy.utils.exceptions import AstropyWarning
from astropy.wcs import WCS

from constants import JWST_DATALABS_PATH, JWST_FILTERS, STAGE3_REGEX

warnings.simplefilter("ignore", category=AstropyWarning)

REPO_ROOT = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "DATA"
FILE_PATHS_OUTPUT = DATA_DIR / "file_paths.parquet"
FOOTPRINTS_OUTPUT = DATA_DIR / "jwst_stage3_footprints.parquet"


def extract_ra_dec(header) -> tuple[float, float]:
    ra_values = [
        header[key]
        for key in header
        if key.startswith("RA") and isinstance(header[key], (int, float))
    ]
    dec_values = [
        header[key]
        for key in header
        if key.startswith("DEC") and isinstance(header[key], (int, float))
    ]

    if not ra_values or not dec_values:
        return float("nan"), float("nan")

    return ra_values[0], dec_values[0]


def is_stage3_fits(filename: str) -> bool:
    return (
        STAGE3_REGEX.match(filename) is not None
        and (filename.endswith(".fits") or filename.endswith(".fits.gz"))
        and any(flt in filename for flt in JWST_FILTERS)
    )


def collect_stage3_file_paths(root_dir: str) -> tuple[list[str], int]:
    file_paths: list[str] = []
    total_files = 0

    for root, _, files in os.walk(root_dir):
        total_files += len(files)
        for filename in files:
            if is_stage3_fits(filename):
                file_paths.append(os.path.join(root, filename))

    return file_paths, total_files


def compute_footprint(file_path: str) -> dict | None:
    try:
        with fits.open(file_path) as hdul:
            header = hdul["SCI"].header
            wcs = WCS(header)
            footprint = wcs.calc_footprint()
            ra_cen, dec_cen = extract_ra_dec(header)

        return {
            "file_path": file_path,
            "RA": ra_cen,
            "DEC": dec_cen,
            "footprint": footprint.tolist(),
        }
    except Exception as exc:
        print(f"Failed to read WCS for {file_path}: {exc}")
        return None


def write_file_paths(file_paths: list[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(file_paths, columns=["path"]).to_parquet(
        FILE_PATHS_OUTPUT,
        engine="pyarrow",
        compression="zstd",
    )


def compute_all_footprints(file_paths: list[str]) -> list[dict]:
    worker_count = max(1, cpu_count() - 1)
    with Pool(processes=worker_count) as pool:
        results = pool.map(compute_footprint, file_paths, chunksize=10)
    return [row for row in results if row is not None]


def write_footprints(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df.to_parquet(
        FOOTPRINTS_OUTPUT,
        engine="pyarrow",
        compression="zstd",
    )
    return df


def main() -> None:
    file_paths, total_files = collect_stage3_file_paths(JWST_DATALABS_PATH)
    write_file_paths(file_paths)
    print(f"Found {len(file_paths)} files. Total files in {JWST_DATALABS_PATH}: {total_files}.")

    start_time = time.time()
    footprint_rows = compute_all_footprints(file_paths)
    df = write_footprints(footprint_rows)

    print(f"Done ({time.time() - start_time:.2f} s).")
    print(f"Saved {len(df)} Stage 3 products to dataset.")


if __name__ == "__main__":
    main()
