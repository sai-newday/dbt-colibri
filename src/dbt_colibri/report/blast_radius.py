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
        self.all_models = self._build_model_index()

    def _build_model_index(self) -> Dict[str, str]:
        """Build an index mapping short names to full model IDs."""
        index = {}
        children = self.lineage_data.get("lineage", {}).get("children", {})
        parents = self.lineage_data.get("lineage", {}).get("parents", {})
        
        # Get all model IDs
        all_model_ids = set(children.keys()) | set(parents.keys())
        
        for model_id in all_model_ids:
            # Extract short name (last part after last dot)
            short_name = model_id.split(".")[-1]
            index[short_name.lower()] = model_id
            index[model_id.lower()] = model_id
        
        return index

    def _resolve_model_id(self, model_name: str) -> Optional[str]:
        """
        Resolve a model name to its full ID.
        
        Supports:
        - Full IDs: model.project.model_name
        - Short names: model_name
        - Project-qualified: project.model_name
        
        Args:
            model_name: The model name to resolve
            
        Returns:
            Full model ID if found, None otherwise
        """
        model_lower = model_name.lower()
        
        # Try exact match first
        if model_lower in self.all_models:
            return self.all_models[model_lower]
        
        # Try partial matches (for short names)
        matches = [mid for short, mid in self.all_models.items() 
                  if short.endswith(model_lower) or mid.endswith(model_lower)]
        
        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            self.logger.warning(
                f"Multiple models match '{model_name}': {matches}. "
                f"Please use full model ID (e.g., model.project.{model_name})"
            )
            return None
        
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
            model_id: The source model ID or name (e.g., "model.project.customers" or "customers")
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

            if current_model not in self.children_map:
                continue

            downstream_models = set()
            for children in self.children_map[current_model].values():
                for child_mapping in children:
                    child_model = child_mapping.get("model") or child_mapping.get("dbt_node")
                    if child_model:
                        downstream_models.add(child_model)

            for child_model in downstream_models:
                edge_key = (current_model, child_model)
                if edge_key in visited_edges:
                    continue

                visited_edges.add(edge_key)

                if child_model not in affected:
                    affected[child_model] = {
                        "columns": set(),
                        "depth": depth + 1,
                        "paths": [],
                    }

                new_path = path + [child_model]
                affected[child_model]["paths"].append(new_path)
                queue.append((child_model, depth + 1, new_path))

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
