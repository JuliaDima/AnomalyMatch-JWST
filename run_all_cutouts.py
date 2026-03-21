import time

from make_cutouts import run_make_cutouts


def run_step(catalogue: str) -> float:
    print(f"Starting {catalogue}")
    start = time.perf_counter()
    run_make_cutouts(catalogue=catalogue)
    elapsed = time.perf_counter() - start
    print(f"Finished {catalogue} in {elapsed:.2f} seconds")
    return elapsed


def main():
    total_start = time.perf_counter()
    astrodeep_elapsed = run_step("astrodeep")
    cosmos_elapsed = run_step("cosmos")
    total_elapsed = time.perf_counter() - total_start

    print("Summary")
    print(f"astrodeep_seconds: {astrodeep_elapsed:.2f}")
    print(f"cosmos_seconds: {cosmos_elapsed:.2f}")
    print(f"total_seconds: {total_elapsed:.2f}")


if __name__ == "__main__":
    main()
