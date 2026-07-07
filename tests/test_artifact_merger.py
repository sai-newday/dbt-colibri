import json
import pytest

from dbt_colibri.lineage_extractor.artifact_merger import merge_project_artifacts


def _project_manifest(project: str, relation: str, include_source: bool = False):
    manifest = {
        "metadata": {"adapter_type": "duckdb", "project_name": project},
        "nodes": {
            f"model.{project}.customers": {
                "unique_id": f"model.{project}.customers",
                "resource_type": "model",
                "database": project,
                "schema": "main",
                "name": "customers",
                "relation_name": relation,
                "compiled_code": "select 1 as customer_id",
                "config": {"materialized": "view"},
                "depends_on": {"nodes": []},
            }
        },
        "sources": {},
        "parent_map": {f"model.{project}.customers": []},
        "child_map": {f"model.{project}.customers": []},
        "group_map": {},
    }
    if include_source:
        manifest["sources"]["source.baffleshop.jaffleshop.customers"] = {
            "unique_id": "source.baffleshop.jaffleshop.customers",
            "resource_type": "source",
            "database": "baffleshop",
            "schema": "main",
            "name": "customers",
            "relation_name": '"baffleshop"."main"."customers"',
        }
        manifest["child_map"]["source.baffleshop.jaffleshop.customers"] = [
            "model.baffleshop.customers"
        ]
        manifest["parent_map"]["model.baffleshop.customers"] = [
            "source.baffleshop.jaffleshop.customers"
        ]
        manifest["nodes"]["model.baffleshop.customers"] = {
            "unique_id": "model.baffleshop.customers",
            "resource_type": "model",
            "database": "baffleshop",
            "schema": "main",
            "name": "customers",
            "relation_name": '"baffleshop"."main"."customers"',
            "compiled_code": "select * from source",
            "config": {"materialized": "view"},
            "depends_on": {"nodes": ["source.baffleshop.jaffleshop.customers"]},
        }
    return manifest


def _project_catalog(project: str):
    return {
        "metadata": {"adapter_type": "duckdb"},
        "nodes": {
            f"model.{project}.customers": {
                "unique_id": f"model.{project}.customers",
                "metadata": {
                    "database": project,
                    "schema": "main",
                    "name": "customers",
                    "type": "VIEW",
                },
                "columns": {"customer_id": {"type": "INTEGER"}},
            }
        },
        "sources": {},
    }


def test_merge_project_artifacts_adds_relation_aliases(tmp_path):
    manifest_a = _project_manifest("jaffleshop", '"jaffleshop"."main"."customers"')
    manifest_b = _project_manifest("jaffleshop", '"baffleshop"."main"."customers"')

    catalog_a = _project_catalog("jaffleshop")
    catalog_b = _project_catalog("jaffleshop")
    catalog_b["nodes"]["model.jaffleshop.customers"]["metadata"]["database"] = "baffleshop"

    manifest_a_path = tmp_path / "a_manifest.json"
    catalog_a_path = tmp_path / "a_catalog.json"
    manifest_b_path = tmp_path / "b_manifest.json"
    catalog_b_path = tmp_path / "b_catalog.json"

    manifest_a_path.write_text(json.dumps(manifest_a), encoding="utf-8")
    catalog_a_path.write_text(json.dumps(catalog_a), encoding="utf-8")
    manifest_b_path.write_text(json.dumps(manifest_b), encoding="utf-8")
    catalog_b_path.write_text(json.dumps(catalog_b), encoding="utf-8")

    merged_manifest, merged_catalog, normalized = merge_project_artifacts(
        [
            ("jaffleshop", str(manifest_a_path), str(catalog_a_path)),
            ("baffleshop", str(manifest_b_path), str(catalog_b_path)),
        ],
        strict=True,
        link_cross_project_sources=False,
    )

    assert normalized == 0
    aliases = merged_manifest["nodes"]["model.jaffleshop.customers"].get(
        "x_colibri_relation_aliases", []
    )
    assert '"jaffleshop"."main"."customers"' in aliases
    assert '"baffleshop"."main"."customers"' in aliases
    table_aliases = merged_catalog["nodes"]["model.jaffleshop.customers"].get(
        "x_colibri_table_aliases", []
    )
    assert any(a["database"] == "jaffleshop" for a in table_aliases)
    assert any(a["database"] == "baffleshop" for a in table_aliases)


def test_merge_project_artifacts_strict_collision_raises(tmp_path):
    manifest_a = _project_manifest("alpha", '"alpha"."main"."customers"')
    manifest_b = _project_manifest("beta", '"beta"."other"."customers"')
    shared_id = "model.missing_owner.customers"
    manifest_a["nodes"][shared_id] = dict(manifest_a["nodes"].pop("model.alpha.customers"))
    manifest_b["nodes"][shared_id] = dict(manifest_b["nodes"].pop("model.beta.customers"))

    catalog_a = _project_catalog("alpha")
    catalog_b = _project_catalog("beta")
    catalog_a["nodes"][shared_id] = dict(catalog_a["nodes"].pop("model.alpha.customers"))
    catalog_b["nodes"][shared_id] = dict(catalog_b["nodes"].pop("model.beta.customers"))

    manifest_a_path = tmp_path / "a_manifest.json"
    catalog_a_path = tmp_path / "a_catalog.json"
    manifest_b_path = tmp_path / "b_manifest.json"
    catalog_b_path = tmp_path / "b_catalog.json"

    manifest_a_path.write_text(json.dumps(manifest_a), encoding="utf-8")
    catalog_a_path.write_text(json.dumps(catalog_a), encoding="utf-8")
    manifest_b_path.write_text(json.dumps(manifest_b), encoding="utf-8")
    catalog_b_path.write_text(json.dumps(catalog_b), encoding="utf-8")

    with pytest.raises(ValueError):
        merge_project_artifacts(
            [
                ("a", str(manifest_a_path), str(catalog_a_path)),
                ("b", str(manifest_b_path), str(catalog_b_path)),
            ],
            strict=True,
            link_cross_project_sources=False,
        )


def test_link_cross_project_sources_rewrites_when_upstream_exists(tmp_path):
    import json

    manifest_a = _project_manifest("jaffleshop", '"jaffleshop"."main"."customers"')
    manifest_b = _project_manifest("baffleshop", '"baffleshop"."main"."customers"', include_source=True)
    catalog_a = _project_catalog("jaffleshop")
    catalog_b = _project_catalog("baffleshop")
    catalog_b["sources"] = {
        "source.baffleshop.jaffleshop.customers": {
            "unique_id": "source.baffleshop.jaffleshop.customers",
            "metadata": {
                "database": "baffleshop",
                "schema": "main",
                "name": "customers",
            },
            "columns": {"customer_id": {"type": "INTEGER"}},
        }
    }

    manifest_a_path = tmp_path / "a_manifest.json"
    catalog_a_path = tmp_path / "a_catalog.json"
    manifest_b_path = tmp_path / "b_manifest.json"
    catalog_b_path = tmp_path / "b_catalog.json"
    manifest_a_path.write_text(json.dumps(manifest_a), encoding="utf-8")
    catalog_a_path.write_text(json.dumps(catalog_a), encoding="utf-8")
    manifest_b_path.write_text(json.dumps(manifest_b), encoding="utf-8")
    catalog_b_path.write_text(json.dumps(catalog_b), encoding="utf-8")

    merged_manifest, _, normalized = merge_project_artifacts(
        [
            ("a", str(manifest_a_path), str(catalog_a_path)),
            ("b", str(manifest_b_path), str(catalog_b_path)),
        ],
        strict=True,
        link_cross_project_sources=True,
    )

    assert normalized == 1
    assert "source.baffleshop.jaffleshop.customers" not in merged_manifest["sources"]
    assert "model.jaffleshop.customers" in merged_manifest["child_map"]