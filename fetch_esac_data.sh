#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${DATA_DIR:-${SCRIPT_DIR}/DATA}"
MANIFEST_FILE="${MANIFEST_FILE:-${SCRIPT_DIR}/zenodo_download_manifest.txt}"
ZENODO_TOKEN="${ZENODO_TOKEN:-}"
SKIP_EXISTING=1
INCLUDE_OPTIONAL=0
DRY_RUN=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [--dry-run] [--force] [--include-optional] [--list] [--manifest PATH]

Downloads dataset files from Zenodo or any direct HTTPS URLs into the
local DATA/ directory.

Manifest format:
  <url> <relative/path/under/DATA> [md5:<checksum>] [optional]

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
  local checksum="${3:-}"
  local target_path="${DATA_DIR}/${relative_path}"
  local part_path="${target_path}.part"
  local -a curl_base_cmd=(
    curl
    --fail
    --location
    --progress-bar
    --retry 8
    --retry-delay 10
    --retry-max-time 900
    --retry-all-errors
  )

  mkdir -p "$(dirname "${target_path}")"

  if [[ -f "${target_path}" && "${SKIP_EXISTING}" -eq 1 ]]; then
    printf 'Existing file found: %s\n' "${target_path}"
    if checksum_matches "${target_path}" "${checksum}"; then
      printf 'Skipping existing verified file: %s\n' "${target_path}"
      return 0
    fi

    printf 'Existing file is incomplete or checksum differs; resuming as partial download.\n'
    if [[ "${DRY_RUN}" -eq 1 ]]; then
      return 0
    fi

    mv "${target_path}" "${part_path}"
  fi

  printf 'Downloading %s -> %s\n' "${url}" "${target_path}"

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    return 0
  fi

  if [[ -n "${ZENODO_TOKEN}" ]]; then
    curl_base_cmd+=(-H "Authorization: Bearer ${ZENODO_TOKEN}")
  fi

  if [[ -f "${part_path}" ]]; then
    if ! "${curl_base_cmd[@]}" --continue-at - --output "${part_path}" "${url}"; then
      printf 'Resume failed for %s; retrying from scratch.\n' "${target_path}" >&2
      rm -f "${part_path}"
      "${curl_base_cmd[@]}" --output "${part_path}" "${url}"
    fi
  else
    "${curl_base_cmd[@]}" --output "${part_path}" "${url}"
  fi

  mv "${part_path}" "${target_path}"
  verify_checksum "${target_path}" "${checksum}"
}

md5_for_file() {
  local file_path="$1"

  if command -v md5sum >/dev/null 2>&1; then
    md5sum "${file_path}" | awk '{print $1}'
  elif command -v md5 >/dev/null 2>&1; then
    md5 -q "${file_path}"
  else
    printf 'Missing checksum command: md5sum or md5\n' >&2
    exit 1
  fi
}

verify_checksum() {
  local file_path="$1"
  local checksum="${2:-}"
  local expected actual

  [[ -z "${checksum}" ]] && return 0

  if [[ "${checksum}" != md5:* ]]; then
    printf 'Unsupported checksum format for %s: %s\n' "${file_path}" "${checksum}" >&2
    exit 1
  fi

  expected="${checksum#md5:}"
  actual="$(md5_for_file "${file_path}")"

  if [[ "${actual}" != "${expected}" ]]; then
    printf 'Checksum mismatch for %s\nExpected: %s\nActual:   %s\n' "${file_path}" "${expected}" "${actual}" >&2
    exit 1
  fi

  printf 'Verified md5: %s\n' "${file_path}"
}

checksum_matches() {
  local file_path="$1"
  local checksum="${2:-}"
  local expected actual

  [[ -z "${checksum}" ]] && return 0

  if [[ "${checksum}" != md5:* ]]; then
    printf 'Unsupported checksum format for %s: %s\n' "${file_path}" "${checksum}" >&2
    exit 1
  fi

  expected="${checksum#md5:}"
  actual="$(md5_for_file "${file_path}")"

  [[ "${actual}" == "${expected}" ]]
}

print_manifest() {
  local line url relative_path checksum optional

  if [[ ! -f "${MANIFEST_FILE}" ]]; then
    printf 'Manifest file not found: %s\n' "${MANIFEST_FILE}" >&2
    exit 1
  fi

  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" ]] && continue
    [[ "${line}" =~ ^# ]] && continue

    read -r url relative_path checksum optional <<< "${line}"

    if [[ -z "${url}" || -z "${relative_path}" ]]; then
      printf 'Invalid manifest line: %s\n' "${line}" >&2
      exit 1
    fi

    if [[ "${checksum:-}" == "optional" ]]; then
      optional="optional"
      checksum=""
    fi

    printf '%s -> %s/%s' "${url}" "${DATA_DIR}" "${relative_path}"
    [[ -n "${checksum:-}" ]] && printf ' (%s)' "${checksum}"
    [[ "${optional:-}" == "optional" ]] && printf ' [optional]'
    printf '\n'
  done < "${MANIFEST_FILE}"
}

run_manifest() {
  local line url relative_path checksum optional

  if [[ ! -f "${MANIFEST_FILE}" ]]; then
    printf 'Manifest file not found: %s\n' "${MANIFEST_FILE}" >&2
    exit 1
  fi

  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" ]] && continue
    [[ "${line}" =~ ^# ]] && continue

    read -r url relative_path checksum optional <<< "${line}"

    if [[ -z "${url}" || -z "${relative_path}" ]]; then
      printf 'Invalid manifest line: %s\n' "${line}" >&2
      exit 1
    fi

    if [[ "${checksum:-}" == "optional" ]]; then
      optional="optional"
      checksum=""
    fi

    if [[ "${optional:-}" == "optional" && "${INCLUDE_OPTIONAL}" -eq 0 ]]; then
      printf 'Skipping optional file: %s\n' "${relative_path}"
      continue
    fi

    download_file "${url}" "${relative_path}" "${checksum:-}"
  done < "${MANIFEST_FILE}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --force)
      SKIP_EXISTING=0
      shift
      ;;
    --include-optional)
      INCLUDE_OPTIONAL=1
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
