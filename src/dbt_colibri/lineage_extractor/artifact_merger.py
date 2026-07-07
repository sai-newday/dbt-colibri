import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


@dataclass
class ProjectArtifacts:
    project: str
    manifest: Dict[str, Any]
    catalog: Dict[str, Any]


def parse_owner_from_unique_id(unique_id: str) -> str:
    parts = str(unique_id).split(".")
    return parts[1] if len(parts) >= 2 else ""


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def dedup_list(values: List[Any]) -> List[Any]:
    seen = set()
    output = []
    for value in values:
        key = json.dumps(value, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def replace_list_values(values: List[Any], replacements: Dict[str, str]) -> List[Any]:
    return dedup_list([replacements.get(value, value) for value in values])


def build_cross_project_source_rewrites(manifest: Dict[str, Any]) -> Dict[str, str]:
    rewrites: Dict[str, str] = {}
    for source_id in (manifest.get("sources") or {}):
        if not source_id.startswith("source."):
            continue

        parts = source_id.split(".")
        if len(parts) < 4:
            continue

        consuming_project = parts[1]
        upstream_project = parts[2]
        table_name = parts[3]
        if consuming_project == upstream_project:
            continue

        upstream_model_id = f"model.{upstream_project}.{table_name}"
        if upstream_model_id in (manifest.get("nodes") or {}):
            rewrites[source_id] = upstream_model_id

    return rewrites


def append_relation_alias(node: Dict[str, Any], relation_name: str) -> None:
    if not relation_name:
        return
    aliases = list(node.get("x_colibri_relation_aliases") or [])
    aliases.append(relation_name)
    node["x_colibri_relation_aliases"] = dedup_list(aliases)


def append_table_alias(entry: Dict[str, Any], database: str, schema: str, name: str) -> None:
    if not (database and schema and name):
        return
    aliases = list(entry.get("x_colibri_table_aliases") or [])
    aliases.append({"database": database, "schema": schema, "name": name})
    entry["x_colibri_table_aliases"] = dedup_list(aliases)


def normalize_cross_project_sources(manifest: Dict[str, Any], catalog: Dict[str, Any]) -> int:
    rewrites = build_cross_project_source_rewrites(manifest)
    if not rewrites:
        return 0

    nodes = manifest.get("nodes") or {}
    sources = manifest.get("sources") or {}
    catalog_nodes = catalog.get("nodes") or {}
    catalog_sources = catalog.get("sources") or {}

    for source_id, upstream_model_id in rewrites.items():
        source_node = sources.get(source_id) or {}
        upstream_node = nodes.get(upstream_model_id)
        if upstream_node is not None:
            append_relation_alias(upstream_node, source_node.get("relation_name"))

        source_catalog = catalog_sources.get(source_id) or {}
        upstream_catalog = catalog_nodes.get(upstream_model_id)
        if upstream_catalog is not None:
            metadata = source_catalog.get("metadata") or {}
            append_table_alias(
                upstream_catalog,
                metadata.get("database"),
                metadata.get("schema"),
                metadata.get("name"),
            )

    for node in nodes.values():
        depends_on = node.get("depends_on") or {}
        if "nodes" in depends_on:
            depends_on["nodes"] = replace_list_values(depends_on.get("nodes") or [], rewrites)

    parent_map = manifest.get("parent_map") or {}
    for node_id, parents in list(parent_map.items()):
        parent_map[node_id] = replace_list_values(parents or [], rewrites)

    child_map = manifest.get("child_map") or {}
    for source_id, upstream_model_id in rewrites.items():
        source_children = child_map.pop(source_id, [])
        if source_children:
            child_map.setdefault(upstream_model_id, [])
            child_map[upstream_model_id].extend(source_children)

    for node_id, children in list(child_map.items()):
        child_map[node_id] = replace_list_values(children or [], rewrites)

    for source_id in rewrites:
        sources.pop(source_id, None)
        parent_map.pop(source_id, None)
        catalog_sources.pop(source_id, None)

    return len(rewrites)


def merge_map_of_lists(projects: List[ProjectArtifacts], section: str) -> Dict[str, List[Any]]:
    merged: Dict[str, List[Any]] = {}
    for project_artifacts in projects:
        source = project_artifacts.manifest.get(section) or {}
        for key, values in source.items():
            merged.setdefault(key, [])
            merged[key].extend(values or [])
    return {key: dedup_list(values) for key, values in merged.items()}


def choose_owner_record(
    unique_id: str,
    by_project: Dict[str, Dict[str, Any]],
    strict: bool,
    critical_fields: Tuple[str, ...],
    kind: str,
) -> Dict[str, Any]:
    owner = parse_owner_from_unique_id(unique_id)
    if owner in by_project:
        return by_project[owner]

    records = list(by_project.items())
    first = records[0][1]
    for _, record in records[1:]:
        for field in critical_fields:
            if first.get(field) != record.get(field):
                message = (
                    f"Unresolvable {kind} collision for {unique_id}: "
                    f"{field} differs and owner project '{owner}' is not in merge inputs."
                )
                if strict:
                    raise ValueError(message)
                return first
    return first


def merge_manifest_nodes(projects: List[ProjectArtifacts], strict: bool) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for project_artifacts in projects:
        for unique_id, record in (project_artifacts.manifest.get("nodes") or {}).items():
            index.setdefault(unique_id, {})[project_artifacts.project] = record

    merged: Dict[str, Dict[str, Any]] = {}
    for unique_id, by_project in index.items():
        chosen = dict(
            choose_owner_record(
                unique_id,
                by_project,
                strict=strict,
                critical_fields=("database", "schema", "relation_name"),
                kind="manifest node",
            )
        )

        relation_aliases = sorted(
            {
                record.get("relation_name")
                for record in by_project.values()
                if record.get("relation_name")
            }
        )
        if relation_aliases:
            chosen["x_colibri_relation_aliases"] = relation_aliases

        merged[unique_id] = chosen
    return merged


def merge_catalog_section(
    projects: List[ProjectArtifacts], section: str, strict: bool
) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for project_artifacts in projects:
        for unique_id, record in (project_artifacts.catalog.get(section) or {}).items():
            index.setdefault(unique_id, {})[project_artifacts.project] = record

    merged: Dict[str, Dict[str, Any]] = {}
    for unique_id, by_project in index.items():
        chosen = dict(
            choose_owner_record(
                unique_id,
                by_project,
                strict=strict,
                critical_fields=("metadata",),
                kind=f"catalog {section}",
            )
        )
        table_aliases = []
        for record in by_project.values():
            database = record.get("metadata", {}).get("database")
            schema = record.get("metadata", {}).get("schema")
            name = record.get("metadata", {}).get("name")
            if database and schema and name:
                table_aliases.append({"database": database, "schema": schema, "name": name})
        if table_aliases:
            chosen["x_colibri_table_aliases"] = dedup_list(table_aliases)
        merged[unique_id] = chosen
    return merged


def merge_manifest(projects: List[ProjectArtifacts], strict: bool) -> Dict[str, Any]:
    base = projects[0].manifest
    output: Dict[str, Any] = {
        "metadata": base.get("metadata", {}),
        "dbt_schema_version": base.get("dbt_schema_version"),
        "project_name": "mesh_combined",
        "nodes": merge_manifest_nodes(projects, strict=strict),
        "sources": {},
        "macros": {},
        "docs": {},
        "exposures": {},
        "metrics": {},
        "groups": {},
        "selectors": {},
        "semantic_models": {},
        "unit_tests": {},
        "saved_queries": {},
        "fixtures": {},
        "disabled": [],
        "parent_map": merge_map_of_lists(projects, "parent_map"),
        "child_map": merge_map_of_lists(projects, "child_map"),
        "group_map": merge_map_of_lists(projects, "group_map"),
    }

    dict_sections = [
        "sources",
        "macros",
        "docs",
        "exposures",
        "metrics",
        "groups",
        "selectors",
        "semantic_models",
        "unit_tests",
        "saved_queries",
        "fixtures",
    ]
    for section in dict_sections:
        merged = {}
        for project_artifacts in projects:
            merged.update(project_artifacts.manifest.get(section) or {})
        output[section] = merged

    disabled = []
    for project_artifacts in projects:
        disabled.extend(project_artifacts.manifest.get("disabled") or [])
    output["disabled"] = dedup_list(disabled)
    return output


def merge_catalog(projects: List[ProjectArtifacts], strict: bool) -> Dict[str, Any]:
    base = projects[0].catalog
    return {
        "metadata": base.get("metadata", {}),
        "nodes": merge_catalog_section(projects, "nodes", strict=strict),
        "sources": merge_catalog_section(projects, "sources", strict=strict),
        "errors": {},
    }


def load_project_artifacts(project_artifacts: List[Tuple[str, str, str]]) -> List[ProjectArtifacts]:
    projects: List[ProjectArtifacts] = []
    for project_name, manifest_path, catalog_path in project_artifacts:
        manifest = read_json(Path(manifest_path))
        catalog = read_json(Path(catalog_path))
        projects.append(ProjectArtifacts(project=project_name, manifest=manifest, catalog=catalog))
    return projects


def merge_project_artifacts(
    project_artifacts: List[Tuple[str, str, str]],
    strict: bool = True,
    link_cross_project_sources: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any], int]:
    projects = load_project_artifacts(project_artifacts)
    if not projects:
        raise ValueError("At least one project artifact set is required")

    merged_manifest = merge_manifest(projects, strict=strict)
    merged_catalog = merge_catalog(projects, strict=strict)
    normalized_sources = 0
    if link_cross_project_sources:
        normalized_sources = normalize_cross_project_sources(merged_manifest, merged_catalog)
    return merged_manifest, merged_catalog, normalized_sources


def write_merged_artifacts(output_dir: Path, manifest: Dict[str, Any], catalog: Dict[str, Any]) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    catalog_path = output_dir / "catalog.json"
    write_json(manifest_path, manifest)
    write_json(catalog_path, catalog)
    return manifest_path, catalog_path