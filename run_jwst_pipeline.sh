#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$REPO_ROOT"

echo "Starting: JWST footprint extraction"
python make_Datalabs_JWST_footprints.py
echo "Finished: JWST footprint extraction"

echo "Starting: Source-to-footprint matching"
python match_sources_to_Datalabs_footprints.py
echo "Finished: Source-to-footprint matching"

echo "Starting: Cutout generation"
python run_all_cutouts.py
echo "Finished: Cutout generation"
