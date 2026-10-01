from pathlib import Path

from app.services.loaders.gml import iter_gml_files, relative_source


def test_gml_loader_uses_explicit_data_dir(tmp_path: Path):
    root = tmp_path / "uploaded"
    path = root / "NT_GMLs" / "bulletin.gml"
    path.parent.mkdir(parents=True)
    path.write_text("<gml />")

    files = list(iter_gml_files(data_dir=root))

    assert files == [("NT", path)]
    assert relative_source(path, root) == "NT_GMLs/bulletin.gml"
