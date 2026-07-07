
# Newday Column Lineage

Newday-specific CLI tooling and a self-hostable dashboard for extracting and visualizing **column-level lineage** from dbt projects.

Built for internal data teams who need transparent lineage tracking for development, release reviews, and production change impact analysis.

## Why Newday Column Lineage?

- **Complete visibility**: Track how each column flows through dbt transformations
- **Fast and lightweight**: Generate reports quickly from existing dbt artifacts
- **Self-hosted**: Run fully within Newday environments

## Quick Start

### Installation

Install this project in your Newday Python environment from the internal source used by your team.

### Basic Usage

1. Run dbt to generate required artifacts:
   ```bash
   dbt compile
   dbt docs generate
   ```

2. Generate lineage report:
   ```bash
   colibri generate
   ```

3. View results: open `dist/index.html` in your browser.

You can also use `dbt run` or `dbt build` to generate `manifest.json`.

## CLI Commands

### `colibri generate`

Generate column lineage reports from dbt artifacts.

```bash
colibri generate [OPTIONS]
```

Options:
- `--manifest`: Path to dbt `manifest.json` (default: `target/manifest.json`)
- `--catalog`: Path to dbt `catalog.json` (default: `target/catalog.json`)
- `--output-dir`: Output directory (default: `dist/`)
- `--light`: Excludes heavier attributes such as compiled SQL for large projects

### `colibri blast-radius`

Analyze downstream impact of column changes in a model or source.

```bash
colibri blast-radius [OPTIONS]
```

Options:
- `--model`: Fully qualified model/source ID (required)
- `--columns`: Comma-separated column names; omit for model-level lineage
- `--manifest`: Path to dbt `manifest.json` (default: `target/manifest.json`)
- `--catalog`: Path to dbt `catalog.json` (default: `target/catalog.json`)
- `--format`: `json` or `text` (default: `json`)
- `--max-depth`: Maximum depth to traverse (default: unlimited)
- `--debug`: Enable debug logging

Example:

```bash
colibri blast-radius --model model.analytics.customers --columns customer_id --format json
```

### `colibri resolve-model`

Resolve a short model/source table name to matching fully qualified IDs.

```bash
colibri resolve-model --name raw_customers [OPTIONS]
```

Options:
- `--name`: Short model/source table name to resolve (required)
- `--manifest`: Path to dbt `manifest.json` (default: `target/manifest.json`)

### `colibri merge-artifacts`

Merge manifest/catalog files from multiple dbt projects.

```bash
colibri merge-artifacts [OPTIONS]
```

Options:
- `--project-artifacts`: Repeatable triple: `PROJECT MANIFEST_PATH CATALOG_PATH` (required)
- `--output-dir`: Directory where merged artifacts are written (required)
- `--no-strict`: Allow unresolved collisions without failing
- `--link-cross-project-sources`: Rewrite cross-project sources to upstream models when available

### `colibri validate-cross-project`

Validate cross-project lineage in generated `colibri-manifest.json`.

```bash
colibri validate-cross-project --manifest dist/colibri-manifest.json [OPTIONS]
```

Options:
- `--manifest`: Path to generated `colibri-manifest.json` (required)
- `--format`: `text` or `json` (default: `text`)

## Output Files

- `colibri-manifest.json`: lineage data
- `index.html`: interactive visualization dashboard

## Project Structure

```text
your-dbt-project/
|-- target/
|   |-- manifest.json
|   `-- catalog.json
`-- dist/
    |-- index.html
    `-- colibri-manifest.json
```

## Multi-Project Usage

1. Merge dbt artifacts from multiple projects.
2. Generate HTML from merged artifacts.
3. Validate cross-project lineage using generated output.

Example paths in this repository:
- `combined-lineage/dist/index.html`
- `combined-lineage/dist/colibri-manifest.json`
- `combined-lineage/dist/_merged_artifacts/manifest.json`
- `combined-lineage/dist/_merged_artifacts/catalog.json`

## CI/CD Integration

Use the workflow example in [docs/github_pages_example.yml](docs/github_pages_example.yml) as a starting point for publishing generated static output.

Typical pipeline flow:
1. Install dependencies.
2. Run `dbt compile` and `dbt docs generate`.
3. Run `colibri generate`.
4. Publish the `dist/` output.

## Technical Details

### Requirements

- Python versions tested: 3.9, 3.11, 3.13
- dbt-core versions tested: 1.8.x, 1.9.x, 1.10.x

### Supported dbt Adapters

- Snowflake
- BigQuery
- Redshift
- duckDB
- Postgres
- Databricks (SQL models)
- Athena
- Trino
- SQL Server (TSQL)
- ClickHouse
- Oracle
- StarRocks

### Architecture

This project uses:
- SQL parsing and lineage extraction
- dbt artifacts (`manifest.json`, `catalog.json`) for metadata
- static HTML output for simple deployment

## Contributing

Contributions are welcome through your team's normal development and review process.

### Development Setup

```bash
# Install development dependencies
uv sync --dev

# Run tests
pytest

# Format code
ruff format
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
