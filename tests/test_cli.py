import os
import json
import pytest
from click.testing import CliRunner
from dbt_colibri.cli.cli import cli


@pytest.fixture
def test_data_dir(dbt_valid_test_data_dir):
    if dbt_valid_test_data_dir is None:
        pytest.skip("No valid versioned test data present")
    return dbt_valid_test_data_dir


@pytest.fixture
def test_output_dir(tmp_path):
    """Create a temporary directory for CLI output"""
    return str(tmp_path)


def test_generate_success(test_data_dir, test_output_dir):
    """Test successful report generation using default CLI arguments"""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate",
            "--manifest", os.path.join(test_data_dir, "manifest.json"),
            "--catalog", os.path.join(test_data_dir, "catalog.json"),
            "--output-dir", test_output_dir
        ]
    )

    assert result.exit_code == 0, result.output
    assert os.path.exists(os.path.join(test_output_dir, "colibri-manifest.json"))
    assert os.path.exists(os.path.join(test_output_dir, "index.html"))


def test_generate_missing_manifest(test_data_dir, test_output_dir):
    """Test CLI behavior when manifest file is missing"""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate",
            "--manifest", os.path.join(test_data_dir, "nonexistent_manifest.json"),
            "--catalog", os.path.join(test_data_dir, "catalog.json"),
            "--output-dir", test_output_dir
        ]
    )

    assert result.exit_code == 1
    


def test_generate_missing_catalog(test_data_dir, test_output_dir):
    """Test CLI behavior when catalog file is missing"""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate",
            "--manifest", os.path.join(test_data_dir, "manifest.json"),
            "--catalog", os.path.join(test_data_dir, "nonexistent_catalog.json"),
            "--output-dir", test_output_dir
        ]
    )

    assert result.exit_code == 1



def test_generate_raises_exception(monkeypatch, test_data_dir, test_output_dir):
    """Simulate internal exception to verify error handling"""
    from dbt_colibri.cli import cli as cli_module

    def raise_exception(*args, **kwargs):
        raise RuntimeError("Simulated failure")

    monkeypatch.setattr(cli_module, "DbtColumnLineageExtractor", raise_exception)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate",
            "--manifest", os.path.join(test_data_dir, "manifest.json"),
            "--catalog", os.path.join(test_data_dir, "catalog.json"),
            "--output-dir", test_output_dir
        ]
    )

    assert result.exit_code == 1


def test_generate_with_bigquery_adapter(test_output_dir):
    """Test successful report generation with BigQuery adapter type detection"""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate",
            "--manifest", "tests/test_data/bigquery/manifest.json",
            "--catalog", "tests/test_data/bigquery/catalog.json",
            "--output-dir", test_output_dir
        ]
    )

    assert result.exit_code == 0, result.output
    assert os.path.exists(os.path.join(test_output_dir, "colibri-manifest.json"))
    assert os.path.exists(os.path.join(test_output_dir, "index.html"))


def test_generate_with_duckdb_adapter(test_output_dir):
    """Test successful report generation with DuckDB adapter type detection"""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate",
            "--manifest", "tests/test_data/duckdb/manifest.json",
            "--catalog", "tests/test_data/duckdb/catalog.json",
            "--output-dir", test_output_dir
        ]
    )

    assert result.exit_code == 0, result.output
    assert os.path.exists(os.path.join(test_output_dir, "colibri-manifest.json"))
    assert os.path.exists(os.path.join(test_output_dir, "index.html"))


def test_merge_artifacts_success(tmp_path):
    manifest_a = {
        "metadata": {"adapter_type": "duckdb"},
        "nodes": {
            "model.alpha.customers": {
                "unique_id": "model.alpha.customers",
                "resource_type": "model",
                "database": "alpha",
                "schema": "main",
                "name": "customers",
                "relation_name": '"alpha"."main"."customers"',
                "config": {"materialized": "view"},
                "depends_on": {"nodes": []},
            }
        },
        "sources": {},
        "parent_map": {"model.alpha.customers": []},
        "child_map": {"model.alpha.customers": []},
        "group_map": {},
    }
    manifest_b = {
        "metadata": {"adapter_type": "duckdb"},
        "nodes": {
            "model.beta.orders": {
                "unique_id": "model.beta.orders",
                "resource_type": "model",
                "database": "beta",
                "schema": "main",
                "name": "orders",
                "relation_name": '"beta"."main"."orders"',
                "config": {"materialized": "view"},
                "depends_on": {"nodes": []},
            }
        },
        "sources": {},
        "parent_map": {"model.beta.orders": []},
        "child_map": {"model.beta.orders": []},
        "group_map": {},
    }
    catalog_a = {
        "metadata": {"adapter_type": "duckdb"},
        "nodes": {
            "model.alpha.customers": {
                "unique_id": "model.alpha.customers",
                "metadata": {"database": "alpha", "schema": "main", "name": "customers"},
                "columns": {"customer_id": {"type": "INTEGER"}},
            }
        },
        "sources": {},
    }
    catalog_b = {
        "metadata": {"adapter_type": "duckdb"},
        "nodes": {
            "model.beta.orders": {
                "unique_id": "model.beta.orders",
                "metadata": {"database": "beta", "schema": "main", "name": "orders"},
                "columns": {"order_id": {"type": "INTEGER"}},
            }
        },
        "sources": {},
    }

    manifest_a_path = tmp_path / "manifest_a.json"
    catalog_a_path = tmp_path / "catalog_a.json"
    manifest_b_path = tmp_path / "manifest_b.json"
    catalog_b_path = tmp_path / "catalog_b.json"
    out_dir = tmp_path / "merged"

    manifest_a_path.write_text(json.dumps(manifest_a), encoding="utf-8")
    catalog_a_path.write_text(json.dumps(catalog_a), encoding="utf-8")
    manifest_b_path.write_text(json.dumps(manifest_b), encoding="utf-8")
    catalog_b_path.write_text(json.dumps(catalog_b), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "merge-artifacts",
            "--project-artifacts",
            "alpha",
            str(manifest_a_path),
            str(catalog_a_path),
            "--project-artifacts",
            "beta",
            str(manifest_b_path),
            str(catalog_b_path),
            "--output-dir",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (out_dir / "manifest.json").exists()
    assert (out_dir / "catalog.json").exists()


def test_validate_cross_project_accepts_source_only(tmp_path):
    manifest_path = tmp_path / "colibri-manifest.json"
    manifest_data = {
        "nodes": {
            "source.consumer.nonexistent_upstream.customers": {},
            "model.consumer.orders": {},
        },
        "lineage": {
            "edges": [
                {
                    "source": "source.consumer.nonexistent_upstream.customers",
                    "target": "model.consumer.orders",
                }
            ]
        },
    }
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "validate-cross-project",
            "--manifest",
            str(manifest_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Accepted source-only cases: 1" in result.output
