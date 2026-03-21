import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent

STEPS = [
    ("JWST footprint extraction", [sys.executable, "make_Datalabs_JWST_footprints.py"]),
    ("Source-to-footprint matching", [sys.executable, "match_sources_to_Datalabs_footprints.py"]),
    ("Cutout generation", [sys.executable, "run_all_cutouts.py"]),
]


def run_step(label: str, command: list[str]) -> float:
    print(f"Starting: {label}")
    print("Command:", " ".join(command))
    start = time.perf_counter()
    subprocess.run(command, cwd=REPO_ROOT, check=True)
    elapsed = time.perf_counter() - start
    print(f"Finished: {label} ({elapsed:.2f} s)")
    return elapsed


def main() -> None:
    total_start = time.perf_counter()
    elapsed_by_step = []

    for label, command in STEPS:
        elapsed_by_step.append((label, run_step(label, command)))

    total_elapsed = time.perf_counter() - total_start
    print("Pipeline summary")
    for label, elapsed in elapsed_by_step:
        print(f"- {label}: {elapsed:.2f} s")
    print(f"- Total: {total_elapsed:.2f} s")


if __name__ == "__main__":
    main()
