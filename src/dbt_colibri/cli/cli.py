# src/dbt_colibri/cli/cli.py

import click
import os
import sys
import json
from ..lineage_extractor.extractor import DbtColumnLineageExtractor
from ..report.generator import DbtColibriReportGenerator
from ..report.blast_radius import BlastRadiusAnalyzer
from importlib.metadata import version, PackageNotFoundError

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
    help="Model name to analyze (e.g., model.project.customers)",
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


if __name__ == "__main__":
    cli()
