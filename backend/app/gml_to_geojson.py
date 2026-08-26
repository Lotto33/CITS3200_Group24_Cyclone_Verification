from pathlib import Path
import json
import xml.etree.ElementTree as ET
import sys

#relative path
DEFAULT_GML_INPUT_PATH = "backend/data"
DEFAULT_GEOJSON_OUTPUT_PATH = "backend/data/geojson"

TC_NS = "http://www.bom.gov.au/dtd/tc"
GML_NS = "http://www.opengis.net/gml"
NAMESPACES = {"bom": TC_NS, "gml": GML_NS}


def iter_gml_files(root: Path):
    #NOTE CAN REMOVE SORT IF PERFOMANCE IS AN ISSUE.
    return sorted(path for path in root.rglob("*.gml") if path.is_file())

def text_of(element) -> str:
    return (element.text or "").strip() if element is not None else ""

def qname(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"

def sanitize_output_name(value: str) -> str:
    cleaned = (value or "").strip()
    cleaned = cleaned.replace(" ", "_")
    cleaned = "".join(ch for ch in cleaned if ch.isalnum() or ch in {"_", "-", "."})
    return cleaned

def get_gml_identifier(gml_file: Path) -> str:
    try:
        root = ET.parse(str(gml_file)).getroot()
    except (ET.ParseError, OSError):
        return gml_file.stem

    for key in ("name", "identifier", "id"):
        value = root.attrib.get(key)
        if value:
            sanitized = sanitize_output_name(value)
            if sanitized:
                return sanitized

    for elem in root.iter():
        local_name = elem.tag.rsplit("}", 1)[-1].lower()
        if local_name in {"name", "identifier", "id", "cyclonename", "cycloneid"}:
            value = text_of(elem)
            sanitized = sanitize_output_name(value)
            if sanitized:
                return sanitized

    return gml_file.stem


def get_geojson_dest(gml_file: Path, output_dir: Path) -> Path:
    identifier = get_gml_identifier(gml_file)
    return output_dir / f"{identifier}.geojson"


def get_distid_dataset_path(dist_id: str, output_dir: Path) -> Path:
    name = sanitize_output_name(dist_id or "unknown") or "unknown"
    return output_dir / f"{name}.json"


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
    bbox = collect_bbox(features)
    if bbox is not None:
        feature_collection["bbox"] = bbox
    return feature_collection

def collect_features(root):
    #Iterate through the supported tcData feature elements in the XML,
    #       build their GeoJSON geometry and properties, and append each as a
    #       GeoJSON Feature to the features list.
    features = []

    for feature_type in [qname(TC_NS, "tcFix"),qname(TC_NS, "tcTrack"), qname(TC_NS, "tcForecastArea"),qname(TC_NS, "tcWarningArea"), qname(TC_NS, "tcWatchArea"), qname(TC_NS, "tcWindArea") ]:
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

def normalize_longitude(lon: float) -> float:
    # Take a longitude value and normalize it into the standard
    # GeoJSON longitude range of -180 to 180 degrees.
    # Parameters:
    #   lon: The longitude value to normalize.
    # Returns:
    #   The normalized longitude as a float.
    normalized = (lon + 180.0) % 360.0 - 180.0
    if normalized == -180.0 and lon > 0:
        normalized = 180.0
    return normalized

def normalize_coords(coords):
    # Iterate through a collection of [longitude, latitude] coordinate
    # pairs and normalize the longitude of each coordinate using
    # normalize_longitude().
    # Parameters:
    #   coords: A list of [longitude, latitude] coordinate pairs.
    # Returns:
    #   A new list containing the coordinates with normalized longitudes.
    return [[normalize_longitude(lon), lat] for lon, lat in coords]


def split_at_antimeridian(coords):
    # Split a sequence of coordinates into separate line segments whenever
    # consecutive coordinates cross the antimeridian. The real fix is to insert
    # the actual crossing coordinate at ±180 so each split piece remains a valid
    # ring/line segment instead of silently collapsing into a 2-point stub.
    #
    # Note: for polygon rings that wrap across the dateline in a closed loop, the
    # first and last segment can still be handled as separate pieces; this is the
    # normal trade-off for a lightweight, stable solution.
    if not coords:
        return []

    def interpolate_crossing(prev_coord, curr_coord):
        lon1, lat1 = prev_coord
        lon2, lat2 = curr_coord
        delta = lon2 - lon1

        if delta > 180.0:
            boundary_lon = -180.0
            lon2_unwrapped = lon2 - 360.0
        elif delta < -180.0:
            boundary_lon = 180.0
            lon2_unwrapped = lon2 + 360.0
        else:
            return None

        if lon2_unwrapped == lon1:
            return [boundary_lon, lat1]

        t = (boundary_lon - lon1) / (lon2_unwrapped - lon1)
        lat_cross = lat1 + (lat2 - lat1) * t
        return [boundary_lon, lat_cross]

    segments = []
    current_segment = [coords[0]]

    for prev_coord, curr_coord in zip(coords, coords[1:]):
        if abs(curr_coord[0] - prev_coord[0]) > 180:
            crossing = interpolate_crossing(prev_coord, curr_coord)
            if crossing is not None:
                current_segment.append(crossing)
                segments.append(current_segment)
                current_segment = [crossing, curr_coord]
                continue
            segments.append(current_segment)
            current_segment = [curr_coord]
        else:
            current_segment.append(curr_coord)

    segments.append(current_segment)
    return [segment for segment in segments if len(segment) >= 2]


def ensure_ring_closed(ring):
    # Ensure that a polygon ring is closed by making its final coordinate
    # equal to its first coordinate. If the ring is empty, return it unchanged.
    #
    # Parameters:
    #   ring: A list of [longitude, latitude] coordinates representing
    #         a polygon ring.
    #
    # Returns:
    #   The closed polygon ring.
    if not ring:
        return ring
    if ring[0] != ring[-1]:
        return ring + [ring[0]]
    return ring


def signed_area(ring):
    # Calculate the signed area of a polygon ring using the shoelace formula.
    # The sign of the result is used to determine the ring's winding direction.
    #
    # Parameters:
    #   ring: A closed list of [longitude, latitude] coordinates.
    #
    # Returns:
    #   The signed area as a float. Return 0.0 if the ring does not contain
    #   enough coordinates to form a valid polygon.
    if len(ring) < 4:
        return 0.0
    
    area = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        area += (x1 * y2) - (x2 * y1)
    return area / 2.0    


def enforce_winding(ring, exterior: bool):
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
    area = signed_area(ring)
    if exterior and area <0:
        return list(reversed(ring))
    if not exterior and area > 0:
        return list(reversed(ring))
    return ring


def parse_coordinate_pairs(text):
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
    coords = []
    if not text:
        return coords

    for token in text.split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        try:
            lon = float(parts[0])
            lat = float(parts[1])
        except ValueError:
            continue

        if lon != lon or lat != lat:
            continue
        if lon in (float("inf"), float("-inf")) or lat in (float("inf"), float("-inf")):
            continue
        coords.append([normalize_longitude(lon), lat])
    return coords



def build_ring(coords, exterior: bool):
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
    if not coords:
        return []

    normalized = normalize_coords(coords)
    segments = split_at_antimeridian(normalized)

    rings = []
    for segment in segments:
        closed = ensure_ring_closed(segment)
        if len(closed) < 4:
            continue
        rings.append(enforce_winding(closed, exterior))
    return rings


def parse_polygon_geometry(geometry_elem):
    # Find polygon members within the GML geometry element and parse their
    # exterior and interior boundaries into GeoJSON-compatible polygon rings.
    #
    # Parameters:
    #   geometry_elem: The XML element containing the GML polygon geometry.
    #
    # Returns:
    #   A list of polygons, where each polygon contains its exterior ring
    #   and any interior hole rings.
    polygons = []
    for polygon_elem in geometry_elem.findall(f".//{qname(GML_NS, 'Polygon')}"):
        outer_elem = polygon_elem.find(qname(GML_NS, "outerBoundaryIs"))
        if outer_elem is None:
            outer_elem = polygon_elem.find(qname(GML_NS, "exterior"))

        exterior_text = ""
        if outer_elem is not None:
            outer_ring = outer_elem.find(qname(GML_NS, "LinearRing"))
            if outer_ring is not None:
                exterior_text = text_of(outer_ring.find(qname(GML_NS, "coordinates")))

        exterior_coords = parse_coordinate_pairs(exterior_text)
        exterior_rings = build_ring(exterior_coords, exterior=True)
        if not exterior_rings:
            continue

        inner_elems = polygon_elem.findall(qname(GML_NS, "innerBoundaryIs"))
        if not inner_elems:
            inner_elems = polygon_elem.findall(qname(GML_NS, "interior"))

        hole_rings = []
        for inner_elem in inner_elems:
            interior_text = ""
            inner_ring = inner_elem.find(qname(GML_NS, "LinearRing"))
            if inner_ring is not None:
                interior_text = text_of(inner_ring.find(qname(GML_NS, "coordinates")))
            interior_coords = parse_coordinate_pairs(interior_text)
            hole_rings.extend(build_ring(interior_coords, exterior=False))

        if len(exterior_rings) == 1:
            polygons.append([exterior_rings[0], *hole_rings])
        else:
            # For split exterior rings crossing the dateline, a hole cannot be
            # safely assigned to every piece without per-piece point-in-polygon
            # checks. Dropping holes in this rare case is safer than emitting
            # silently wrong geometry.
            polygons.extend([[ext_ring] for ext_ring in exterior_rings])

    return polygons


def build_geometry_for_feature(feature_elem, feature_type: str):
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
    polygon_feature_types = {"tcForecastArea", "tcWarningArea", "tcWatchArea", "tcWindArea"}

    if feature_type in polygon_feature_types:
        polygons = parse_polygon_geometry(feature_elem)
        if not polygons:
            return None
        return {"type": "MultiPolygon", "coordinates": polygons}
    if feature_type == "tcFix":
        coords_elem = feature_elem.find(f".//{qname(GML_NS, 'coordinates')}")
        coords_text = text_of(coords_elem)
        parsed = parse_coordinate_pairs(coords_text)

        if not parsed:
            pos_elem = feature_elem.find(f".//{qname(GML_NS, 'pos')}")
            pos_text = text_of(pos_elem)
            if pos_text:
                parts = pos_text.split()
                if len(parts) >= 2:
                    try:
                        lon, lat = float(parts[0]), float(parts[1])
                        parsed = [[normalize_longitude(lon), lat]]
                    except ValueError:
                        parsed = []

        if not parsed:
            return None
        return {"type": "Point", "coordinates": parsed[0]}
    if feature_type == "tcTrack":  
        coords_elem = feature_elem.find(f".//{qname(GML_NS, 'coordinates')}")
        coords = parse_coordinate_pairs(text_of(coords_elem))
        if len(coords) < 2:
            return None
        segments = split_at_antimeridian(coords)
        if not segments:
            return None
        if len(segments) == 1:
            return {"type": "LineString", "coordinates": segments[0]}
        return {"type": "MultiLineString", "coordinates": segments}
    return None


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
    
    props = {
        "featureType": feature_type, 
        "source_file":  Path(root.get("sourceFile", "")).name, #NOTE THIS WILL SILENTLY FAIL # TODO SOMEONE DOUBLE CHECK IF THIS IS OK
        "fcastTime": text_of(root.find(qname(TC_NS, "fcastTime"))),
        "issueTime": text_of(root.find(qname(TC_NS, "issueTime"))),
        "expiryHrs": parse_text_number(text_of(root.find(qname(TC_NS, "expiryHrs")))),
        "distId": text_of(root.find(qname(TC_NS, "distId"))),
        "distName": text_of(root.find(qname(TC_NS, "distName"))),
    }
    if feature_type == "tcFix":
        props.update(
            {
                "fixType": text_of(feature_elem.find(qname(TC_NS, "fixType"))),
                "fixTime": text_of(feature_elem.find(qname(TC_NS, "fixTime"))),
                "symbol": text_of(feature_elem.find(qname(TC_NS, "symbol"))),
                "category": coerce_optional_category(feature_elem.find(qname(TC_NS, "category"))),
                "timeOffset": coerce_optional_number(feature_elem.find(qname(TC_NS, "timeOffset"))),
            }
        )
    elif feature_type == "tcTrack":
        props.update(
            {
                "trackType": text_of(feature_elem.find(qname(TC_NS, "trackType"))),
                "startTime": text_of(feature_elem.find(qname(TC_NS, "startTime"))),
                "endTime": text_of(feature_elem.find(qname(TC_NS, "endTime"))),
            }
        )
    elif feature_type in {"tcForecastArea", "tcWarningArea", "tcWatchArea"}:
        props.update(
            {
                "areaType": text_of(feature_elem.find(qname(TC_NS, "areaType"))),
                "extent": coerce_optional_text(feature_elem.find(qname(TC_NS, "extent"))),
            }
        )
    elif feature_type == "tcWindArea":
        props.update(
            {
                "windType": text_of(feature_elem.find(qname(TC_NS, "windType"))),
                "marineType": text_of(feature_elem.find(qname(TC_NS, "marineType"))),
                "fixTime": text_of(feature_elem.find(qname(TC_NS, "fixTime"))),
                "fixType": text_of(feature_elem.find(qname(TC_NS, "fixType"))),
            }
        )
    return props


def collect_bbox(features):
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
    coords = []
    for feature in features:
        geometry = feature["geometry"]
        if geometry["type"] == "Point":
            coords.append(geometry["coordinates"])
        elif geometry["type"] == "LineString":
            # For a Point, coordinates is already a single [lon, lat] — append it directly.
            coords.extend(geometry["coordinates"])
        elif geometry["type"] == "MultiLineString":
            for line in geometry["coordinates"]:
                coords.extend(line)
        elif geometry["type"] == "MultiPolygon":
            for polygon in geometry["coordinates"]:
                for ring in polygon:
                    coords.extend(ring)
    if not coords:
        return None

    lons = [coord[0] for coord in coords]
    lats = [coord[1] for coord in coords]
    return [min(lons), min(lats), max(lons), max(lats)]

def run_conversion(data_dir: str | Path, output_dir: str | Path | None = None) -> list[Path]:
    """Convert every GML bulletin under data_dir into one dataset file per distId.

    Each file contains a JSON list of the bulletin FeatureCollections for that
    cyclone, preserving the historical time series instead of overwriting
    previous updates for the same distId.
    """
    gml_src = Path(data_dir).expanduser().resolve()
    geojson_root = Path(output_dir).expanduser().resolve() if output_dir is not None else (gml_src / "geojson")

    if not gml_src.is_dir():
        raise SystemExit(f"Expected a directory containing GML state folders: {gml_src}")

    grouped: dict[str, list[dict]] = {}
    for gml_file in iter_gml_files(gml_src):
        try:
            tree = ET.parse(str(gml_file))
            root = tree.getroot()
            root.set("sourceFile", gml_file.name)
            feature_collection = build_feature_collection(root)
            dist_id = (feature_collection.get("metadata") or {}).get("distId") or gml_file.stem
            grouped.setdefault(dist_id, []).append(feature_collection)
        except Exception as exc:  # pragma: no cover - robustness for batch runs
            print(f"Failed to convert {gml_file}: {exc}", file=sys.stderr)

    outputs = []
    geojson_root.mkdir(parents=True, exist_ok=True)
    for dist_id, feature_collections in grouped.items():
        output_path = get_distid_dataset_path(dist_id, geojson_root)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(feature_collections, handle, indent=2)
        outputs.append(output_path)

    if outputs:
        print(f"Converted {len(outputs)} distId dataset(s)")

    return outputs

def main() -> None:
    #NOTE: PATH YET TO BE FINALISED.
    # It should point to the root folder containing the state-wide GML folders.
    gml_src = Path(DEFAULT_GML_INPUT_PATH).expanduser().resolve()
    geojson_root = Path(DEFAULT_GEOJSON_OUTPUT_PATH).expanduser().resolve() if DEFAULT_GEOJSON_OUTPUT_PATH is not None else (gml_src / "geojson")

    if not gml_src.is_dir():
        raise SystemExit(f"Expected a directory containing state folders: {gml_src}")

    # Recursively gets all GML files across the state folders.
    gml_files = iter_gml_files(gml_src)
    if not gml_files:
        raise SystemExit(f"No .gml files found in {gml_src}")

    outputs = []
    grouped: dict[str, list[dict]] = {}
    for gml_file in gml_files:
        try:
            tree = ET.parse(str(gml_file))
            root = tree.getroot()
            root.set("sourceFile", gml_file.name)
            feature_collection = build_feature_collection(root)
            dist_id = (feature_collection.get("metadata") or {}).get("distId") or gml_file.stem
            grouped.setdefault(dist_id, []).append(feature_collection)
        except Exception as exc:  # pragma: no cover - robustness for batch runs
            print(f"Failed to convert {gml_file}: {exc}", file=sys.stderr)

    geojson_root.mkdir(parents=True, exist_ok=True)
    for dist_id, feature_collections in grouped.items():
        output_path = get_distid_dataset_path(dist_id, geojson_root)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(feature_collections, handle, indent=2)
        outputs.append(output_path)

    if outputs:
        print(f"Converted {len(outputs)} distId dataset(s)")


if __name__ == "__main__":
    main()

