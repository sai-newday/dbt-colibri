# src/dbt_colibri/cli/cli.py

import click
import os
import sys
import json
from ..lineage_extractor.extractor import DbtColumnLineageExtractor
from ..lineage_extractor.artifact_merger import merge_project_artifacts, write_merged_artifacts
from ..lineage_extractor.cross_project_validator import validate_cross_project_lineage
from ..report.generator import DbtColibriReportGenerator
from ..report.blast_radius import BlastRadiusAnalyzer
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

COLIBRI_LOGO = r"""
 ______     ______     __         __     ______     ______     __    
/\  ___\   /\  __ \   /\ \       /\ \   /\  == \   /\  == \   /\ \   
\ \ \____  \ \ \/\ \  \ \ \____  \ \ \  \ \  __<   \ \  __<   \ \ \  
 \ \_____\  \ \_____\  \ \_____\  \ \_\  \ \_____\  \ \_\ \_\  \ \_\ 
  \/_____/   \/_____/   \/_____/   \/_/   \/_____/   \/_/ /_/   \/_/ 
"""

try:
    __version__ = version("dbt-colibri")
except PackageNotFoundError:
    __version__ = "unknown"

@click.group()
@click.version_option(__version__, prog_name="dbt-colibri")
def cli():
    """dbt-colibri CLI tool"""
    click.echo(f"{COLIBRI_LOGO}\n")
    click.echo("Welcome to dbt-colibri 🐦")

    from ..utils.version_check import get_update_message

    update_msg = get_update_message(__version__)
    if update_msg:
        click.echo(click.style(update_msg, fg="yellow"))


def _find_matching_model_ids(manifest_data: dict, name: str) -> list[str]:
    """Return matching fully-qualified node IDs for an exact dbt node/table name."""
    target = name.strip().lower()
    if not target:
        return []

    all_nodes = {
        **manifest_data.get("nodes", {}),
        **manifest_data.get("sources", {}),
    }

    matches = []
    for node_id, node in all_nodes.items():
        node_name = (node.get("name") or "").lower()
        if node_name == target or node_id.lower().endswith(f".{target}"):
            matches.append(node_id)

    return sorted(set(matches))


@cli.command("resolve-model")
@click.option(
    "--name",
    type=str,
    required=True,
    help="Short model/source table name to resolve (e.g., raw_customers)",
)
@click.option(
    "--manifest",
    type=str,
    default="target/manifest.json",
    help="Path to dbt manifest.json file (default: target/manifest.json)",
)
def resolve_model_cmd(name, manifest):
    """Resolve a short model/source name to matching fully-qualified dbt node IDs."""
    if not os.path.exists(manifest):
        click.echo(f"❌ Manifest file not found at {manifest}")
        sys.exit(1)

    try:
        with open(manifest, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
    except Exception as e:
        click.echo(f"❌ Error reading manifest: {str(e)}")
        sys.exit(1)

    matches = _find_matching_model_ids(manifest_data, name)

    click.echo("")
    if not matches:
        click.echo(f"No matches found for '{name}'.")
        sys.exit(1)

    click.echo(f"Matching full IDs for '{name}':")
    for model_id in matches:
        click.echo(f"- {model_id}")

    click.echo("")
    click.echo(f"✅ Found {len(matches)} match(es)")
    sys.exit(0)


@cli.command("merge-artifacts")
@click.option(
    "--project-artifacts",
    type=(str, str, str),
    multiple=True,
    required=True,
    help="Repeatable triple: PROJECT MANIFEST_PATH CATALOG_PATH",
)
@click.option(
    "--output-dir",
    type=str,
    required=True,
    help="Directory where merged manifest.json and catalog.json will be written.",
)
@click.option(
    "--no-strict",
    is_flag=True,
    default=False,
    help="Allow unresolved collisions without failing.",
)
@click.option(
    "--link-cross-project-sources",
    is_flag=True,
    default=False,
    help="Rewrite cross-project sources to upstream models when those models exist.",
)
def merge_artifacts_cmd(project_artifacts, output_dir, no_strict, link_cross_project_sources):
    """Merge manifest/catalog pairs from multiple dbt projects into one artifact set."""
    if len(project_artifacts) < 2:
        click.echo("❌ At least two --project-artifacts entries are required")
        sys.exit(1)

    try:
        merged_manifest, merged_catalog, normalized_sources = merge_project_artifacts(
            project_artifacts=list(project_artifacts),
            strict=not no_strict,
            link_cross_project_sources=link_cross_project_sources,
        )
        manifest_path, catalog_path = write_merged_artifacts(
            Path(output_dir), merged_manifest, merged_catalog
        )

        click.echo("✅ Artifacts merged")
        click.echo(f"  📄 Manifest: {manifest_path}")
        click.echo(f"  📄 Catalog:  {catalog_path}")
        click.echo(f"  🔢 Manifest nodes: {len(merged_manifest.get('nodes', {}))}")
        click.echo(f"  🔢 Manifest sources: {len(merged_manifest.get('sources', {}))}")
        click.echo(f"  🔢 Catalog nodes: {len(merged_catalog.get('nodes', {}))}")
        click.echo(f"  🔢 Catalog sources: {len(merged_catalog.get('sources', {}))}")
        if link_cross_project_sources:
            click.echo(f"  🔁 Normalized cross-project sources: {normalized_sources}")
        sys.exit(0)
    except Exception as e:
        click.echo(f"❌ Error: {str(e)}")
        sys.exit(1)

@cli.command("generate")
@click.option(
    "--output-dir",
    type=str,
    default="dist",
    help="Directory to save both JSON and HTML files (default: dist)"
)
@click.option(
    "--manifest",
    type=str,
    default="target/manifest.json",
    help="Path to dbt manifest.json file (default: target/manifest.json)"
)
@click.option(
    "--catalog", 
    type=str,
    default="target/catalog.json",
    help="Path to dbt catalog.json file (default: target/catalog.json)"
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug-level logging"
)
@click.option(
    "--light",
    is_flag=True,
    default=False,
    help="Enable light mode (excludes compiled_code from output for smaller file size)"
)

def generate_report(output_dir, manifest, catalog, debug, light):
    """Generate a dbt-colibri lineage report with both JSON and HTML output."""
    import logging
    from ..utils import log

    try:


        # Set up logging based on flag
        log_level = logging.DEBUG if debug else logging.INFO
        logger = log.setup_logging(level=log_level)

        if not os.path.exists(manifest):
            logger.error(f"❌ Manifest file not found at {manifest}")
            sys.exit(1)
        if not os.path.exists(catalog):
            logger.error(f"❌ Catalog file not found at {catalog}")
            sys.exit(1)

        logger.info("Loading dbt manifest and catalog...")
        extractor = DbtColumnLineageExtractor(manifest, catalog)

        # --- Log version info (matches what will end up in metadata) ---
        manifest_meta = extractor.manifest.get("metadata", {})
        adapter = manifest_meta.get("adapter_type", "unknown")
        dbt_version = manifest_meta.get("dbt_version", "unknown")
        project = manifest_meta.get("project_name", "unknown")

        logger.info(
            "Running with configuration:\n"
            f"         dbt-colbri version : {extractor.colibri_version}\n"
            f"         dbt version        : {dbt_version}\n"
            f"         SQL dialect        : {adapter}\n"
            f"         dbt project        : {project}"
        )

        logger.info("Extracting lineage data...")
        report_generator = DbtColibriReportGenerator(
            extractor, light_mode=light
        )

        logger.info("Generating report...")
        report_generator.generate_report(output_dir=output_dir)
        click.echo("\n")
        click.echo("✅ Report completed!")
        click.echo(f"  📁 JSON: {output_dir}/colibri-manifest.json")
        click.echo(f"  🌐 HTML: {output_dir}/index.html")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        sys.exit(1)


@cli.command("blast-radius")
@click.option(
    "--model",
    type=str,
    required=True,
    help="Fully-qualified model/source ID to analyze (e.g., model.project.customers or source.project.source_name.table_name)",
)
@click.option(
    "--columns",
    type=str,
    required=False,
    help="Comma-separated list of column names (e.g., customer_id,email). Omit for model-level lineage.",
)
@click.option(
    "--manifest",
    type=str,
    default="target/manifest.json",
    help="Path to dbt manifest.json file (default: target/manifest.json)",
)
@click.option(
    "--catalog",
    type=str,
    default="target/catalog.json",
    help="Path to dbt catalog.json file (default: target/catalog.json)",
)
@click.option(
    "--format",
    type=click.Choice(["json", "text"]),
    default="json",
    help="Output format (default: json)",
)
@click.option(
    "--max-depth",
    type=int,
    default=None,
    help="Maximum depth to traverse (default: unlimited)",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug-level logging",
)
def blast_radius_cmd(model, columns, manifest, catalog, format, max_depth, debug):
    """Analyze the blast radius of a change to a dbt model's columns.
    
    This command shows all downstream models and columns that would be affected
    by changes to the specified columns in the source model.
    
    Example:
        colibri blast-radius --model model.analytics.customers --columns customer_id,email
    """
    import logging
    from ..utils import log

    try:
        # Set up logging based on flag
        log_level = logging.DEBUG if debug else logging.INFO
        logger = log.setup_logging(level=log_level)

        if not os.path.exists(manifest):
            logger.error(f"❌ Manifest file not found at {manifest}")
            sys.exit(1)
        if not os.path.exists(catalog):
            logger.error(f"❌ Catalog file not found at {catalog}")
            sys.exit(1)

        logger.info("Loading dbt manifest and catalog...")
        extractor = DbtColumnLineageExtractor(manifest, catalog)

        logger.info("Extracting lineage data...")
        lineage_data = extractor.extract_project_lineage()
        lineage_data["model_children"] = extractor.child_map

        # Parse columns when provided; otherwise run model-level lineage.
        column_list = [col.strip() for col in columns.split(",") if col.strip()] if columns else []

        if column_list:
            logger.info(f"Analyzing blast radius for {model} [{', '.join(column_list)}]...")
        else:
            logger.info(f"Analyzing model-level blast radius for {model}...")
        analyzer = BlastRadiusAnalyzer(lineage_data, logger=logger)
        result = analyzer.find_blast_radius(model, column_list, max_depth=max_depth)

        # Output results
        click.echo("\n")
        if format == "json":
            click.echo(json.dumps(result, indent=2))
        else:  # text format
            click.echo(analyzer.get_blast_radius_text(model, column_list, max_depth))

        click.echo("\n")
        click.echo("✅ Blast radius analysis completed!")
        sys.exit(0)

    except Exception as e:
        logger.error(f"❌ Error: {str(e)}", exc_info=debug)
        sys.exit(1)


@cli.command("validate-cross-project")
@click.option(
    "--manifest",
    type=str,
    required=True,
    help="Path to colibri-manifest.json generated by colibri generate.",
)
@click.option(
    "--format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format.",
)
def validate_cross_project_cmd(manifest, format):
    """Validate cross-project lineage in a generated colibri-manifest.json."""
    if not os.path.exists(manifest):
        click.echo(f"❌ Manifest file not found at {manifest}")
        sys.exit(1)

    try:
        with open(manifest, "r", encoding="utf-8") as file_handle:
            manifest_data = json.load(file_handle)
    except Exception as e:
        click.echo(f"❌ Error reading manifest: {str(e)}")
        sys.exit(1)

    result = validate_cross_project_lineage(manifest_data)
    summary = result["summary"]

    if format == "json":
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo("🔍 Cross-project lineage validation")
        click.echo("")
        click.echo(f"Cross-project sources found: {summary['cross_project_source_count']}")
        click.echo(f"Validated cross-project sources: {summary['validated_cross_source_count']}")
        click.echo(f"Accepted source-only cases: {summary['accepted_source_only_count']}")
        click.echo(
            f"Direct cross-project model links: {summary['direct_cross_project_model_link_count']}"
        )
        click.echo(f"Issues: {summary['issue_count']}")

        if result["accepted_source_only_sources"]:
            click.echo("")
            click.echo("Accepted source-only parent references:")
            for source_id in result["accepted_source_only_sources"]:
                click.echo(f"- {source_id}")

        if result["issues"]:
            click.echo("")
            click.echo("Issues:")
            for issue in result["issues"]:
                click.echo(
                    f"- {issue['source_id']}: expected {issue['expected_upstream_model']} but found candidates "
                    f"{', '.join(issue['matching_models_in_other_projects'])}"
                )

    if summary["issue_count"] > 0:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    cli()
