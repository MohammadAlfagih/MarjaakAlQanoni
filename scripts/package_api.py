"""Package only backend source files for upload, without creating a notebook."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".model_cache", ".offload", "chroma_e5_db", "__pycache__", ".data"}
SOURCE_TYPES = {".py", ".md", ".txt", ".json", ".pdf"}


def main():
    destination = ROOT / "tmp" / "marjaak-api.zip"
    destination.parent.mkdir(exist_ok=True)
    files = [ROOT / "app.py"]
    for path in (ROOT / "apps" / "api").rglob("*"):
        relative = path.relative_to(ROOT)
        if (
            path.is_file()
            and not path.is_symlink()
            and not EXCLUDED.intersection(relative.parts)
            and path.suffix in SOURCE_TYPES
            and not path.name.startswith(".")
        ):
            files.append(path)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, path.relative_to(ROOT).as_posix())
    print(f"Created {destination} ({len(files)} source files)")


if __name__ == "__main__":
    main()
