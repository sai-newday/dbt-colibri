import os
from dbt_colibri.lineage_extractor.extractor import DbtColumnLineageExtractor
from dbt_colibri.report.generator import DbtColibriReportGenerator

# Use the pre-merged 3-project artifacts (baffleshop, daffleshop, jaffleshop)
manifest_path = "combined-lineage/dist/_merged_artifacts/manifest.json"
catalog_path = "combined-lineage/dist/_merged_artifacts/catalog.json"

print("Processing merged 3-project demo (baffleshop, daffleshop, jaffleshop)...")

# Output must be 'dist/' for GitHub Pages
output_dir = "dist"

# Ensure output directory exists
os.makedirs(output_dir, exist_ok=True)

# Extract lineage
extractor = DbtColumnLineageExtractor(
    manifest_path=manifest_path,
    catalog_path=catalog_path
)

# Generate HTML report
report_generator = DbtColibriReportGenerator(extractor)
report_generator.generate_report(output_dir=output_dir)

print(f"✔ Report generated in {output_dir}/index.html")
