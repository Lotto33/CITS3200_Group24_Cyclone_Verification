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

def text_of(element) -> str:
    return (element.text or "").strip() if element is not None else ""

def qname(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def get_geojson_dest(gml_file: Path) -> Path:
    state = infer_state(gml_file)
    return Path("data/geojson") / state / f"{gml_file.stem}.geojson"

def convert_file(input_path: Path, output_path: Path):
    tree = ET.parse(str(input_path))
    # get the root XML element -> tags root with source filename
    root = tree.getroot()
    root.set("sourceFile", input_path.name)
    feature_collection = build_feature_collection(root) #turns the XML features into GeoJSON data
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(feature_collection, handle, indent=2) # write the GeoJSON to disk
    return output_path

def build_feature_collection(root):
    features = collect_features(root)
    root_metadata = {
        "fcastTime": text_of(root.find(qname(TC_NS, "fcastTime"))),
        "issueTime": text_of(root.find(qname(TC_NS, "issueTime"))),
        "expiryHrs": parse_text_number(text_of(root.find(qname(TC_NS, "expiryHrs")))),
        "distId": text_of(root.find(qname(TC_NS, "distId"))),
        "distName": text_of(root.find(qname(TC_NS, "distName"))),
    }
    feature_collection = {
        "type": "FeatureCollection",
        "metadata": root_metadata,
        "features": features,
    }
    bbox = collect_boundingbox(features)
    if bbox is not None:
        feature_collection["bbox"] = bbox
    return feature_collection

def collect_features(element):
    features = []
    # TODO  Iterate through the supported tcData feature elements in the XML,
    #       build their GeoJSON geometry and properties, and append each as a
    #       GeoJSON Feature to the features list.
    return features

def parse_text_number(text: str):
    value = (text or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None

def collect_boundingbox(features):
    #TODO calculate the bounding box of all the geometries in a given GeoJSON features.
    return

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

