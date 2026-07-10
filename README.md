# dbt-colibri

dbt-colibri is the shared lineage toolkit for Newday dbt projects.
It generates column-level lineage, answers blast-radius questions, and powers the reusable PR comment workflow used by the dbt repos.

## What it does

- Extracts column-level lineage from dbt artifacts
- Generates a browsable HTML lineage dashboard
- Merges artifacts across dbt projects
- Validates cross-project lineage
- Posts reusable PR blast-radius comments for dbt repos

## Key features

- `colibri generate` for lineage reports
- `colibri blast-radius` for downstream impact analysis
- `colibri merge-artifacts` for multi-project lineage
- `colibri publish-artifacts` to publish repo artifacts and regenerate the master catalog
- `colibri validate-cross-project` for merged graph validation
- Reusable GitHub workflow: `.github/workflows/dbt-model-change-comment.yml`

## Example commands

Generate a report:

```bash
colibri generate --manifest target/manifest.json --catalog target/catalog.json --output-dir dist
```

Expected output:

```text
✅ Report completed!
  📁 JSON: dist/colibri-manifest.json
  🌐 HTML: dist/index.html
```

Inspect blast radius:

```bash
colibri blast-radius --model model.analytics.customers --columns customer_id --format json
```

Expected output:

```json
{
  "source_model": "model.analytics.customers",
  "affected_items": [...],
  "summary": {
    "affected_models_count": 3,
    "affected_columns_count": 5
  }
}
```

Merge multiple projects:

```bash
colibri merge-artifacts --project-artifacts project_a target/manifest.json target/catalog.json --project-artifacts project_b target/manifest.json target/catalog.json --output-dir dist/_merged_artifacts
```

Expected output:

```text
✅ Artifacts merged
  📄 Manifest: dist/_merged_artifacts/manifest.json
  📄 Catalog:  dist/_merged_artifacts/catalog.json
```

Publish repo artifacts and refresh the master catalog:

```bash
colibri publish-artifacts --repo-name jaffleshop --source-manifest target/manifest.json --source-catalog target/catalog.json --artifacts-root artifacts --branch artifacts-sync
```

Expected output:

```text
✅ Published repo artifacts
  📄 Repo manifest: artifacts/jaffleshop/manifest.json
  📄 Repo catalog:   artifacts/jaffleshop/catalog.json
  📄 Master manifest: artifacts/master/manifest.json
  📄 Master catalog:  artifacts/master/catalog.json
  ✅ Pushed artifacts branch: artifacts-sync
```

## PR workflow

This repo exposes the reusable GitHub Actions workflow for dbt repos:

`.github/workflows/dbt-model-change-comment.yml`

It takes:

- `dbt_profile_name`
- `base_sha`
- `head_sha`
- `pr_number`

## Published artifact branch

dbt repos publish their latest `manifest.json` and `catalog.json` into the
`artifacts-sync` branch under:

- `artifacts/<repo-name>/manifest.json`
- `artifacts/<repo-name>/catalog.json`
- `artifacts/master/manifest.json`
- `artifacts/master/catalog.json`

The PR blast-radius workflow prefers `artifacts/master/*` and falls back to the
legacy merged output if the published branch is not available yet.

## Development

```bash
uv sync --dev
pytest
ruff format
```
