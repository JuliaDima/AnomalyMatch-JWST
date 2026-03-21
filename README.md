## Table of Contents

- [Setup](#setup)
- [Code](#code)
  - [Core Scripts](#core-scripts)
  - [Supporting Files](#supporting-files)
  - [Model Development](#model-development)
- [Data](#data)
  - [`lenses_confirmed.csv`](#lenses_confirmedcsv)
  - [`jwst_stage3_footprints.parquet`](#jwst_stage3_footprintsparquet)
  - [`astrodeep_footprint_matches.parquet`](#astrodeep_footprint_matchesparquet)
  - [`cosmos_footprint_matches.parquet`](#cosmos_footprint_matchesparquet)
  - [`cutouts_df.parquet`](#cutouts_dfparquet)
- [Model](#model)

# Setup

This repository is a JWST-specific application layer built on top of [AnomalyMatch](https://github.com/esa/AnomalyMatch). Install AnomalyMatch as a regular dependency first, then install the extra packages required by this repo.

Create and activate an environment:

```bash
conda create -n am-jwst python=3.11
conda activate am-jwst
pip install git+https://github.com/esa/AnomalyMatch.git
pip install -r requirements.txt
```

Download the data into the local `DATA/` directory before running the scripts. The downloader reads URLs from `zenodo_download_manifest.txt` and writes the files into `DATA/`.

For private or draft Zenodo files, export your token first:

```bash
export ZENODO_TOKEN="your_zenodo_token"
bash fetch_esac_data.sh
```

# Code

### Core Scripts

- **`make_Datalabs_JWST_footprints.py`**  
  Extracts JWST Stage 3 image footprints from Datalabs volumes and stores them in a structured format (Parquet).

- **`match_sources_to_Datalabs_footprints.py`**  
  Cross-matches catalog sources with JWST Stage 3 footprints, assigning sources to the nearest valid footprint.

- **`make_cutouts.py`**  
  Creates cutouts around matched sources, resizes them to a uniform resolution, and applies padding relative to source segmentation areas.

- **`imgs_to_zarr.py`**  
  Converts generated cutouts into Zarr format in chunks (1 chunk : 10,000 cutouts) for efficient storage and access during evaluation.  

### Supporting Files

- **`constants.py`**  
  Holds global configuration parameters for/about JWST such as pixel scales, cutout sizes, and padding factors.  

- **`utils.py`**  
  Utility functions used across scripts (I/O helpers, coordinate transforms, normalization, etc.).  

### Model Development

- **`model_training.ipynb`**  
  Training the AM models on the cutouts dataset (classification, evaluation, + deduplication within a radius).  

- **`scripts.ipynb`**  
  Code snippets and helper routines used during development (dataset plots, lens mosaics/plots, HST-JWST lens plots, ADS/ESA-Sky cross-reference, manual cutouts).  

# Data
## `lenses_confirmed.csv`

**Description:** All lenses found through AnomalyMatch (58) + COWLS 17 selected lenses (11)

**Number of Entries:** 69

**Columns:**

| Column           | Type    | Description                                                           |
|------------------|---------|-----------------------------------------------------------------------|
| `filename`       | object  | Processed filename of the cutout                                      |
| `label`          | object  | Assigned class label (nominal / anomaly)                              |
| `filename_before`| object  | Original filename prior to post-processing (deduplication)            |
| `file_path`      | object  | Absolute path to the cutout image                                     |
| `RA`             | float64 | Right Ascension of the source (deg)                                   |
| `DEC`            | float64 | Declination of the source (deg)                                       |
| `CATALOGUE`      | object  | Source origin (COSMOS / ASTRODEEP / COWLS)                            |
| `zspec`          | float64 | Spectroscopic redshift (if available)                                 |
| `zphot`          | float64 | Photometric redshift (if available)                                   |
| `Identified`     | bool    | Flag indicating whether the source is referenced as a lens            |
| `ID`             | object  | Unique identifier of the source (if assigned)                         |
| `voted_class`    | object  | Consensus class afterexpert validation                                |

## `jwst_stage3_footprints.parquet`

**Description:** Contains metadata about JWST Stage 3 images located in Datalabs volumes and their corresponding sky footprints (only one `file_path` per four filters => **x4** number of files used).  

**Number of Entries:** 3,663  

**Columns:**  

| Column      | Type    | Description                                       |
|-------------|---------|---------------------------------------------------|
| `file_path` | object  | Full path to the JWST Stage 3 FITS image          |
| `RA`        | float64 | Right Ascension of the footprint center (deg)     |
| `DEC`       | float64 | Declination of the footprint center (deg)         |
| `footprint` | object  | Polygon footprint in WKT format (RA/Dec vertices) |


## `astrodeep_footprint_matches.parquet`

**Description:** Mapping of JWST Stage 3 image footprints (`jwst_stage3_footprints.parquet`) to Astrodeep source IDs contained within them. Each Astrodeep source is assigned to the most suitable JWST product, defined as the footprint whose centroid lies closest (by angular distance) to the source coordinates, with the condition that teh source does not fall into an invalid footprint area.  

**Number of Entries:** 472,493  

**Columns:**  

| Column      | Type    | Description                                     |
|-------------|---------|-------------------------------------------------|
| `RA`        | float64 | Right Ascension of the Astrodeep source (deg)   |
| `DEC`       | float64 | Declination of the Astrodeep source (deg)       |
| `ID`        | object  | Unique identifier of the Astrodeep source       |
| `seg_area`  | float64 | Segmentation area of the source (arcsec²)       |
| `file_path` | object  | Full path to the matched JWST Stage 3 FITS file |

## `cosmos_footprint_matches.parquet` 

(idem)

**Number of Entries:** 393,429

## `cutouts_df.parquet`

**Description:** The final dataframe of cutouts generated from JWST Stage 3 images, matched to sources from external catalogs.  

**Number of Entries:** 614,015  

**Columns:**  

| Column      | Type    | Description                                                               |
|-------------|---------|---------------------------------------------------------------------------|
| `file_path` | object  | Full path to the cutout file                                              |
| `RA`        | float64 | Right Ascension of the source for which the cutout was made (deg)         |
| `DEC`       | float64 | Declination of the source for which the cutout was made (deg)             |
| `CATALOGUE` | object  | Source catalog from which the object originates (e.g., ASTRODEEP, COSMOS) |

# Model

The model checkpoints, configs and labelled files used are in `dataset_v{N}/` directories (N: 1, 2).
