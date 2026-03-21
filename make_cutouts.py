import argparse
import os
import time
from pathlib import Path

import pandas as pd
from astropy.io import fits
from astropy.wcs import WCS

from constants import CUTOUT_FACTOR, JWST_FILTERS, MIN_CUTOUT_SIZE
from utils import create_list_one_band_cutout_w_area, make_mtf_rgb, np, cv2

REPO_ROOT = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "DATA"


def build_parser():
    parser = argparse.ArgumentParser(description="Create JWST cutouts for one catalogue.")
    parser.add_argument(
        "--catalogue",
        default="astrodeep",
        choices=["astrodeep", "cosmos"],
        help="Catalogue to process.",
    )
    parser.add_argument(
        "--matches",
        default=None,
        help="Input parquet for footprint matches. Defaults to DATA/<catalogue>_footprint_matches.parquet.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output parquet path. Defaults to DATA/<catalogue>_cutouts_df.parquet.",
    )
    parser.add_argument(
        "--image-dir",
        default=str(DATA_DIR / "temp_all_lenses"),
        help="Directory where PNG cutouts are written.",
    )
    return parser


def summarize_input(matches_df: pd.DataFrame, catalogue: str) -> None:
    print(f"[{catalogue}] Input rows: {len(matches_df)}")
    print(f"[{catalogue}] Unique JWST file paths: {matches_df['file_path'].nunique()}")
    if "RA" in matches_df and "DEC" in matches_df:
        print(
            f"[{catalogue}] RA range: {matches_df['RA'].min():.6f} .. {matches_df['RA'].max():.6f}"
        )
        print(
            f"[{catalogue}] DEC range: {matches_df['DEC'].min():.6f} .. {matches_df['DEC'].max():.6f}"
        )
    if "seg_area" in matches_df:
        print(
            f"[{catalogue}] seg_area min/max/median: "
            f"{matches_df['seg_area'].min():.4f} / {matches_df['seg_area'].max():.4f} / {matches_df['seg_area'].median():.4f}"
        )


def summarize_output(results_df: pd.DataFrame, matches_df: pd.DataFrame, catalogue: str) -> None:
    print(f"[{catalogue}] Output rows before save: {len(results_df)}")
    print(f"[{catalogue}] Output columns: {list(results_df.columns)}")
    if not results_df.empty:
        print(
            f"[{catalogue}] Output RA range: {results_df['RA'].min():.6f} .. {results_df['RA'].max():.6f}"
        )
        print(
            f"[{catalogue}] Output DEC range: {results_df['DEC'].min():.6f} .. {results_df['DEC'].max():.6f}"
        )
        print(f"[{catalogue}] Unique output file paths: {results_df['file_path'].nunique()}")
        print(f"[{catalogue}] Catalogue values: {sorted(results_df['CATALOGUE'].unique().tolist())}")

    if "radius_pixels" in matches_df:
        print(
            f"[{catalogue}] radius_pixels min/max/median: "
            f"{matches_df['radius_pixels'].min():.4f} / {matches_df['radius_pixels'].max():.4f} / {matches_df['radius_pixels'].median():.4f}"
        )
    if "cutout_size_px" in matches_df:
        print(
            f"[{catalogue}] cutout_size_px min/max/median: "
            f"{matches_df['cutout_size_px'].min():.4f} / {matches_df['cutout_size_px'].max():.4f} / {matches_df['cutout_size_px'].median():.4f}"
        )


def run_make_cutouts(catalogue: str, matches_path: str | None = None, output_path: str | None = None, image_dir: str | None = None) -> pd.DataFrame:
    matches_path = matches_path or str(DATA_DIR / f"{catalogue}_footprint_matches.parquet")
    output_path = output_path or str(DATA_DIR / f"{catalogue}_cutouts_df.parquet")
    image_dir = image_dir or str(DATA_DIR / "temp_all_lenses")

    matches_df = pd.read_parquet(matches_path)
    summarize_input(matches_df, catalogue)

    matches_df["radius_pixels"] = np.sqrt(matches_df["seg_area"] / np.pi)
    matches_df["cutout_size_px"] = matches_df["radius_pixels"] * CUTOUT_FACTOR
    matches_df = matches_df[matches_df["cutout_size_px"] >= MIN_CUTOUT_SIZE].copy()
    matches_df.sort_values(by=["seg_area"], ascending=[False], inplace=True)

    print(f"[{catalogue}] Rows after minimum cutout-size filter: {len(matches_df)}")
    os.makedirs(image_dir, exist_ok=True)

    start_time = time.perf_counter()
    results = []

    n_groups = 0
    n_candidates = 0
    n_bad_cutout = 0
    n_not_all_filters_ok = 0
    n_flt_exception = 0

    for group_name, group_df in matches_df.groupby(["file_path"]):
        n_groups += 1
        file_path = group_name[0]
        matching_filters = [flt for flt in JWST_FILTERS if flt in file_path]
        if not matching_filters:
            continue

        file_flt = matching_filters[0]
        prod_type = file_path.split(file_flt)[0]
        all_prod_type_paths = [
            file_path.replace(file_flt, other_flt)
            for other_flt in JWST_FILTERS
            if os.path.isfile(file_path.replace(file_flt, other_flt))
        ]

        if len(all_prod_type_paths) < len(JWST_FILTERS):
            continue

        all_prod_type_wcs = []
        all_prod_type_fits_data = []
        for fits_file in all_prod_type_paths:
            with fits.open(fits_file) as hdul:
                data = hdul["SCI"].data
                header = hdul["SCI"].header
            all_prod_type_wcs.append(WCS(header))
            all_prod_type_fits_data.append(data)

        for _, row in group_df.iterrows():
            n_candidates += 1
            ra, dec = row["RA"], row["DEC"]
            path_to_save = os.path.join(
                image_dir,
                f"{catalogue}_{prod_type.split('/')[-1]}{ra}-{dec}.png",
            )

            cutout = create_list_one_band_cutout_w_area(
                all_prod_type_paths,
                all_prod_type_wcs,
                all_prod_type_fits_data,
                [ra] * len(all_prod_type_paths),
                [dec] * len(all_prod_type_paths),
                areas=[row["seg_area"]] * len(all_prod_type_paths),
            )

            if not cutout:
                n_bad_cutout += 1
                continue

            f115 = next((v for k, v in cutout.items() if "f115" in k), None)
            f150 = next((v for k, v in cutout.items() if "f150" in k), None)
            f277 = next((v for k, v in cutout.items() if "f277" in k), None)
            f444 = next((v for k, v in cutout.items() if "f444" in k), None)

            if any(arr is None for arr in (f115, f150, f277, f444)):
                n_not_all_filters_ok += 1
                continue

            try:
                rgb_mtf = make_mtf_rgb(f115, f150, f277, f444).astype(np.uint8)
                cv2.imwrite(path_to_save, cv2.cvtColor(rgb_mtf, cv2.COLOR_BGR2RGB))
                results.append(
                    {
                        "file_path": path_to_save,
                        "RA": ra,
                        "DEC": dec,
                        "CATALOGUE": catalogue,
                    }
                )
            except Exception as exc:
                n_flt_exception += 1
                print(f"[{catalogue}] Exception while writing cutout: {exc}")

        del all_prod_type_wcs
        del all_prod_type_fits_data

    elapsed = time.perf_counter() - start_time
    results_df = pd.DataFrame(results)

    print(f"[{catalogue}] n_groups: {n_groups}")
    print(f"[{catalogue}] n_candidates: {n_candidates}")
    print(f"[{catalogue}] n_bad_cutout: {n_bad_cutout}")
    print(f"[{catalogue}] n_not_all_filters_ok: {n_not_all_filters_ok}")
    print(f"[{catalogue}] n_flt_exception: {n_flt_exception}")
    print(f"[{catalogue}] Successful cutouts: {len(results_df)}")
    print(f"[{catalogue}] Elapsed seconds: {elapsed:.2f}")

    summarize_output(results_df, matches_df, catalogue)
    print(f"[{catalogue}] Writing parquet to {output_path}")
    results_df.to_parquet(output_path, engine="pyarrow", compression="zstd")
    print(f"[{catalogue}] Done.")

    return results_df


def main():
    args = build_parser().parse_args()
    run_make_cutouts(
        catalogue=args.catalogue,
        matches_path=args.matches,
        output_path=args.output,
        image_dir=args.image_dir,
    )


if __name__ == "__main__":
    main()
