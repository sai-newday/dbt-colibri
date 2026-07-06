"""
Blast radius analysis for dbt model changes.

This module provides functionality to analyze the downstream impact (blast radius)
of changes to specific columns in a dbt model.
"""

import logging
from typing import Dict, List, Set, Optional, Tuple
from collections import deque


class BlastRadiusAnalyzer:
    """
    Analyzes the blast radius (downstream impact) of changes to specific columns
    in a dbt model.
    
    The blast radius shows all downstream models and columns that would be affected
    by changes to the specified source columns.
    """

    def __init__(self, lineage_data: dict, logger: Optional[logging.Logger] = None):
        """
        Initialize the BlastRadiusAnalyzer.
        
        Args:
            lineage_data: The lineage dictionary from DbtColumnLineageExtractor,
                         containing 'parents' and 'children' maps
            logger: Optional logger instance for debug output
        """
        self.lineage_data = lineage_data
        self.logger = logger or logging.getLogger("colibri.blast_radius")
        self.children_map = lineage_data.get("lineage", {}).get("children", {})
        self.parents_map = lineage_data.get("lineage", {}).get("parents", {})
        self.model_children_map = lineage_data.get("model_children", {})
        self.all_model_ids = self._build_model_index()

    def _build_model_index(self) -> Dict[str, str]:
        """Build an exact-match index for fully-qualified node IDs."""
        all_ids: Dict[str, str] = {}
        children = self.lineage_data.get("lineage", {}).get("children", {})
        parents = self.lineage_data.get("lineage", {}).get("parents", {})
        manifest_children = self.lineage_data.get("model_children", {})
        
        # Get all known node IDs from extracted column lineage and manifest model graph.
        all_model_ids = set(children.keys()) | set(parents.keys()) | set(manifest_children.keys())
        for child_list in manifest_children.values():
            all_model_ids.update(child_list)
        
        for model_id in all_model_ids:
            all_ids[model_id.lower()] = model_id

        return all_ids

    def _resolve_model_id(self, model_name: str) -> Optional[str]:
        """
        Resolve a model name to its full ID.
        
        Args:
            model_name: The model name to resolve
            
        Returns:
            Full model ID if found, None otherwise
        """
        model_lower = model_name.lower()

        # Full IDs only: exact match against known node IDs.
        if model_lower in self.all_model_ids:
            return self.all_model_ids[model_lower]

        self.logger.warning(
            f"Model '{model_name}' not found as a full node ID. "
            "Please pass the fully-qualified ID (for example: "
            "model.project.customers or source.project.source_name.table_name)."
        )
        
        return None

    def find_blast_radius(
        self,
        model_id: str,
        columns: Optional[List[str]],
        max_depth: Optional[int] = None,
    ) -> Dict:
        """
        Find all downstream models and columns affected by changes to the specified columns.
        
        Args:
            model_id: The source model full ID (e.g., "model.project.customers")
            columns: List of column names to analyze
            max_depth: Maximum depth to traverse (None = unlimited)
            
        Returns:
            A dictionary containing:
            {
                "source_model": "model.project.customers",
                "source_columns": ["customer_id", "email"],
                "affected_items": [...],
                "summary": {...}
            }
        """
        # Resolve model name to full ID
        resolved_model_id = self._resolve_model_id(model_id)
        if not resolved_model_id:
            self.logger.warning(f"Model '{model_id}' not found in lineage data")
            return self._empty_result(model_id, columns or [])

        # Validate model exists in children map
        if resolved_model_id not in self.children_map:
            self.logger.warning(f"Model {resolved_model_id} has no downstream lineage")
            return self._empty_result(resolved_model_id, columns or [])

        if not columns:
            return self._find_model_level_blast_radius(resolved_model_id, max_depth)

        # BFS traversal to find all downstream impacts
        affected = {}  # model_id -> {columns: set, depth: int, paths: list}
        visited_edges: Set[Tuple[str, str, str]] = set()  # (source_model, source_col, target_model)

        # Initialize queue with source model/columns
        queue = deque()
        for col in columns:
            queue.append((resolved_model_id, col, 0, [resolved_model_id]))  # (model, column, depth, path)

        while queue:
            current_model, current_col, depth, path = queue.popleft()

            # Stop if max depth already exceeded
            if max_depth is not None and depth >= max_depth:
                continue

            # Get children for this model/column
            if current_model not in self.children_map:
                continue

            if current_col not in self.children_map[current_model]:
                continue

            # Process each child relationship
            for child_mapping in self.children_map[current_model][current_col]:
                # Support both formats: 'model'/'column' and 'dbt_node'/'column'
                child_model = child_mapping.get("model") or child_mapping.get("dbt_node")
                child_col = child_mapping.get("column")

                if not child_model or not child_col:
                    continue

                edge_key = (current_model, current_col, child_model, child_col)

                # Skip if we've already processed this exact column lineage
                if edge_key in visited_edges:
                    continue

                visited_edges.add(edge_key)

                # Record affected model/column
                if child_model not in affected:
                    affected[child_model] = {
                        "columns": set(),
                        "depth": depth + 1,
                        "paths": [],
                    }

                affected[child_model]["columns"].add(child_col)
                new_path = path + [child_model]
                affected[child_model]["paths"].append(new_path)

                # Add to queue for further traversal
                queue.append((child_model, child_col, depth + 1, new_path))

        # Format and return results
        return self._format_results(resolved_model_id, columns, affected)

    def _expand_column_results_with_gui_traceability(
        self,
        source_model: str,
        source_columns: List[str],
        affected: Dict,
        max_depth: Optional[int] = None,
    ) -> Dict:
        """Extend column impacts with GUI-style dependency/parent inference.

        Existing entries keep strict column mappings. Newly discovered downstream
        models receive inferred impacted columns when parent mappings are known;
        otherwise they are recorded as model-level impact only.
        """
        if not affected:
            return affected

        impacted_columns_by_model: Dict[str, Set[str]] = {
            source_model: set(source_columns)
        }
        for model, data in affected.items():
            impacted_columns_by_model.setdefault(model, set()).update(data.get("columns", set()))

        queue = deque()
        visited_edges: Set[Tuple[str, str]] = set()

        queue.append((source_model, 0, [source_model]))

        # Seed traversal with known paths so we keep shortest path information
        # from strict column traversal.
        for model, model_data in affected.items():
            for path in model_data.get("paths", []):
                if path:
                    queue.append((model, len(path) - 1, path))

        while queue:
            current_node, depth, path = queue.popleft()

            if max_depth is not None and depth >= max_depth:
                continue

            for child_node in self.model_children_map.get(current_node, []):
                edge_key = (current_node, child_node)
                if edge_key in visited_edges:
                    continue

                visited_edges.add(edge_key)

                next_path = path + [child_node]
                next_depth = depth + 1
                queue.append((child_node, next_depth, next_path))

                if not child_node.startswith("model.") or child_node == source_model:
                    continue

                inferred_columns = self._infer_child_columns_from_parents(
                    parent_model=current_node,
                    parent_impacted_columns=impacted_columns_by_model.get(current_node, set()),
                    child_model=child_node,
                )

                if child_node not in affected:
                    affected[child_node] = {
                        "columns": set(inferred_columns),
                        "depth": next_depth,
                        "paths": [next_path],
                    }
                    impacted_columns_by_model.setdefault(child_node, set()).update(inferred_columns)
                    continue

                affected[child_node]["depth"] = min(affected[child_node]["depth"], next_depth)
                if next_path not in affected[child_node]["paths"]:
                    affected[child_node]["paths"].append(next_path)
                if inferred_columns:
                    affected[child_node]["columns"].update(inferred_columns)
                    impacted_columns_by_model.setdefault(child_node, set()).update(inferred_columns)

        return affected

    def _infer_child_columns_from_parents(
        self,
        parent_model: str,
        parent_impacted_columns: Set[str],
        child_model: str,
    ) -> Set[str]:
        """Infer impacted child columns from parent mappings for GUI-like traceability."""
        inferred: Set[str] = set()
        child_parent_map = self.parents_map.get(child_model, {})

        for child_col, parent_refs in child_parent_map.items():
            for parent_ref in parent_refs:
                ref_model = parent_ref.get("model") or parent_ref.get("dbt_node")
                ref_col = parent_ref.get("column")

                if ref_model != parent_model:
                    continue

                # If we have explicit impacted columns for the parent model,
                # preserve specificity where possible.
                if parent_impacted_columns:
                    if ref_col in parent_impacted_columns or str(ref_col).startswith("__colibri_"):
                        inferred.add(child_col)

        return inferred

    def _find_model_level_blast_radius(
        self,
        model_id: str,
        max_depth: Optional[int] = None,
    ) -> Dict:
        """Find downstream models without column-level detail."""
        affected = {}
        visited_edges: Set[Tuple[str, str]] = set()

        queue = deque([(model_id, 0, [model_id])])

        while queue:
            current_model, depth, path = queue.popleft()

            if max_depth is not None and depth >= max_depth:
                continue

            downstream_nodes = self.model_children_map.get(current_model)

            # Fallback for lineage payloads without manifest model graph.
            if downstream_nodes is None:
                downstream_nodes = []
                if current_model in self.children_map:
                    dedup = set()
                    for children in self.children_map[current_model].values():
                        for child_mapping in children:
                            child_model = child_mapping.get("model") or child_mapping.get("dbt_node")
                            if child_model and child_model not in dedup:
                                dedup.add(child_model)
                                downstream_nodes.append(child_model)

            for child_node in downstream_nodes:
                edge_key = (current_model, child_node)
                if edge_key in visited_edges:
                    continue

                visited_edges.add(edge_key)

                new_path = path + [child_node]
                queue.append((child_node, depth + 1, new_path))

                # Keep output focused on downstream models.
                if not child_node.startswith("model."):
                    continue

                if child_node not in affected:
                    affected[child_node] = {
                        "columns": set(),
                        "depth": depth + 1,
                        "paths": [],
                    }

                affected[child_node]["paths"].append(new_path)

        return self._format_results(model_id, [], affected)

    def _empty_result(self, model_id: str, columns: List[str]) -> Dict:
        """Return an empty result structure."""
        return {
            "source_model": model_id,
            "source_columns": columns,
            "affected_items": [],
            "summary": {
                "affected_models_count": 0,
                "affected_columns_count": 0,
                "max_depth": 0,
                "total_downstream_items": 0,
            },
        }

    def _format_results(
        self, model_id: str, columns: List[str], affected: Dict
    ) -> Dict:
        """Format the blast radius results into the output structure."""
        if not affected:
            return self._empty_result(model_id, columns)

        affected_items = []
        max_depth = 0
        total_affected_columns = 0

        for model, data in sorted(affected.items()):
            columns_list = sorted(list(data["columns"]))
            max_depth = max(max_depth, data["depth"])
            total_affected_columns += len(columns_list)

            affected_items.append(
                {
                    "model": model,
                    "columns": columns_list,
                    "depth": data["depth"],
                    "paths": data["paths"],
                }
            )

        return {
            "source_model": model_id,
            "source_columns": columns,
            "affected_items": affected_items,
            "summary": {
                "affected_models_count": len(affected),
                "affected_columns_count": total_affected_columns,
                "max_depth": max_depth,
                "total_downstream_items": len(affected_items),
            },
        }

    def get_blast_radius_text(
        self,
        model_id: str,
        columns: List[str],
        max_depth: Optional[int] = None,
    ) -> str:
        """
        Get a human-readable text representation of the blast radius.
        
        Args:
            model_id: The source model ID
            columns: List of column names
            max_depth: Maximum depth to traverse
            
        Returns:
            Formatted text string showing the blast radius
        """
        result = self.find_blast_radius(model_id, columns, max_depth)
        
        lines = []
        lines.append(f"Blast Radius for: {model_id}")
        if result["source_columns"]:
            lines.append(f"Columns: {', '.join(result['source_columns'])}")
        else:
            lines.append("Columns: (model-level lineage)")
        lines.append("=" * 80)
        lines.append("")

        summary = result["summary"]
        if summary["affected_models_count"] == 0:
            lines.append("✓ No downstream impact detected")
            return "\n".join(lines)

        # Group by depth
        by_depth = {}
        for item in result["affected_items"]:
            depth = item["depth"]
            if depth not in by_depth:
                by_depth[depth] = []
            by_depth[depth].append(item)

        for depth in sorted(by_depth.keys()):
            if depth == 1:
                lines.append("Depth 1 (direct impact):")
            else:
                lines.append(f"Depth {depth} (indirect impact):")

            for item in by_depth[depth]:
                lines.append(f"  ├─ {item['model']}")
                if item["columns"]:
                    for col in item["columns"]:
                        # Format join marker columns with user-friendly label
                        if col == "__colibri_join__":
                            lines.append(f"  │  └─ (used as part of join condition)")
                        else:
                            lines.append(f"  │  └─ {col}")
                else:
                    lines.append("  │  └─ model-level impact")

            lines.append("")

        lines.append("Summary:")
        lines.append(f"  • Affected Models: {summary['affected_models_count']}")
        lines.append(f"  • Affected Columns: {summary['affected_columns_count']}")
        lines.append(f"  • Maximum Depth: {summary['max_depth']}")

        return "\n".join(lines)
