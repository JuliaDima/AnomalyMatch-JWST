#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${DATA_DIR:-${SCRIPT_DIR}/DATA}"
MANIFEST_FILE="${MANIFEST_FILE:-${SCRIPT_DIR}/zenodo_download_manifest.txt}"
ZENODO_TOKEN="${ZENODO_TOKEN:-}"
DRY_RUN=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [--dry-run] [--list] [--manifest PATH]

Downloads dataset files from Zenodo or any direct HTTPS URLs into the
local DATA/ directory.

Manifest format:
  <url> <relative/path/under/DATA>

Environment overrides:
  DATA_DIR
  MANIFEST_FILE
  ZENODO_TOKEN
EOF
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'Missing required command: %s\n' "$1" >&2
    exit 1
  }
}

download_file() {
  local url="$1"
  local relative_path="$2"
  local target_path="${DATA_DIR}/${relative_path}"
  local -a curl_cmd=(curl --fail --location --progress-bar --output "${target_path}")

  mkdir -p "$(dirname "${target_path}")"
  printf 'Downloading %s -> %s\n' "${url}" "${target_path}"

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    return 0
  fi

  if [[ -n "${ZENODO_TOKEN}" ]]; then
    curl_cmd+=(-H "Authorization: Bearer ${ZENODO_TOKEN}")
  fi

  curl_cmd+=("${url}")
  "${curl_cmd[@]}"
}

print_manifest() {
  local line url relative_path

  if [[ ! -f "${MANIFEST_FILE}" ]]; then
    printf 'Manifest file not found: %s\n' "${MANIFEST_FILE}" >&2
    exit 1
  fi

  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" ]] && continue
    [[ "${line}" =~ ^# ]] && continue

    url="${line%%[[:space:]]*}"
    relative_path="${line#${url}}"
    relative_path="${relative_path#"${relative_path%%[![:space:]]*}"}"

    if [[ -z "${url}" || -z "${relative_path}" ]]; then
      printf 'Invalid manifest line: %s\n' "${line}" >&2
      exit 1
    fi

    printf '%s -> %s/%s\n' "${url}" "${DATA_DIR}" "${relative_path}"
  done < "${MANIFEST_FILE}"
}

run_manifest() {
  local line url relative_path

  if [[ ! -f "${MANIFEST_FILE}" ]]; then
    printf 'Manifest file not found: %s\n' "${MANIFEST_FILE}" >&2
    exit 1
  fi

  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" ]] && continue
    [[ "${line}" =~ ^# ]] && continue

    url="${line%%[[:space:]]*}"
    relative_path="${line#${url}}"
    relative_path="${relative_path#"${relative_path%%[![:space:]]*}"}"

    if [[ -z "${url}" || -z "${relative_path}" ]]; then
      printf 'Invalid manifest line: %s\n' "${line}" >&2
      exit 1
    fi

    download_file "${url}" "${relative_path}"
  done < "${MANIFEST_FILE}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --list)
      print_manifest
      exit 0
      ;;
    --manifest)
      MANIFEST_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

need_cmd curl
mkdir -p "${DATA_DIR}"

run_manifest

printf 'Done. Files are available under %s\n' "${DATA_DIR}"
