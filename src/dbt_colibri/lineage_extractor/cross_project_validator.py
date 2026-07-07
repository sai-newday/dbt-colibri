from typing import Dict, List, Set, Tuple


def _parse_node_id(node_id: str) -> List[str]:
    return str(node_id).split(".")


def find_cross_project_sources(manifest: Dict) -> Dict[str, Tuple[str, str, str]]:
    nodes = manifest.get("nodes", {})
    cross_project_sources = {}

    for node_id in nodes:
        if not node_id.startswith("source."):
            continue

        parts = _parse_node_id(node_id)
        if len(parts) < 4:
            continue

        consuming_project = parts[1]
        source_name = parts[2]
        table_name = parts[3]
        if source_name != consuming_project:
            cross_project_sources[node_id] = (
                consuming_project,
                source_name,
                table_name,
            )

    return cross_project_sources


def find_models_using_source(manifest: Dict, source_id: str) -> List[str]:
    edges = manifest.get("lineage", {}).get("edges", [])
    models = []

    for edge in edges:
        if edge.get("source") == source_id:
            target = edge.get("target")
            if target and target.startswith("model."):
                models.append(target)

    return sorted(set(models))


def find_direct_cross_project_model_links(manifest: Dict) -> Dict[Tuple[str, str], Set[str]]:
    edges = manifest.get("lineage", {}).get("edges", [])
    links: Dict[Tuple[str, str], Set[str]] = {}

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if not (source and target):
            continue
        if not (source.startswith("model.") and target.startswith("model.")):
            continue

        source_parts = _parse_node_id(source)
        target_parts = _parse_node_id(target)
        if len(source_parts) < 3 or len(target_parts) < 3:
            continue
        if source_parts[1] == target_parts[1]:
            continue

        links.setdefault((source, target), set())
        if edge.get("sourceColumn"):
            links[(source, target)].add(edge["sourceColumn"])

    return links


def find_matching_upstream_models(manifest: Dict, consuming_project: str, table_name: str) -> List[str]:
    nodes = manifest.get("nodes", {})
    candidates = []
    for node_id in nodes:
        if not node_id.startswith("model."):
            continue
        parts = _parse_node_id(node_id)
        if len(parts) < 3:
            continue
        project = parts[1]
        model_name = parts[2]
        if project == consuming_project:
            continue
        if model_name == table_name:
            candidates.append(node_id)
    return sorted(set(candidates))


def validate_cross_project_lineage(manifest: Dict) -> Dict:
    cross_sources = find_cross_project_sources(manifest)
    direct_links = find_direct_cross_project_model_links(manifest)

    issues: List[Dict] = []
    accepted_source_only_sources: List[str] = []
    validated_cross_sources: List[Dict] = []

    for source_id, (consuming_project, upstream_project, table_name) in cross_sources.items():
        expected_upstream = f"model.{upstream_project}.{table_name}"
        matching_models = find_matching_upstream_models(manifest, consuming_project, table_name)

        if expected_upstream in manifest.get("nodes", {}):
            downstream_models = find_models_using_source(manifest, source_id)
            validated_cross_sources.append(
                {
                    "source_id": source_id,
                    "upstream_model": expected_upstream,
                    "downstream_models": downstream_models,
                }
            )
            continue

        # Valid case requested by user: source-only parent when there is no
        # matching upstream model in any other project.
        if not matching_models:
            accepted_source_only_sources.append(source_id)
            continue

        issues.append(
            {
                "type": "missing_expected_upstream_model",
                "source_id": source_id,
                "expected_upstream_model": expected_upstream,
                "matching_models_in_other_projects": matching_models,
            }
        )

    return {
        "cross_sources": cross_sources,
        "direct_cross_project_links": {
            f"{source}->{target}": sorted(list(columns))
            for (source, target), columns in sorted(direct_links.items())
        },
        "validated_cross_sources": validated_cross_sources,
        "accepted_source_only_sources": accepted_source_only_sources,
        "issues": issues,
        "summary": {
            "cross_project_source_count": len(cross_sources),
            "validated_cross_source_count": len(validated_cross_sources),
            "accepted_source_only_count": len(accepted_source_only_sources),
            "direct_cross_project_model_link_count": len(direct_links),
            "issue_count": len(issues),
        },
    }