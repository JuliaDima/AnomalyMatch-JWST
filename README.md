<div align="center">
  <h2>AnomalyMatch for James Webb Space Telescope</h2>
  <p>
    <a href="https://github.com/esa/AnomalyMatch">
      <img alt="View AnomalyMatch on GitHub" src="https://img.shields.io/badge/View%20AnomalyMatch%20on-GitHub-2da44e?style=flat&logo=github&logoColor=white">
    </a>
  </p>
  <p>
    <sub>
      JWST data-preparation and lens-discovery workflow built on
      <a href="https://github.com/esa/AnomalyMatch">AnomalyMatch</a>.
    </sub>
  </p>
</div>

<p align="center">
  <img src="assets/mosaic_A.png" alt="Grade A lens mosaic" width="560"><br>
  <sub><em>Examples of Grade A lenses found in this project, with measurement method specified.</em></sub>
</p>

<h3>Setup</h3>

<p><sub>Create a conda environment, then install this project and its dependencies into that environment.</sub></p>

```bash
conda create -n am-jwst python=3.11
conda activate am-jwst
"$CONDA_PREFIX/bin/python" -m pip install -r requirements.txt
"$CONDA_PREFIX/bin/python" -m pip install -e .
```

<p>
  <sub>
    <code>requirements.txt</code> installs AnomalyMatch from
    <code>https://github.com/ESA/AnomalyMatch.git</code>, which provides the
    <code>anomaly_match</code> module used by the notebooks.
  </sub>
</p>

<h3>Workflow</h3>

<p><sub>This repository is the JWST-specific data-preparation layer around AnomalyMatch.</sub></p>

<table>
  <tr>
    <th><sub>Step</sub></th>
    <th><sub>What it does</sub></th>
  </tr>
  <tr>
    <td><sub>1</sub></td>
    <td><sub>Scan JWST NIRCam Stage 3 products and source catalogues.</sub></td>
  </tr>
  <tr>
    <td><sub>2</sub></td>
    <td><sub>Match ASTRODEEP and COSMOS sources to JWST footprints.</sub></td>
  </tr>
  <tr>
    <td><sub>3</sub></td>
    <td><sub>Build 4-filter RGB cutouts around matched sources.</sub></td>
  </tr>
  <tr>
    <td><sub>4</sub></td>
    <td><sub>Package cutouts for model training and prediction.</sub></td>
  </tr>
  <tr>
    <td><sub>5</sub></td>
    <td><sub>Use AnomalyMatch on the resulting JWST cutout dataset.</sub></td>
  </tr>
</table>

<h3>Configuration</h3>

<table>
  <tr>
    <th><sub>Parameter</sub></th>
    <th><sub>Value</sub></th>
    <th><sub>Meaning</sub></th>
  </tr>
  <tr>
    <td><sub>JWST_FILTERS</sub></td>
    <td><sub>F115, F150, F277, F444</sub></td>
    <td><sub>NIRCam filters used by the main pipeline.</sub></td>
  </tr>
  <tr>
    <td><sub>MIN_CUTOUT_SIZE</sub></td>
    <td><sub>12</sub></td>
    <td><sub>Minimum allowed source-derived cutout radius in pixels.</sub></td>
  </tr>
  <tr>
    <td><sub>CUTOUT_FACTOR</sub></td>
    <td><sub>3.5</sub></td>
    <td><sub>Scale factor applied to the source-derived radius.</sub></td>
  </tr>
  <tr>
    <td><sub>CUTOUT_RES</sub></td>
    <td><sub>224</sub></td>
    <td><sub>Final resized image resolution for training.</sub></td>
  </tr>
  <tr>
    <td><sub>JWST_OPT_RES_NIRCam_SHORT</sub></td>
    <td><sub>0.0317 arcsec/pixel</sub></td>
    <td><sub>Short-wavelength NIRCam pixel scale.</sub></td>
  </tr>
  <tr>
    <td><sub>JWST_OPT_RES_NIRCam_LONG</sub></td>
    <td><sub>0.063 arcsec/pixel</sub></td>
    <td><sub>Long-wavelength NIRCam pixel scale.</sub></td>
  </tr>
</table>

<h3>Data</h3>

<p>
  <sub>
    Download the shared dataset from Zenodo. The manifest points to
    <a href="https://zenodo.org/records/19147582">Zenodo record 19147582</a>
    (<code>10.5281/zenodo.19147582</code>) and verifies MD5 checksums.
  </sub>
</p>

```bash
./fetch_esac_data.sh
```

<p>
  <sub>
    This downloads the shared tables into <code>DATA/</code>. The large
    <code>training_images.zip</code> file is optional and skipped by default.
    Include it only when needed:
  </sub>
</p>

```bash
./fetch_esac_data.sh --include-optional
```

<table>
  <tr>
    <th><sub>Input</sub></th>
    <th><sub>Default path</sub></th>
  </tr>
  <tr>
    <td><sub>JWST footprints</sub></td>
    <td><sub><code>DATA/jwst_stage3_footprints.parquet</code></sub></td>
  </tr>
  <tr>
    <td><sub>ASTRODEEP catalogue</sub></td>
    <td><sub><code>DATA/ASTRODEEP_cat.csv</code></sub></td>
  </tr>
  <tr>
    <td><sub>COSMOS catalogue</sub></td>
    <td><sub><code>DATA/COSMOS_cat.csv</code></sub></td>
  </tr>
  <tr>
    <td><sub>COSMOS observation filter</sub></td>
    <td><sub><code>DATA/cosmos_observations.csv</code>, if available</sub></td>
  </tr>
</table>

<h3>Run</h3>

<p><sub>Re-run matching and cutout generation from the downloaded <code>DATA/</code> inputs.</sub></p>

```bash
./run_jwst_pipeline.sh
```

<p>
  <sub>
    Raw FITS footprint extraction is still available as <code>amjwst-footprints</code>
    for ESA Datalabs use, but it is not part of the default pipeline because it
    requires access to JWST archives in ESA Datalabs.
  </sub>
</p>

<p><sub>Optional CLI entry points after editable install:</sub></p>

```bash
amjwst-footprints
amjwst-match-footprints
amjwst-run-cutouts
```

<h3>Notebooks</h3>

<ul>
  <li><sub><code>scripts.ipynb</code></sub></li>
  <li><sub><code>model_training.ipynb</code></sub></li>
</ul>
