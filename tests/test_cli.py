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


def test_resolve_model_success(tmp_path):
    """resolve-model returns matching fully-qualified IDs."""
    manifest_path = tmp_path / "manifest.json"
    manifest_data = {
        "nodes": {
            "model.pkg.stg_customers": {"name": "stg_customers"},
            "seed.pkg.raw_customers": {"name": "raw_customers"},
        },
        "sources": {
            "source.pkg.raw.raw_customers": {"name": "raw_customers"},
        },
    }
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "resolve-model",
            "--name",
            "raw_customers",
            "--manifest",
            str(manifest_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "seed.pkg.raw_customers" in result.output
    assert "source.pkg.raw.raw_customers" in result.output


def test_resolve_model_no_matches(tmp_path):
    """resolve-model exits with code 1 when nothing matches."""
    manifest_path = tmp_path / "manifest.json"
    manifest_data = {
        "nodes": {"model.pkg.stg_customers": {"name": "stg_customers"}},
        "sources": {},
    }
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "resolve-model",
            "--name",
            "raw_customers",
            "--manifest",
            str(manifest_path),
        ],
    )

    assert result.exit_code == 1
    assert "No matches found" in result.output


def test_resolve_model_missing_manifest():
    """resolve-model exits with code 1 when manifest path is invalid."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "resolve-model",
            "--name",
            "raw_customers",
            "--manifest",
            "does-not-exist.json",
        ],
    )

    assert result.exit_code == 1
    assert "Manifest file not found" in result.output
