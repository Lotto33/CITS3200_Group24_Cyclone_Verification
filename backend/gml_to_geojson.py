from pathlib import Path
import json
import xml.etree.ElementTree as ET
import sys

#relative path
gml_inputPath = "../data/"

TC_NS = "http://www.bom.gov.au/dtd/tc"
GML_NS = "http://www.opengis.net/gml"
NAMESPACES = {"bom": TC_NS, "gml": GML_NS}


def iter_gml_files(root: Path):
    #NOTE CAN REMOVE SORT IF PERFOMANCE IS AN ISSUE.
    return sorted(path for path in root.rglob("*.gml") if path.is_file())

def infer_state(input_path: Path) -> str:
    for path in [input_path, *input_path.parents]:
        parent_name = path.name.upper()
        if "QLD" in parent_name:
            return "QLD"
        if "NT" in parent_name:
            return "NT"
        if "WA" in parent_name:
            return "WA"
    return "UNKNOWN"

def convert_file(input_path: Path, output_path: Path):
    #TODO
    return output_path

def get_geojson_dest(gml_file: Path) -> Path:
    state = infer_state(gml_file)
    return Path("data/geojson") / state / f"{gml_file.stem}.geojson"

def main() -> None:
    #NOTE: PATH YET TO BE FINALISED.
    # It should point to the root folder containing the state-wide GML folders.
    gml_src = Path(gml_inputPath).expanduser().resolve()

    if not gml_src.is_dir():
        raise SystemExit(f"Expected a directory containing state folders: {gml_src}")

    # Recursively gets all GML files across the state folders.
    gml_files = iter_gml_files(gml_src)
    if not gml_files:
        raise SystemExit(f"No .gml files found in {gml_src}")

    outputs = []
    for gml_file in gml_files:
        geojson_dest = get_geojson_dest(gml_file)
        try:
            out = convert_file(gml_file, geojson_dest)
            outputs.append(out)
        except Exception as exc:  # pragma: no cover - robustness for batch runs
            print(f"Failed to convert {gml_file}: {exc}", file=sys.stderr)

    if outputs:
        print(f"Converted {len(outputs)} file(s)")


if __name__ == "__main__":
    main()

