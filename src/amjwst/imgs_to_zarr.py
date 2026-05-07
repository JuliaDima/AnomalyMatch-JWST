import tempfile
from pathlib import Path

import pandas as pd
from images_to_zarr.convert import convert

from .constants import IMAGE_EXTENSIONS

repo_root = Path(__file__).resolve().parents[2]
base_folder = repo_root / "DATA" / "dataset_v2"
destination_folder = base_folder / "training_images"
labeled_data_path = base_folder / "labels_w_clear_lenses.csv"
zarr_output_dir = base_folder / "all_images_zarr_chunks"
custom_tmp_root = repo_root / "DATA" / "tmp_zarr"


def list_training_images(training_dir: Path) -> list[str]:
    training_dir.mkdir(parents=True, exist_ok=True)
    return [
        str(path)
        for path in training_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]


def load_unlabeled_paths() -> list[str]:
    cutouts_df = pd.read_parquet(base_folder / "all_cutouts_df.parquet")
    labeled_df = pd.read_csv(labeled_data_path)
    labeled_filenames = labeled_df["filename"].tolist()

    unlabeled_paths = [
        file_path
        for file_path in cutouts_df["file_path"]
        if not any(labeled_name in file_path for labeled_name in labeled_filenames)
    ]
    return unlabeled_paths[400000:500000]


def symlink_unlabeled_images(unlabeled_paths: list[str], tmp_dir_path: Path) -> int:
    symlink_count = 0
    for file_path in unlabeled_paths:
        filename = Path(file_path).name
        source_path = destination_folder / filename
        if not source_path.exists():
            continue

        try:
            (tmp_dir_path / filename).symlink_to(source_path)
            symlink_count += 1
        except Exception as exc:
            print(exc)

    return symlink_count


def main() -> None:
    all_images = list_training_images(destination_folder)
    print(f"Found {len(all_images)} image files in cutouts folder: {destination_folder}.")

    unlabeled_paths = load_unlabeled_paths()
    print(f"Found {len(unlabeled_paths)} unlabeled images in parquet metadata.")

    custom_tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=custom_tmp_root) as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        symlink_count = symlink_unlabeled_images(unlabeled_paths, tmp_dir_path)
        print(f"Symlinked {symlink_count} images to temporary folder.")

        zarr_path = convert(
            folders=[str(tmp_dir_path)],
            recursive=True,
            output_dir=str(zarr_output_dir),
            num_parallel_workers=8,
            chunk_shape=(1000, 3, 224, 224),
            compressor="zstd",
            clevel=4,
        )

    print(f"Zarr file created at: {zarr_path}")


if __name__ == "__main__":
    main()
