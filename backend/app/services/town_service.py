import pandas as pd

from app.gen_cont_tables import load_locations


def get_towns() -> list[dict]:
    locations = load_locations()
    return locations.drop(columns="geometry").rename(
        columns={"name": "name", "state": "state", "is_coastal": "is_coastal"}
    ).to_dict(orient="records")


def get_town(name: str) -> dict:
    locations = load_locations()
    matches = locations[locations["name"].str.casefold() == name.casefold()]
    if matches.empty:
        raise KeyError(name)
    row = matches.iloc[0]
    return {
        "name": row["name"],
        "state": row["state"],
        "is_coastal": bool(row["is_coastal"]),
        "latitude": float(row.geometry.y),
        "longitude": float(row.geometry.x),
    }
