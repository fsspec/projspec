"""Tests for the CroissantDataset project spec and CroissantRecordSet content class."""

import json
import os
import textwrap

import pytest

import projspec
from projspec.proj.datapackage import CroissantDataset


# ---------------------------------------------------------------------------
# Helpers (copied from test_new_specs.py pattern)
# ---------------------------------------------------------------------------


def write_files(tmpdir, files: dict[str, str]) -> str:
    path = str(tmpdir)
    for rel, content in files.items():
        full = os.path.join(path, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(textwrap.dedent(content))
    return path


def make_proj(tmpdir, files: dict[str, str]):
    path = write_files(tmpdir, files)
    return projspec.Project(path)


def raw_spec(cls, proj):
    """Instantiate a spec bypassing __init__'s match() call."""
    inst = cls.__new__(cls)
    inst.proj = proj
    inst._contents = None
    inst._artifacts = None
    inst._matched_file = None
    return inst


# ---------------------------------------------------------------------------
# Minimal valid Croissant document used across several tests
# ---------------------------------------------------------------------------

MINIMAL_CROISSANT = {
    "@context": {
        "@language": "en",
        "@vocab": "https://schema.org/",
        "cr": "http://mlcommons.org/schema/",
        "dct": "http://purl.org/dc/terms/",
    },
    "@type": "sc:Dataset",
    "name": "test-dataset",
    "description": "A test dataset for projspec.",
    "license": "https://creativecommons.org/licenses/by/4.0/",
    "url": "https://example.com/test-dataset",
    "dct:conformsTo": "http://mlcommons.org/croissant/1.0",
    "distribution": [
        {
            "@type": "cr:FileObject",
            "@id": "data.csv",
            "contentUrl": "data.csv",
            "encodingFormat": "text/csv",
        }
    ],
    "recordSet": [
        {
            "@type": "cr:RecordSet",
            "@id": "records",
            "name": "records",
            "description": "The main record set.",
            "field": [
                {
                    "@type": "cr:Field",
                    "@id": "records/id",
                    "name": "id",
                    "dataType": "sc:Integer",
                },
                {
                    "@type": "cr:Field",
                    "@id": "records/label",
                    "name": "label",
                    "dataType": "sc:Text",
                },
            ],
        }
    ],
}


# ---------------------------------------------------------------------------
# match() tests
# ---------------------------------------------------------------------------


class TestCroissantMatch:
    def test_match_positive_croissant_json(self, tmpdir):
        """croissant.json with conformsTo marker is detected."""
        files = {"croissant.json": json.dumps(MINIMAL_CROISSANT)}
        proj = make_proj(tmpdir, files)
        spec = raw_spec(CroissantDataset, proj)
        assert spec.match()
        assert spec._matched_file == "croissant.json"

    def test_match_positive_metadata_json(self, tmpdir):
        """metadata.json with conformsTo marker is also detected."""
        files = {"metadata.json": json.dumps(MINIMAL_CROISSANT)}
        proj = make_proj(tmpdir, files)
        spec = raw_spec(CroissantDataset, proj)
        assert spec.match()
        assert spec._matched_file == "metadata.json"

    def test_match_negative_no_json(self, tmpdir):
        """Empty directory does not match."""
        proj = make_proj(tmpdir, {})
        spec = raw_spec(CroissantDataset, proj)
        assert not spec.match()

    def test_match_negative_plain_json(self, tmpdir):
        """A plain JSON file without the Croissant conformsTo marker is not detected."""
        files = {"data.json": json.dumps({"key": "value"})}
        proj = make_proj(tmpdir, files)
        spec = raw_spec(CroissantDataset, proj)
        assert not spec.match()

    def test_match_negative_datapackage(self, tmpdir):
        """datapackage.json (Frictionless) is not treated as Croissant."""
        files = {
            "datapackage.json": json.dumps(
                {"name": "pkg", "resources": [{"name": "r", "path": "r.csv"}]}
            )
        }
        proj = make_proj(tmpdir, files)
        spec = raw_spec(CroissantDataset, proj)
        assert not spec.match()

    def test_match_positive_via_project(self, tmpdir):
        """Project.resolve() picks up CroissantDataset in its specs."""
        files = {"croissant.json": json.dumps(MINIMAL_CROISSANT)}
        proj = make_proj(tmpdir, files)
        assert "croissant_dataset" in proj.specs


# ---------------------------------------------------------------------------
# parse() tests
# ---------------------------------------------------------------------------


class TestCroissantParse:
    FILES = {"croissant.json": json.dumps(MINIMAL_CROISSANT)}

    def _spec(self, tmpdir):
        proj = make_proj(tmpdir, self.FILES)
        spec = raw_spec(CroissantDataset, proj)
        assert spec.match()
        spec.parse()
        return spec

    def test_parse_descriptive_metadata(self, tmpdir):
        spec = self._spec(tmpdir)
        assert "descriptive_metadata" in spec._contents
        dm = spec._contents["descriptive_metadata"]
        assert dm.meta["name"] == "test-dataset"
        assert "description" in dm.meta

    def test_parse_license(self, tmpdir):
        spec = self._spec(tmpdir)
        assert "license" in spec._contents
        lic = spec._contents["license"]
        assert "creativecommons" in lic.url

    def test_parse_record_sets(self, tmpdir):
        spec = self._spec(tmpdir)
        assert "croissant_record_set" in spec._contents
        rs_map = spec._contents["croissant_record_set"]
        assert "records" in rs_map

    def test_parse_record_set_fields(self, tmpdir):
        spec = self._spec(tmpdir)
        rs = spec._contents["croissant_record_set"]["records"]
        assert "id" in rs.fields
        assert "label" in rs.fields

    def test_parse_record_set_description(self, tmpdir):
        spec = self._spec(tmpdir)
        rs = spec._contents["croissant_record_set"]["records"]
        assert rs.description == "The main record set."

    def test_parse_no_record_sets(self, tmpdir):
        """Documents without recordSet should parse without error."""
        doc = dict(MINIMAL_CROISSANT)
        doc.pop("recordSet")
        files = {"croissant.json": json.dumps(doc)}
        proj = make_proj(tmpdir, files)
        spec = raw_spec(CroissantDataset, proj)
        assert spec.match()
        spec.parse()
        assert "descriptive_metadata" in spec._contents
        assert "croissant_record_set" not in spec._contents

    def test_parse_citation(self, tmpdir):
        """citeAs is parsed into a Citation content object."""
        doc = dict(MINIMAL_CROISSANT)
        doc["citeAs"] = "@article{test2024, title={Test}}"
        files = {"croissant.json": json.dumps(doc)}
        proj = make_proj(tmpdir, files)
        spec = raw_spec(CroissantDataset, proj)
        assert spec.match()
        spec.parse()
        assert "citation" in spec._contents
        assert "Test" in spec._contents["citation"].meta["citeAs"]

    def test_parse_license_dict(self, tmpdir):
        """license expressed as a dict with @id is handled."""
        doc = dict(MINIMAL_CROISSANT)
        doc["license"] = {"@id": "https://opensource.org/licenses/MIT", "name": "MIT"}
        files = {"croissant.json": json.dumps(doc)}
        proj = make_proj(tmpdir, files)
        spec = raw_spec(CroissantDataset, proj)
        assert spec.match()
        spec.parse()
        lic = spec._contents["license"]
        assert lic.shortname == "MIT"

    def test_parse_multiple_record_sets(self, tmpdir):
        """Multiple RecordSets are all captured."""
        doc = dict(MINIMAL_CROISSANT)
        doc["recordSet"] = [
            {
                "@type": "cr:RecordSet",
                "@id": "train",
                "name": "train",
                "field": [{"@type": "cr:Field", "@id": "train/x", "name": "x"}],
            },
            {
                "@type": "cr:RecordSet",
                "@id": "test",
                "name": "test",
                "field": [{"@type": "cr:Field", "@id": "test/y", "name": "y"}],
            },
        ]
        files = {"croissant.json": json.dumps(doc)}
        proj = make_proj(tmpdir, files)
        spec = raw_spec(CroissantDataset, proj)
        assert spec.match()
        spec.parse()
        rs_map = spec._contents["croissant_record_set"]
        assert "train" in rs_map
        assert "test" in rs_map
        assert "x" in rs_map["train"].fields
        assert "y" in rs_map["test"].fields


# ---------------------------------------------------------------------------
# CroissantRecordSet content class tests
# ---------------------------------------------------------------------------


class TestCroissantRecordSet:
    def test_import(self):
        from projspec.content.data import CroissantRecordSet  # noqa: F401

    def test_public_import(self):
        from projspec.content import CroissantRecordSet  # noqa: F401

    def test_fields(self, tmpdir):
        files = {"croissant.json": json.dumps(MINIMAL_CROISSANT)}
        proj = make_proj(tmpdir, files)
        from projspec.content.data import CroissantRecordSet

        rs = CroissantRecordSet(
            proj=proj, name="rs", description="desc", fields=["a", "b"]
        )
        assert rs.name == "rs"
        assert rs.description == "desc"
        assert rs.fields == ["a", "b"]

    def test_to_dict(self, tmpdir):
        files = {"croissant.json": json.dumps(MINIMAL_CROISSANT)}
        proj = make_proj(tmpdir, files)
        from projspec.content.data import CroissantRecordSet

        rs = CroissantRecordSet(proj=proj, name="rs", fields=["x"])
        d = rs.to_dict()
        assert d["name"] == "rs"
        assert d["fields"] == ["x"]


# ---------------------------------------------------------------------------
# _create() / round-trip test
# ---------------------------------------------------------------------------


class TestCroissantCreate:
    def test_create_writes_file(self, tmp_path):
        CroissantDataset._create(str(tmp_path))
        assert (tmp_path / "croissant.json").exists()

    def test_create_valid_json(self, tmp_path):
        CroissantDataset._create(str(tmp_path))
        with open(tmp_path / "croissant.json") as f:
            doc = json.load(f)
        assert "dct:conformsTo" in doc
        assert "mlcommons.org/croissant" in doc["dct:conformsTo"]

    def test_create_detected_by_project(self, tmp_path):
        CroissantDataset._create(str(tmp_path))
        proj = projspec.Project(str(tmp_path))
        assert "croissant_dataset" in proj.specs

    def test_roundtrip_to_dict(self, tmp_path):
        CroissantDataset._create(str(tmp_path))
        proj = projspec.Project(str(tmp_path))
        d = proj.to_dict(compact=False)
        proj2 = projspec.Project.from_dict(d)
        assert "croissant_dataset" in proj2.specs
