

<h1 align="center">AnomalyMatch for James Webb Space Telescope</h1>

<p align="center">
  <a href="https://github.com/esa/AnomalyMatch">
    <img alt="View AnomalyMatch on GitHub" src="https://img.shields.io/badge/View%20AnomalyMatch%20on-GitHub-2da44e?style=flat&logo=github&logoColor=white">
  </a>
</p>

This repository builds on top of [AnomalyMatch](https://github.com/esa/AnomalyMatch) and is focused on discovering gravitational lenses in JWST.

# Setup

Create a conda environment, then install this project and its dependencies into
that environment:

```bash
conda create -n am-jwst python=3.11
conda activate am-jwst
"$CONDA_PREFIX/bin/python" -m pip install -r requirements.txt
"$CONDA_PREFIX/bin/python" -m pip install -e .
```

`requirements.txt` installs AnomalyMatch from
`https://github.com/ESA/AnomalyMatch.git`, which provides the
`anomaly_match` Python module used by the notebooks.


<p align="center">
  <img src="assets/mosaic_A.png" alt="Grade A lens mosaic" width="620"><br>
  <sub><em>Examples of Grade A lenses found in this project, with their measurement method specified (spectroscopic / photometric).</em></sub>
</p>

# Workflow

This repository is the JWST-specific data-preparation layer around AnomalyMatch. It does the following:

1. scans JWST NIRCam Stage 3 image products and external source catalogues available on ESA Datalabs (needs access to `JWST_DATALABS_PATH`)
2. matches ASTRODEEP and COSMOS catalogue sources with these JWST footprints
3. builds 4-filter RGB cutouts around those matched sources
4. package the cutouts into formats that are convenient for model training and prediction
5. use AnomalyMatch on the resulting cutout dataset

These steps use the following predefined configuration:

<table>
  <tr>
    <th><sub>Parameter</sub></th>
    <th><sub>Value</sub></th>
    <th><sub>Meaning</sub></th>
  </tr>
  <tr>
    <td><sub>JWST_FILTERS</sub></td>
    <td><sub>F115, F150, F277, F444</sub></td>
    <td><sub>The four NIRCam filters used here. If one or more filters are missing for a product, that product is skipped in the main pipeline.</sub></td>
  </tr>
  <tr>
    <td><sub>MIN_CUTOUT_SIZE</sub></td>
    <td><sub>12</sub></td>
    <td><sub>Minimum allowed cutout radius size in pixels resulted from Source Extractor segmentation area.</sub></td>
  </tr>
  <tr>
    <td><sub>CUTOUT_FACTOR</sub></td>
    <td><sub>3.5</sub></td>
    <td><sub>Factor applied to the source-derived radius for the cutout extraction window.</sub></td>
  </tr>
  <tr>
    <td><sub>CUTOUT_RES</sub></td>
    <td><sub>224</sub></td>
    <td><sub>Final resized image resolution used for training.</sub></td>
  </tr>
  <tr>
    <td><sub>JWST_OPT_RES_NIRCam_SHORT</sub></td>
    <td><sub>0.0317 arcsec/pixel</sub></td>
    <td><sub>Pixel scale used for short-wavelength NIRCam channels.</sub></td>
  </tr>
  <tr>
    <td><sub>JWST_OPT_RES_NIRCam_LONG</sub></td>
    <td><sub>0.063 arcsec/pixel</sub></td>
    <td><sub>Pixel scale used for long-wavelength NIRCam channels.</sub></td>
  </tr>
</table>

There are two ways to get the inputs for this workflow:

1. Download the shared dataset from Zenodo:

```bash
./fetch_esac_data.sh
```

The download manifest points to the published Zenodo record:

- https://zenodo.org/records/19147582
- DOI: `10.5281/zenodo.19147582`

It downloads the shared tables into `DATA/`. The large `training_images.zip`
file is optional and is skipped by default (use `--include-optional` to include it):

```bash
./fetch_esac_data.sh
```

The pipeline reads these downloaded paths directly:

- `DATA/jwst_stage3_footprints.parquet`
- `DATA/ASTRODEEP_cat.csv`
- `DATA/COSMOS_cat.csv`
- `DATA/cosmos_observations.csv` if available; otherwise the COSMOS observation
  filter is skipped

2. To re-run the matching and cutout steps from the downloaded `DATA/` inputs (regenerated matched observations and image cutouts):

```bash
./run_jwst_pipeline.sh
```

The raw FITS footprint extraction command is still available as
`amjwst-footprints` for **ESA Datalabs** use, but it is not part of the default
`run_jwst_pipeline.sh` as it requires access to JWST archives in ESA Datalabs.

**(optional)** After installing the project in editable mode, the workflow steps can also be run directly:

```bash
amjwst-footprints
amjwst-match-footprints
amjwst-run-cutouts
```

The original notebooks are still available for exploratory work:
- `scripts.ipynb`
- `model_training.ipynb`
