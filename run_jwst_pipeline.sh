#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$REPO_ROOT"
export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

DATA_DIR="${REPO_ROOT}/DATA"
FOOTPRINTS_PATH="${DATA_DIR}/jwst_stage3_footprints.parquet"
ASTRODEEP_PATH="${DATA_DIR}/ASTRODEEP_cat.csv"
COSMOS_PATH="${DATA_DIR}/COSMOS_cat.csv"
COSMOS_OBS_PATH="${DATA_DIR}/cosmos_observations.csv"

for required_file in "$FOOTPRINTS_PATH" "$ASTRODEEP_PATH" "$COSMOS_PATH"; do
  if [[ ! -f "$required_file" ]]; then
    printf 'Missing required input: %s\nRun ./fetch_esac_data.sh first.\n' "$required_file" >&2
    exit 1
  fi
done

echo "Starting: Source-to-footprint matching"
python -m amjwst.match_sources_to_datalabs_footprints \
  --footprints "$FOOTPRINTS_PATH" \
  --astrodeep-file "$ASTRODEEP_PATH" \
  --cosmos-file "$COSMOS_PATH" \
  --cosmos-obs-file "$COSMOS_OBS_PATH"
echo "Finished: Source-to-footprint matching"

echo "Starting: Cutout generation"
python -m amjwst.run_all_cutouts
echo "Finished: Cutout generation"
