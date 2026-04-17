import argparse
import os
import time
from pathlib import Path

import pandas as pd
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree

from constants import JWST_FILTERS
from utils import compute_invalid_mask, is_within_arcsec, u

REPO_ROOT = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "DATA"

ASTRODEEP_FILE = "/media/home/team_workspaces/AnomalyMatch-JWST-Lenses/astrodeep-source-catalogue/ASTRODEEP-JWST_optap.csv"
COSMOS_OBS_FILE = "/media/home/team_workspaces/AnomalyMatch-JWST-Lenses/COSMOS-source-catalogue/cosmos_observations.csv"
COSMOS_FILE = "/media/home/team_workspaces/AnomalyMatch-JWST-Lenses/COSMOS-source-catalogue/cosmos_catalog.csv"


def build_parser():
    parser = argparse.ArgumentParser(description="Match source catalogues to JWST Datalabs footprints.")
    parser.add_argument(
        "--catalogue",
        default="all",
        choices=["all", "astrodeep", "cosmos"],
        help="Catalogue to process. Defaults to both, in astrodeep then cosmos order.",
    )
    parser.add_argument(
        "--footprints",
        default=str(DATA_DIR / "jwst_stage3_footprints.parquet"),
        help="Input parquet containing JWST stage-3 footprints.",
    )
    return parser


def pointing_key(path: str) -> str:
    key = path
    for flt in JWST_FILTERS:
        key = key.replace(flt, "FILTER")
    return key


def check_if_all_filters_exist(file_path: str) -> bool:
    first_filter = next((flt for flt in JWST_FILTERS if flt in file_path), None)
    if first_filter is None:
        return False
    return all(os.path.exists(file_path.replace(first_filter, flt)) for flt in JWST_FILTERS)


def open_sci_fits(file_path: str):
    hdul = fits.open(file_path, memmap=True)
    sci = hdul["SCI"].data
    hdr = hdul["SCI"].header
    return hdul, sci, hdr


def load_footprints(footprints_path: str, catalogue: str) -> pd.DataFrame:
    footprints_df = pd.read_parquet(footprints_path)
    print(f"[{catalogue}] Footprint rows loaded: {len(footprints_df)}")

    required_columns = {"file_path", "footprint"}
    missing_columns = required_columns - set(footprints_df.columns)
    if missing_columns:
        raise ValueError(
            f"[{catalogue}] Footprints parquet is missing required columns: {sorted(missing_columns)}. "
            "This usually means the JWST footprint extraction step found no valid Stage 3 FITS files."
        )

    if catalogue == "cosmos":
        cosmos_obs = pd.read_csv(COSMOS_OBS_FILE)
        obs_to_keep = cosmos_obs["obs_id"].tolist()
        pattern = "|".join(obs_to_keep)
        footprints_df = footprints_df[
            footprints_df["file_path"].str.contains(pattern, case=False, na=False)
        ].copy()
        print(f"[{catalogue}] Footprint rows after COSMOS observation filter: {len(footprints_df)}")

    footprints_df["polygon"] = footprints_df["footprint"].apply(lambda fp: Polygon(fp))
    footprints_df["pointing_key"] = footprints_df["file_path"].apply(pointing_key)
    footprints_df = (
        footprints_df.groupby("pointing_key", sort=False, as_index=False)
        .first()
        .reset_index(drop=True)
    )

    print(f"[{catalogue}] Unique pointings after filter collapse: {len(footprints_df)}")
    print(f"[{catalogue}] Unique file paths: {footprints_df['file_path'].nunique()}")
    return footprints_df


def load_sources(catalogue: str) -> pd.DataFrame:
    if catalogue == "astrodeep":
        df = pd.read_csv(ASTRODEEP_FILE)
        df = df[["RA", "DEC", "ID", "isoarea_SE"]].copy()
        df["seg_area"] = df["isoarea_SE"]
        df.drop(columns=["isoarea_SE"], inplace=True)
    elif catalogue == "cosmos":
        df = pd.read_csv(COSMOS_FILE)
    else:
        raise ValueError("catalogue must be 'astrodeep' or 'cosmos'")

    print(f"[{catalogue}] Source rows loaded: {len(df)}")
    print(f"[{catalogue}] Source RA range: {df['RA'].min():.6f} .. {df['RA'].max():.6f}")
    print(f"[{catalogue}] Source DEC range: {df['DEC'].min():.6f} .. {df['DEC'].max():.6f}")
    if "seg_area" in df:
        print(
            f"[{catalogue}] seg_area min/max/median: "
            f"{df['seg_area'].min():.4f} / {df['seg_area'].max():.4f} / {df['seg_area'].median():.4f}"
        )
    return df


def summarize_output(catalogue: str, out_df: pd.DataFrame, elapsed: float, skipped_missing_filters: int, opened_fits_failures: int) -> None:
    print(f"[{catalogue}] Matched rows before save: {len(out_df)}")
    print(f"[{catalogue}] Skipped footprints missing one or more filters: {skipped_missing_filters}")
    print(f"[{catalogue}] FITS open/mask failures: {opened_fits_failures}")
    print(f"[{catalogue}] Elapsed seconds: {elapsed:.2f}")
    if out_df.empty:
        return

    print(f"[{catalogue}] Output columns: {list(out_df.columns)}")
    print(f"[{catalogue}] Output RA range: {out_df['RA'].min():.6f} .. {out_df['RA'].max():.6f}")
    print(f"[{catalogue}] Output DEC range: {out_df['DEC'].min():.6f} .. {out_df['DEC'].max():.6f}")
    print(f"[{catalogue}] Matched JWST file paths: {out_df['file_path'].nunique()}")
    if "seg_area" in out_df:
        print(
            f"[{catalogue}] Output seg_area min/max/median: "
            f"{out_df['seg_area'].min():.4f} / {out_df['seg_area'].max():.4f} / {out_df['seg_area'].median():.4f}"
        )


def run_matching(catalogue: str, footprints_path: str) -> pd.DataFrame:
    footprints_df = load_footprints(footprints_path, catalogue)
    source_df = load_sources(catalogue)

    if footprints_df.empty:
        print(f"[{catalogue}] No footprints available after filtering. Writing empty output.")
        out_df = pd.DataFrame(columns=list(source_df.columns) + ["file_path"])
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out_file = DATA_DIR / f"{catalogue}_footprint_matches.parquet"
        out_df.to_parquet(out_file, engine="pyarrow", compression="zstd")
        return out_df

    points = [Point(ra, dec) for ra, dec in zip(source_df["RA"], source_df["DEC"])]
    tree = STRtree(points)

    best: dict[int, dict[str, float | int]] = {}
    skipped_missing_filters = 0
    opened_fits_failures = 0
    start = time.perf_counter()

    for idx, row in footprints_df.iterrows():
        file_path = row["file_path"]
        polygon = row["polygon"]

        if not check_if_all_filters_exist(file_path):
            skipped_missing_filters += 1
            continue

        candidate_indices = tree.query(polygon)
        covered_source_indices = [source_idx for source_idx in candidate_indices if polygon.covers(points[source_idx])]
        if not covered_source_indices:
            continue

        try:
            hdul, sci, hdr = open_sci_fits(file_path)
            wcs = WCS(hdr)
            bad_mask = compute_invalid_mask(sci)
        except Exception as exc:
            opened_fits_failures += 1
            print(f"[{catalogue}] Exception while opening {file_path}: {exc}")
            continue

        centroid = polygon.centroid
        cen_ra, cen_dec = centroid.x, centroid.y

        for source_idx in covered_source_indices:
            ra = float(source_df.at[source_idx, "RA"])
            dec = float(source_df.at[source_idx, "DEC"])

            x, y = wcs.world_to_pixel(SkyCoord(ra=ra * u.deg, dec=dec * u.deg))
            x, y = int(x), int(y)
            if not (0 <= y < sci.shape[0] and 0 <= x < sci.shape[1]):
                continue
            if bad_mask[y, x]:
                continue

            _, distance_arcsec = is_within_arcsec(cen_ra, cen_dec, ra, dec)
            previous = best.get(source_idx)
            if previous is None or distance_arcsec < previous["dist"]:
                best[source_idx] = {"dist": distance_arcsec, "fp_idx": idx}

        hdul.close()

    rows = []
    for source_idx, idx_dict in best.items():
        row = source_df.iloc[source_idx].copy()
        row["file_path"] = footprints_df.iloc[idx_dict["fp_idx"]]["file_path"]
        rows.append(row)

    out_df = pd.DataFrame(rows)
    elapsed = time.perf_counter() - start
    summarize_output(catalogue, out_df, elapsed, skipped_missing_filters, opened_fits_failures)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_file = DATA_DIR / f"{catalogue}_footprint_matches.parquet"
    print(f"[{catalogue}] Writing parquet to {out_file}")
    out_df.to_parquet(out_file, engine="pyarrow", compression="zstd")
    print(f"[{catalogue}] Done.")
    return out_df


def main():
    args = build_parser().parse_args()
    catalogues = ["astrodeep", "cosmos"] if args.catalogue == "all" else [args.catalogue]

    total_start = time.perf_counter()
    for catalogue in catalogues:
        print(f"Starting {catalogue}")
        catalogue_start = time.perf_counter()
        run_matching(catalogue, args.footprints)
        print(f"Finished {catalogue} in {time.perf_counter() - catalogue_start:.2f} seconds")

    print(f"Total elapsed seconds: {time.perf_counter() - total_start:.2f}")


if __name__ == "__main__":
    main()
