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

def collect_features(root):
    #Iterate through the supported tcData feature elements in the XML,
    #       build their GeoJSON geometry and properties, and append each as a
    #       GeoJSON Feature to the features list.
    features = []

    for feature_type in [qname(TC_NS, "tcfix"),qname(TC_NS, "tcTrack"), qname(TC_NS, "tcfix"), qname(TC_NS, "tcForecastArea"),qname(TC_NS, "tcWarningArea"), qname(TC_NS, "tcWatchArea"), qname(TC_NS, "tcWindArea") ]:
        for element in root.findall(f".//{feature_type}"):
            geometry = build_geometry_for_feature(element,feature_type.split("}", 1)[1]) 
            if geometry is None:
                continue
            properties = build_feature_properties(root, element, feature_type.split("}", 1)[1])
            features.append({"type": "Feature", "properties":properties, "geometry": geometry})       
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
    # TODO:
    # Calculate the bounding box containing all coordinates from the
    # geometries in the supplied GeoJSON features.
    #
    # Parameters:
    #   features: A list of GeoJSON Feature dictionaries. Each feature
    #             contains a geometry whose coordinates should be examined.
    #
    # Returns:
    #   A list in the form:
    #       [min_longitude, min_latitude, max_longitude, max_latitude]
    #   representing the bounding box of all features.
    #   Return None if there are no coordinates.
    pass


def normalize_longitude(lon: float) -> float:
    # TODO:
    # Take a longitude value and normalize it into the standard
    # GeoJSON longitude range of -180 to 180 degrees.
    #
    # Parameters:
    #   lon: The longitude value to normalize.
    #
    # Returns:
    #   The normalized longitude as a float.
    pass

def normalize_coords(coords):
    # TODO:
    # Iterate through a collection of [longitude, latitude] coordinate
    # pairs and normalize the longitude of each coordinate using
    # normalize_longitude().
    #
    # Parameters:
    #   coords: A list of [longitude, latitude] coordinate pairs.
    #
    # Returns:
    #   A new list containing the coordinates with normalized longitudes.
    pass


def split_at_antimeridian(coords):
    # TODO:
    # Split a sequence of coordinates into separate line segments whenever
    # consecutive coordinates cross the antimeridian. This prevents GeoJSON
    # geometries from incorrectly drawing a line across the entire map.
    #
    # Parameters:
    #   coords: A list of [longitude, latitude] coordinate pairs.
    #
    # Returns:
    #   A list of coordinate segments, where each segment contains at least
    #   two coordinates.
    pass


def ensure_ring_closed(ring):
    # TODO:
    # Ensure that a polygon ring is closed by making its final coordinate
    # equal to its first coordinate. If the ring is empty, return it unchanged.
    #
    # Parameters:
    #   ring: A list of [longitude, latitude] coordinates representing
    #         a polygon ring.
    #
    # Returns:
    #   The closed polygon ring.
    pass


def signed_area(ring):
    # TODO:
    # Calculate the signed area of a polygon ring using the shoelace formula.
    # The sign of the result is used to determine the ring's winding direction.
    #
    # Parameters:
    #   ring: A closed list of [longitude, latitude] coordinates.
    #
    # Returns:
    #   The signed area as a float. Return 0.0 if the ring does not contain
    #   enough coordinates to form a valid polygon.
    pass


def enforce_winding(ring, exterior: bool):
    # TODO:
    # Ensure that a polygon ring has the required winding direction.
    # Reverse the coordinates when necessary based on whether the ring is
    # an exterior boundary or an interior hole.
    #
    # Parameters:
    #   ring: A polygon ring represented as [longitude, latitude] coordinates.
    #   exterior: True if the ring represents an exterior boundary;
    #             False if it represents an interior hole.
    #
    # Returns:
    #   The ring with the correct winding direction.
    pass


def parse_coordinate_pairs(text):
    # TODO:
    # Parse a string containing longitude,latitude coordinate pairs into
    # a list of [longitude, latitude] coordinates.
    # Validate that each coordinate contains both longitude and latitude
    # values and that the values are finite numbers.
    #
    # Parameters:
    #   text: A string containing whitespace-separated coordinate pairs,
    #         where each pair is formatted as "longitude,latitude".
    #
    # Returns:
    #   A list of [longitude, latitude] coordinate pairs with normalized
    #   longitudes.
    pass


def build_ring(coords, exterior: bool):
    # TODO:
    # Build one or more valid polygon rings from the supplied coordinates.
    # Split coordinates at the antimeridian, normalize the coordinates,
    # close each ring, and enforce the appropriate winding direction.
    #
    # Parameters:
    #   coords: A list of [longitude, latitude] coordinate pairs.
    #   exterior: True if the ring is an exterior polygon boundary;
    #             False if it is an interior hole.
    #
    # Returns:
    #   A list of processed polygon rings.
    pass


def parse_polygon_geometry(geometry_elem):
    # TODO:
    # Find polygon members within the GML geometry element and parse their
    # exterior and interior boundaries into GeoJSON-compatible polygon rings.
    #
    # Parameters:
    #   geometry_elem: The XML element containing the GML polygon geometry.
    #
    # Returns:
    #   A list of polygons, where each polygon contains its exterior ring
    #   and any interior hole rings.
    pass


def build_geometry_for_feature(feature_elem, feature_type: str):
    # TODO:
    # Build the appropriate GeoJSON geometry for a supported BOM tcData
    # feature. Polygon-based feature types should produce MultiPolygon
    # geometries, tcFix should produce a Point, and tcTrack should produce
    # a LineString or MultiLineString when it crosses the antimeridian.
    #
    # Parameters:
    #   feature_elem: The XML element representing the BOM feature.
    #   feature_type: The name of the BOM feature type, such as tcFix,
    #                 tcTrack, tcForecastArea, tcWarningArea, tcWatchArea,
    #                 or tcWindArea.
    #
    # Returns:
    #   A GeoJSON geometry dictionary, or None if the feature has no valid
    #   geometry.
    pass


def coerce_optional_number(value) -> float | None:
    # Extract the text from an XML element and convert it to a float.
    # Return None when the element is missing or contains no value.
    #
    # Parameters:
    #   value: An XML element containing an optional numeric value,
    #          or None.
    #
    # Returns:
    #   The numeric value as a float, or None when no value is present.

    if value is None:
        return None
    text = (value.text or "").strip()
    if not text:
        return None
    return float(text)


def coerce_optional_text(value):
    
    # Extract and strip the text from an optional XML element.
    # Return None when the element is missing or contains no text.
    #
    # Parameters:
    #   value: An XML element containing optional text, or None.
    #
    # Returns:
    #   The stripped text as a string, or None when no text is present.
    if value is None:
        return None
    text = (value.text or "").strip()
    if not text:
        return None
    return text


def coerce_optional_category(value):
    # Extract the text from an optional category XML element.
    # Convert it to a float when it contains a numeric value; otherwise
    # preserve it as text.
    #
    # Parameters:
    #   value: An XML element containing an optional category value,
    #          or None.
    #
    # Returns:
    #   A float if the category is numeric, a string if it is non-numeric,
    #   or None when no value is present.
    if value is None:
            return None
    text = (value.text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return text


def build_feature_properties(root, feature_elem, feature_type: str):
    # TODO:
    # Build the properties dictionary for a GeoJSON Feature.
    # Include metadata from the GML root and feature-specific properties
    # depending on the feature type.
    #
    # Parameters:
    #   root: The root XML element containing shared cyclone metadata.
    #   feature_elem: The XML element representing the individual feature.
    #   feature_type: The name of the BOM feature type.
    #
    # Returns:
    #   A dictionary containing the GeoJSON feature properties.
    pass


def collect_bbox(features):
    # TODO:
    # Calculate the bounding box containing all geometries in the supplied
    # GeoJSON features. Handle Point, LineString, MultiLineString and
    # MultiPolygon geometries.
    #
    # Parameters:
    #   features: A list of GeoJSON Feature dictionaries containing geometry.
    #
    # Returns:
    #   A bounding box in the form [min_longitude, min_latitude,
    #   max_longitude, max_latitude], or None if there are no coordinates.
    pass

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

