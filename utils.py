import ast
import glob
import itertools
import json
import logging
import math
import os
import warnings
from collections import defaultdict
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import astropy.units as u
from PIL import Image
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.nddata import Cutout2D
from astropy.utils.exceptions import AstropyWarning
from astropy.visualization import ZScaleInterval
from astropy.wcs import WCS
from astroquery.esa.jwst import Jwst
from astroquery.mast import Mast
from matplotlib.path import Path as PathM
from reproject import reproject_interp
from sklearn.cluster import DBSCAN
from shapely.geometry import Point, Polygon

from constants import *

logger = logging.getLogger(__name__)
logging.getLogger("astroquery").setLevel(logging.WARNING)
warnings.simplefilter("ignore", category=AstropyWarning)


def open_fits(file_path):
    hdul = fits.open(file_path, memmap=True)
    sci = hdul["SCI"].data
    hdr = hdul["SCI"].header
    return hdul, sci, hdr


def compute_invalid_mask(data):
    finite_data = data[np.isfinite(data)]
    variance_too_small = np.var(finite_data) < 1e-6 if finite_data.size else True
    return (
        ~np.isfinite(data)
        | (data == 0)
        | variance_too_small
    )


def get_pixel_scale_arcsec_per_pixel(wcs_obj: WCS) -> float:
    try:
        pixel_scale_matrix = wcs_obj.pixel_scale_matrix
        pixel_scale_deg = np.sqrt(abs(np.linalg.det(pixel_scale_matrix)))
        return pixel_scale_deg * 3600.0
    except Exception as exc:
        logger.warning("Could not determine pixel scale from WCS, using default: %s", exc)
        return 0.1


def _resize_cutout_data(cutout_data):
    return np.array(Image.fromarray(cutout_data).resize((CUTOUT_RES, CUTOUT_RES)))


def _build_skycoord(ra, dec):
    return SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")


def create_list_one_band_cutout_w_area(
    fits_files: list,
    all_wcs: list,
    all_data: list,
    ras: list,
    decs: list,
    areas: list,
    return_new_coords=False,
    reorient=False,
):
    cutouts = {}
    min_cutout_size = float("inf")
    for wcs, area in zip(all_wcs, areas):
        radius_pixel = math.sqrt(area / math.pi)
        arcsec_per_pixel = get_pixel_scale_arcsec_per_pixel(wcs)
        cutout_size_arcsec = arcsec_per_pixel * radius_pixel * CUTOUT_FACTOR
        min_cutout_size = min(min_cutout_size, cutout_size_arcsec)

    for fits_file, wcs, data, ra, dec, area in zip(fits_files, all_wcs, all_data, ras, decs, areas):
        coord = _build_skycoord(ra, dec)
        try:
            cutout = Cutout2D(
                data,
                coord,
                min_cutout_size * u.arcsec,
                wcs=wcs,
                mode="partial",
                fill_value=np.nan,
            )
            if reorient:
                reprojected_data, footprint = reproject_interp((cutout.data, cutout.wcs), cutout.wcs)
                cutout_data = reprojected_data
            else:
                cutout_data = cutout.data

            new_x, new_y = cutout.slices_original[0].start, cutout.slices_original[1].start
            orig_cutout_size = cutout_data.shape
            data_shape = data.shape

            cutouts[fits_file] = _resize_cutout_data(cutout_data)
        except Exception as exc:
            print(f"[SKIP ⏭️] {fits_file} | RA={ra:.5f}, Dec={dec:.5f} | Exception: {exc}")
            return None
    if return_new_coords:
        return cutouts, new_x, new_y, orig_cutout_size, min_cutout_size, data_shape

    return cutouts


def create_list_one_band_cutout(
    fits_files: list,
    all_wcs: list,
    all_data: list,
    ras: list,
    decs: list,
    sizes: list,
    reorient=False,
):
    cutouts = {}
    for fits_file, wcs, data, ra, dec, size in zip(fits_files, all_wcs, all_data, ras, decs, sizes):
        coord = _build_skycoord(ra, dec)
        try:
            cutout = Cutout2D(data, coord, size * u.arcsec, wcs=wcs, mode="partial", fill_value=np.nan)
            if reorient:
                reprojected_data, footprint = reproject_interp((cutout.data, cutout.wcs), cutout.wcs)
                cutout_data = reprojected_data
            else:
                cutout_data = cutout.data
        except Exception as exc:
            print(f"[SKIP ⏭️] Exception: {exc} (the coord is outside the footprint?)")
            continue

        cutouts[fits_file] = _resize_cutout_data(cutout_data)
        cutouts["object"] = cutout
        cutouts["orig_shape"] = cutout_data.shape

    return cutouts


def get_footprint_polygon(fits_file):
    with fits.open(fits_file) as hdul:
        header = hdul["SCI"].header
        wcs = WCS(header)
        footprint = wcs.calc_footprint()
    return Polygon(footprint)


def check_all_intersections(fits_files):
    footprints = {f: get_footprint_polygon(f) for f in fits_files}
    results = []
    for f1, f2 in itertools.combinations(fits_files, 2):
        inter = footprints[f1].intersects(footprints[f2])
        results.append((f1, f2, inter))
    return results

def extract_prod_type_from_filters(filename):
    match = []
    for flt in JWST_FILTERS:
        if flt in filename:
            match = filename.split(flt)[0]
            break
    return match if match else None


def extract_filter_from_file(filename):
    for flt in JWST_FILTERS:
        if flt in filename:
            return flt
    return None


def angular_separation(ra1_deg, dec1_deg, ra2_deg, dec2_deg):
    ra1, dec1 = math.radians(ra1_deg), math.radians(dec1_deg)
    ra2, dec2 = math.radians(ra2_deg), math.radians(dec2_deg)
    delta_ra = ra2 - ra1
    delta_dec = dec2 - dec1
    a = math.sin(delta_dec / 2) ** 2 + math.cos(dec1) * math.cos(dec2) * math.sin(delta_ra / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return math.degrees(c) * 3600


def is_within_arcsec(ra1, dec1, ra2, dec2, threshold_arcsec=15):
    separation = angular_separation(ra1, dec1, ra2, dec2)
    return separation <= threshold_arcsec, separation


def plot_fits_footprints(i, fits_paths, ras, decs, size_arcsec=10, title="JWST FITS Footprints"):
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.scatter(ras, decs, color="red", s=20, label="Cutout centers")

    for fits_path in fits_paths:
        with fits.open(fits_path) as hdul:
            wcs = WCS(hdul["SCI"].header)
            footprint = wcs.calc_footprint()
            footprint = np.vstack([footprint, footprint[0]])
            ax.plot(footprint[:, 0], footprint[:, 1], color="blue", label="FITS footprint")

    size_deg = size_arcsec / 3600.0
    half_size = size_deg / 2.0

    for ra, dec in zip(ras, decs):
        square_ra = [ra - half_size, ra + half_size, ra + half_size, ra - half_size, ra - half_size]
        square_dec = [dec - half_size, dec - half_size, dec + half_size, dec + half_size, dec - half_size]
        ax.plot(square_ra, square_dec, color="green", linestyle="--", label="Cutout box")

    ax.set_xlabel("RA [deg]")
    ax.set_ylabel("Dec [deg]")
    ax.set_title(title)

    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys())

    plt.grid(True)
    plt.gca().invert_xaxis()
    plt.savefig(f"{i}.png", dpi=300, bbox_inches="tight")
    plt.show()
    plt.close()


def make_mtf_rgb(f115, f150, f277, f444, means=[0.27, 0.25, 0.23, 0.25]) -> np.array:
    mtf_args = {"central_crop_fraction": 1.0, "percentile": 99.85}
    f115_mtf = apply_MTF(f115, **mtf_args, desired_mean_normalized=means[0])
    f150_mtf = apply_MTF(f150, **mtf_args, desired_mean_normalized=means[1])
    f277_mtf = apply_MTF(f277, **mtf_args, desired_mean_normalized=means[2])
    f444_mtf = apply_MTF(f444, **mtf_args, desired_mean_normalized=means[3])

    weights = {
        "f115w": (0, 0, 0.7),
        "f150w": (0, 0.5, 0.3),
        "f277w": (0.3, 0.5, 0),
        "f444w": (0.7, 0, 0),
    }

    red = f115_mtf * weights["f115w"][0] + f150_mtf * weights["f150w"][0] + f277_mtf * weights["f277w"][0] + f444_mtf * weights["f444w"][0]
    green = f115_mtf * weights["f115w"][1] + f150_mtf * weights["f150w"][1] + f277_mtf * weights["f277w"][1] + f444_mtf * weights["f444w"][1]
    blue = f115_mtf * weights["f115w"][2] + f150_mtf * weights["f150w"][2] + f277_mtf * weights["f277w"][2] + f444_mtf * weights["f444w"][2]
    rgb = np.stack([red, green, blue], axis=2)
    return rgb


def apply_MTF(image_data, desired_mean_normalized=0.2, central_crop_size=100, central_crop_fraction=None, quick_mask=False, percentile=99.5):
    image_data = np.nan_to_num(image_data, nan=0.0, posinf=0.0, neginf=0.0)
    valid_mask = ~np.isnan(image_data) & (image_data > 0)

    if percentile is not None:
        image_data = np.clip(image_data, image_data.min(), np.percentile(image_data, percentile))

    normalized_data = np.zeros_like(image_data, dtype=np.float64)
    if np.any(valid_mask):
        min_val = np.min(image_data[valid_mask])
        max_val = np.max(image_data[valid_mask])
        normalized_data[valid_mask] = (image_data[valid_mask] - min_val) / (max_val - min_val)

    m = find_m_for_mean(normalized_data, desired_mean_normalized, central_crop_size, central_crop_fraction, quick_mask)
    transformed_data = MTF_on_normalised_data(normalized_data, m)
    transformed_image_data = (transformed_data * 255).astype(np.uint8)
    return transformed_image_data


def find_m_for_mean(normalized_data, desired_mean, central_crop_size=100, central_crop_fraction=None, quick_mask=False):
    width = normalized_data.shape[1]
    if quick_mask:
        normalized_data_selected = make_quick_mask(normalized_data)
    else:
        if central_crop_fraction is not None:
            central_crop_size = int(central_crop_fraction * width)

        central_crop_low_edge = width//2 - central_crop_size//2
        central_crop_high_edge = width//2 + central_crop_size//2
        normalized_data_selected = normalized_data[central_crop_low_edge:central_crop_high_edge, central_crop_low_edge:central_crop_high_edge]

    x = np.mean(normalized_data_selected)
    alpha = desired_mean
    return (x - alpha * x) / (x - 2 * alpha * x + alpha)


def MTF_on_normalised_data(x, m):
    """Compute the Midtones Transfer Function for normalized data."""
    if x.max() > 1 or x.min() < 0:
        print(x)
    assert x.max() <= 1
    assert x.min() >= 0
    y = np.zeros_like(x)
    mask0 = (x == 0)
    maskm = (x == m)
    mask1 = (x == 1)
    mask_else = ~(mask0 | maskm | mask1)
    y[mask0] = 0
    y[maskm] = 0.5
    y[mask1] = 1
    x_else = x[mask_else]
    numerator = (m - 1) * x_else
    denominator = (2 * m - 1) * x_else - m
    y[mask_else] = numerator / denominator
    return y


def make_quick_mask(normalized_data):
    return normalized_data[normalized_data > 0]


def parse_spoly_to_polygon(spoly_string):
    parts = spoly_string.strip().split()
    if len(parts) == 0 or parts[0].lower() != "polygon":
        return []
    coords = parts[1:]
    if len(coords) % 2 != 0:
        raise ValueError("Invalid polygon string, odd number of coordinates")
    polygon = [(float(coords[i]), float(coords[i+1])) for i in range(0, len(coords), 2)]
    return polygon


def cluster_sources_by_radius(df, radius_arcsec=30.0, ra_col="RA", dec_col="DEC", cluster_col="cluster_id"):
    clustered_df = df.copy()
    coords = SkyCoord(clustered_df[ra_col].to_numpy() * u.deg, clustered_df[dec_col].to_numpy() * u.deg)
    features = np.vstack([coords.ra.radian, coords.dec.radian]).T
    eps_rad = (radius_arcsec * u.arcsec).to(u.rad).value
    clustered_df[cluster_col] = DBSCAN(
        eps=eps_rad,
        min_samples=1,
        metric="euclidean",
    ).fit_predict(features)
    return clustered_df


def get_duplicate_cluster_ids(df, cluster_col="cluster_id"):
    cluster_sizes = df[cluster_col].value_counts()
    return sorted(cluster_sizes.index[cluster_sizes > 1].tolist())


def read_any_image(path):
    path = Path(path)
    suffixes = "".join(path.suffixes).lower()
    if suffixes.endswith(".fits") or suffixes.endswith(".fits.gz"):
        fits_like = True
    else:
        fits_like = False

    if not fits_like:
        return np.asarray(Image.open(path))

    with fits.open(path) as hdul:
        if "SCI" in hdul:
            data = hdul["SCI"].data
        else:
            hdu = next((h for h in hdul if getattr(h, "data", None) is not None and np.ndim(h.data) >= 2), None)
            if hdu is None:
                raise ValueError(f"No 2D image in {path}")
            data = hdu.data
        data = np.asarray(data).squeeze()
        if data.ndim > 2:
            data = data[0]

    zscale = ZScaleInterval()
    vmin, vmax = zscale.get_limits(data)
    return data, vmin, vmax


# Not used anymore (will keep it here for potential use)
def plot_duplicate_lens_clusters(
    df,
    base_dir=".",
    outdir="cluster_panels",
    radius_arcsec=30.0,
    filename_col="filename",
    cluster_col="cluster_id",
):
    outdir = Path(outdir)
    outdir.mkdir(exist_ok=True)
    base_dir = Path(base_dir)

    multi_ids = get_duplicate_cluster_ids(df, cluster_col=cluster_col)
    saved_paths = []

    for cluster_id in multi_ids:
        rows = df[df[cluster_col] == cluster_id].reset_index(drop=True)
        n_members = len(rows)
        ncols = min(5, n_members)
        nrows = math.ceil(n_members / ncols)
        fig, axes = plt.subplots(nrows, ncols, figsize=(3 * ncols, 3 * nrows))
        axes = np.atleast_2d(axes)

        for i, row in rows.iterrows():
            r_idx, c_idx = divmod(i, ncols)
            ax = axes[r_idx, c_idx]
            image_path = Path(row.get(filename_col))

            try:
                if not image_path.is_absolute():
                    image_path = base_dir / image_path
                img = read_any_image(image_path)
                if isinstance(img, tuple):
                    data, vmin, vmax = img
                    ax.imshow(data, origin="lower", cmap="gray", vmin=vmin, vmax=vmax)
                else:
                    ax.imshow(img, origin="lower")
                ax.set_title(str(i), fontsize=8)
            except Exception as exc:
                ax.text(
                    0.5,
                    0.5,
                    f"Failed:\n{image_path.name}\n{exc}",
                    ha="center",
                    va="center",
                    fontsize=7,
                )
            ax.set_axis_off()

        for blank_idx in range(n_members, nrows * ncols):
            r_idx, c_idx = divmod(blank_idx, ncols)
            axes[r_idx, c_idx].set_visible(False)

        fig.suptitle(f"Cluster {cluster_id} - {n_members} members (<={radius_arcsec}\")", y=0.98, fontsize=12)
        fig.tight_layout()
        output_path = outdir / f"cluster_{cluster_id}.png"
        fig.savefig(output_path, dpi=150)
        plt.close(fig)
        saved_paths.append(output_path)

    return saved_paths

def point_in_spoly(ra, dec, spoly_string):
    polygon = parse_spoly_to_polygon(spoly_string)
    if not polygon:
        return False
    path = PathM(polygon)
    return path.contains_point((ra, dec))

def cross_match_astrodeep_with_jwst(astrodeep_ras,
                                    astrodeep_decs,
                                    jwst_datalabs_vol_path, 
                                    stage3_regex, 
                                    n_sources_to_search, 
                                    radius, 
                                    output_path,
                                    filters):
    print('Cross-matching ASTRODEEP catalogue with Datalabs JWST stage-3 products...')
    results_df = pd.DataFrame(columns=['RA', 'DEC', 'Filter', 'Product'])
    for ra, dec in zip(astrodeep_ras[:n_sources_to_search], astrodeep_decs[:n_sources_to_search]):
        coord = SkyCoord(ra=ra, dec=dec, unit=(u.degree, u.degree), frame='icrs')
        
        j = Jwst.cone_search(coordinate=coord, radius=radius, async_job=False) 
        result_ = j.get_results()
        result = result_[
            (result_['instrument_name'] == 'NIRCAM/IMAGE') &
            (result_['dataproducttype'] == 'image') &
            (result_['calibrationlevel'] == 3)
        ]
        
        
        poly_col = result['position_bounds_spoly']
        is_contained = False

        for i, spoly_entry in enumerate(poly_col):
            if poly_col.mask[i]:
                print(f"Row {i} is masked (no polygon)")
                continue

            spoly_string = spoly_entry  # should be a string
            polygon = parse_spoly_to_polygon(spoly_string)
            if point_in_spoly(ra, dec, spoly_string):
                is_contained = True
                
        if not is_contained:
            print(f"[SKIP] Point is NOT inside a polygon at row {i}.")
            continue

        if result and len(result) > 0:
            for i in range(len(result)):
                obs_id = result['observationid'][i]
                visit_number = obs_id[:7]  # 'jw12345'
                visit_path_datalabs = os.path.join(
                    jwst_datalabs_vol_path,
                    f'jwst_{visit_number[:4]}',
                    f'{visit_number}'
                )

                if not os.path.exists(visit_path_datalabs):
                    print(f"📁 Path does not exist: {visit_path_datalabs}")
                    continue

                src_prods_DL = glob.glob(f'{visit_path_datalabs}/*.fits*', recursive=True)

                # Check for stage 3 products
                s3_products = [
                    fname for fname in src_prods_DL
                    if stage3_regex.match(os.path.basename(fname)) and obs_id in fname
                ]
                if not s3_products:
                    print("NO stage 3 prods.")

                if s3_products:
                    for flt in JWST_FILTERS:
                        if flt in obs_id:
                            print('JWST MAST RA:', result['target_ra'][i], 'DEC:', result['target_dec'][i], 'query ra:', ra, 'dec:', dec)
                            flt_stage3_products = [
                                prod for prod in s3_products if flt.lower() in os.path.basename(prod).lower()
                            ]
                            print(f'🚀 Found stage 3 products for RA={ra}, DEC={dec}, filter {flt}.')
                            for prod in flt_stage3_products:
                                new_row = pd.DataFrame({
                                    "RA": [ra],
                                    "DEC": [dec],
                                    "Filter": [flt],
                                    "Product": os.path.basename(prod),
                                    "Target_name": result[i]['target_name']
                                    
                                })
                                results_df = pd.concat([results_df, new_row], ignore_index=True)
                                
    if not results_df.empty:
        results_df.to_csv(output_path)
        print(f"\n💾 Saved {len(results_df)} matching entries to {output_path}.")
        return results_df
    else:
        print("‼️ No stage 3 products found.")
            
    print('✅ Done.')
    
def extract_ra_dec(header):
    ra_keywords = {k: v for k, v in header.items() if k.upper().startswith('RA')}
    dec_keywords = {k: v for k, v in header.items() if k.upper().startswith('DEC')}

    return ra_keywords, dec_keywords

def _to_deg(ra, dec):
    """
    Accepts RA/DEC as floats (deg) or sexagesimal strings.
    Returns (ra_deg, dec_deg) as floats.
    """
    # if either is a string → let SkyCoord parse with hourangle/deg
    if isinstance(ra, str) or isinstance(dec, str):
        c = SkyCoord(ra=ra, dec=dec, unit=(u.hourangle, u.deg), frame="icrs")
        return float(c.ra.deg), float(c.dec.deg)
    
    # assume degrees
    return float(ra), float(dec)

def combined_rgb_cutout(
    file_paths: list[str],          # List of paths to FITS files (4 bands: F115W, F150W, F277W, F444W)
    ra: float | str,                # Right Ascension of target (in degrees or sexagesimal string, will be converted to deg)
    dec: float | str,               # Declination of target (in degrees or sexagesimal string, will be converted to deg)
    path_to_save: str,              # File path where the resulting RGB PNG will be saved
    plot_rgb: bool = True,          # If True, display the combined RGB cutout with matplotlib
    plot_bands: bool = False,       # If True, also plot the 4 individual band cutouts (F115W, F150W, F277W, F444W)
    area: float | None = None,      # Segmentation area (pixels^2), if provided will set cutout size instead of size_arcsec
    wcs_list: list | None = None,   # Optional precomputed WCS objects for the FITS files
    data_list: list | None = None,  # Optional preloaded image data arrays for the FITS files
    size_arcsec: float = 15,        # Cutout size in arcseconds (used if area is None)
    return_components: bool = False,# If True, return both the RGB image and the per-band cutouts
    orient_cutout: bool = False     # If True, reorient cutout to north-up, east-left using WCS
):

    ra, dec = _to_deg(ra, dec)
    
    ras = [ra] * len(file_paths)
    decs = [dec] * len(file_paths)
    if area is not None:
        areas = [area] * len(file_paths)
        
    if (wcs_list is None) or (data_list is None):
        wcs_list, data_list = [], []
        for fits_file in file_paths:
            with fits.open(fits_file) as hdul:
                data = hdul["SCI"].data
                header = hdul["SCI"].header
            wcs_list.append(WCS(header))
            data_list.append(data)

    if len(wcs_list) != len(file_paths) or len(data_list) != len(file_paths):
        raise ValueError("wcs_list and data_list must align with file_paths in length.")
    if area is not None:        
        cutouts, cutout_info = create_list_one_band_cutout_w_area(file_paths, ras, decs, areas, orient_cutout)
    else:
        sizes = [size_arcsec] * len(file_paths)
        cutouts = create_list_one_band_cutout(file_paths, wcs_list, data_list, ras, decs, sizes, orient_cutout)
        
    rgb_mtf = make_mtf_rgb(cutouts[file_paths[0]], cutouts[file_paths[1]], cutouts[file_paths[2]], cutouts[file_paths[3]]).astype(np.uint8)
    if rgb_mtf is not None:
        cv2.imwrite(path_to_save, cv2.cvtColor(rgb_mtf, cv2.COLOR_RGB2BGR))
        
    try:
        plt.imshow(rgb_mtf, origin="lower")
        plt.show()
        plt.close()

        if plot_bands:
            fig, axs = plt.subplots(1, 4, figsize=(12, 3))
            bands = [("F115W", f115), ("F150W", f150), ("F277W", f277), ("F444W", f444)]
            for ax, (name, arr) in zip(axs, bands):
                im = ax.imshow(arr, origin="lower")
                ax.set_title(name)
                ax.axis("off")
            fig.colorbar(im, ax=axs.ravel().tolist(), shrink=0.75)
            plt.suptitle("Per-band cutouts")
            plt.tight_layout()
            plt.show()
    except Exception as _plot_err:
        pass
                    
    return (rgb_mtf, cutouts)

def check_coord_in_df(
    ra,
    dec,
    df,
    max_sep_arcsec=1.0,
    ra_col="RA",
    dec_col="DEC"
):
   
    ra, dec = _to_deg(ra, dec)
    target = SkyCoord(ra=float(ra)*u.deg, dec=float(dec)*u.deg, frame="icrs")
    
    catalog = SkyCoord(
        ra=df[ra_col].to_numpy(dtype=float) * u.deg,
        dec=df[dec_col].to_numpy(dtype=float) * u.deg,
        frame="icrs",
    )

    seps = target.separation(catalog).arcsec
    matches = df.loc[seps <= max_sep_arcsec].copy()
    min_sep = np.min(seps) if len(seps) > 0 else np.inf
    
    if len(matches):
        print(f'Found {len(matches)} match, with min separation dist: {min_sep}.')
        return (matches['file_path'].tolist(), matches[ra_col].tolist(), matches[dec_col].tolist(), matches['astrodeep_obs_ID'].tolist()), float(min_sep)
    else:
        print(f'Coord {ra}, {dec} did not match any entry.')
        return (None, None, None), None

def find_lenses_in_footprints(lens_coords, df_fp, areas=None):
    matching_rows = []

    for idx_lens, (ra_lens, dec_lens) in enumerate(zip(lens_coords[0], lens_coords[1])):
        point = Point(ra_lens, dec_lens)
        best_dist = float('inf')
        best_path = None
        pattern = '|'.join(JWST_FILTERS) 

        for idx, row in df_fp[df_fp['file_path'].str.contains(pattern, case=False, na=False)].iterrows():
            poly = row['polygon']

            if poly.contains(point):
                centroid = poly.centroid
                _, dist = is_within_arcsec(centroid.x, centroid.y, ra_lens, dec_lens)

                if dist < best_dist:
                    best_dist = dist
                    best_path = row['file_path']
                if areas is not None:
                    matching_rows.append({
                        'RA': ra_lens,
                        'DEC': dec_lens,
                        'Area': areas[idx_lens],
                        'file_path': row['file_path'],
                        'best_path': best_path,

                    })
                else:
                    matching_rows.append({
                        'RA': ra_lens,
                        'DEC': dec_lens,
                        'file_path': row['file_path'],
                        'best_path': best_path,

                    })
                    
    return pd.DataFrame(matching_rows)

def add_jwst_sizes(q_col=None,       
                   pixscale=0.031,    
                   psf_fwhm=0.07):   
    """
    Add JWST pixel sizes and areas to a DataFrame given GALFIT effective radii in arcsec.
    
    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame containing a column with effective radius (arcsec).
    re_col : str
        Name of the column with effective radius (arcsec).
    q_col : str or None
        Optional column with axis ratio b/a (for elliptical area).
    pixscale : float
        JWST pixel scale in arcsec/pixel (0.031 for SW, 0.063 for LW).
    psf_fwhm : float
        PSF FWHM in arcsec (0.07 for SW, 0.14 for LW).
    
    Returns
    -------
    df_out : pandas.DataFrame
        Copy of the DataFrame with added columns:
        - re_arcsec_clipped : arcsec radius after PSF floor
        - re_pix : effective radius in pixels
        - area_circ_pix : circular area (pixels^2)
        - area_ell_pix : elliptical area (pixels^2) if q_col is provided
    """
    df = df.copy()

    # Apply PSF floor in arcsec
    df["re_arcsec_clipped"] = np.maximum(df[re_col], psf_fwhm)

    df["re_pix"] = df["re_arcsec_clipped"] / pixscale

    df["area_circ_pix"] = np.pi * df["re_pix"]**2

    # Elliptical area (π r^2 q), if axis ratio provided
    if q_col is not None and q_col in df.columns:
        df["area_ell_pix"] = np.pi * df["re_pix"]**2 * df[q_col]

    return df

def re_to_area_pix(paths:list, re:list):
    areas = []
    for fp in paths:
        if re < 5000:
            pix_res = JWST_OPT_RES_NIRCam_SHORT if 'f115' in fp or 'f150' in fp else JWST_OPT_RES_NIRCam_LONG
            areas.append((re/pix_res)**2 * math.pi)
        else:
            areas.append(re)
    print('Size', areas)
    return areas
