"""Tests for blast radius analysis functionality."""

import pytest
import logging
from src.dbt_colibri.report.blast_radius import BlastRadiusAnalyzer


@pytest.fixture
def sample_lineage_data():
    """Create a sample lineage structure for testing."""
    return {
        "lineage": {
            "parents": {
                "model.analytics.orders": {
                    "order_id": [
                        {
                            "model": "model.raw.orders",
                            "column": "id",
                            "lineage_type": "direct",
                        }
                    ],
                    "customer_id": [
                        {
                            "model": "model.analytics.customers",
                            "column": "customer_id",
                            "lineage_type": "direct",
                        }
                    ],
                },
                "model.analytics.order_metrics": {
                    "order_id": [
                        {
                            "model": "model.analytics.orders",
                            "column": "order_id",
                            "lineage_type": "direct",
                        }
                    ],
                    "customer_id": [
                        {
                            "model": "model.analytics.orders",
                            "column": "customer_id",
                            "lineage_type": "direct",
                        }
                    ],
                },
                "model.analytics.dashboards": {
                    "customer_email": [
                        {
                            "model": "model.analytics.customers",
                            "column": "email",
                            "lineage_type": "direct",
                        }
                    ],
                    "total_orders": [
                        {
                            "model": "model.analytics.order_metrics",
                            "column": "total_count",
                            "lineage_type": "direct",
                        }
                    ],
                },
                "model.analytics.reporting": {
                    "order_value": [
                        {
                            "model": "model.analytics.order_metrics",
                            "column": "total_value",
                            "lineage_type": "direct",
                        }
                    ],
                },
            },
            "children": {
                "model.analytics.customers": {
                    "customer_id": [
                        {
                            "model": "model.analytics.orders",
                            "column": "customer_id",
                            "lineage_type": "direct",
                        }
                    ],
                    "email": [
                        {
                            "model": "model.analytics.dashboards",
                            "column": "customer_email",
                            "lineage_type": "direct",
                        }
                    ],
                },
                "model.analytics.orders": {
                    "order_id": [
                        {
                            "model": "model.analytics.order_metrics",
                            "column": "order_id",
                            "lineage_type": "direct",
                        }
                    ],
                    "customer_id": [
                        {
                            "model": "model.analytics.order_metrics",
                            "column": "customer_id",
                            "lineage_type": "direct",
                        }
                    ],
                },
                "model.analytics.order_metrics": {
                    "total_count": [
                        {
                            "model": "model.analytics.dashboards",
                            "column": "total_orders",
                            "lineage_type": "direct",
                        }
                    ],
                    "total_value": [
                        {
                            "model": "model.analytics.reporting",
                            "column": "order_value",
                            "lineage_type": "direct",
                        }
                    ],
                },
            },
        }
    }


@pytest.fixture
def analyzer(sample_lineage_data):
    """Create a BlastRadiusAnalyzer instance with sample data."""
    return BlastRadiusAnalyzer(sample_lineage_data)


class TestBlastRadiusAnalyzer:
    """Test suite for BlastRadiusAnalyzer."""

    def test_find_blast_radius_single_column(self, analyzer):
        """Test finding blast radius for a single column."""
        result = analyzer.find_blast_radius("model.analytics.customers", ["customer_id"])

        assert result["source_model"] == "model.analytics.customers"
        assert result["source_columns"] == ["customer_id"]
        assert result["summary"]["affected_models_count"] == 2  # orders, order_metrics
        assert result["summary"]["max_depth"] == 2

        # Check that orders and order_metrics are in affected items
        affected_models = {item["model"] for item in result["affected_items"]}
        assert "model.analytics.orders" in affected_models
        assert "model.analytics.order_metrics" in affected_models

    def test_find_blast_radius_multiple_columns(self, analyzer):
        """Test finding blast radius for multiple columns."""
        result = analyzer.find_blast_radius(
            "model.analytics.customers", ["customer_id", "email"]
        )

        assert len(result["source_columns"]) == 2
        # customer_id affects orders->order_metrics
        # email affects dashboards
        assert result["summary"]["affected_models_count"] == 3  # orders, order_metrics, dashboards
        assert result["summary"]["max_depth"] == 2

    def test_find_blast_radius_no_impact(self, analyzer):
        """Test model with no downstream dependencies."""
        result = analyzer.find_blast_radius("model.analytics.reporting", ["order_value"])

        assert result["summary"]["affected_models_count"] == 0
        assert len(result["affected_items"]) == 0

    def test_find_blast_radius_nonexistent_model(self, analyzer):
        """Test analysis on a model that doesn't exist in lineage."""
        result = analyzer.find_blast_radius("model.analytics.nonexistent", ["column"])

        assert result["summary"]["affected_models_count"] == 0
        assert result["source_model"] == "model.analytics.nonexistent"

    def test_find_blast_radius_empty_columns(self, analyzer):
        """Test with empty column list."""
        result = analyzer.find_blast_radius("model.analytics.customers", [])

        assert result["summary"]["affected_models_count"] == 0
        assert len(result["affected_items"]) == 0

    def test_max_depth_limit(self, analyzer):
        """Test max_depth parameter limits traversal."""
        result_unlimited = analyzer.find_blast_radius(
            "model.analytics.customers", ["customer_id"], max_depth=None
        )
        result_depth1 = analyzer.find_blast_radius(
            "model.analytics.customers", ["customer_id"], max_depth=1
        )

        # With depth limit 1, only orders should be affected
        affected_models_depth1 = {item["model"] for item in result_depth1["affected_items"]}
        assert "model.analytics.orders" in affected_models_depth1
        assert "model.analytics.order_metrics" not in affected_models_depth1

        # Unlimited should have more affected models
        assert result_unlimited["summary"]["affected_models_count"] >= len(
            affected_models_depth1
        )

    def test_result_structure(self, analyzer):
        """Test that result has correct structure."""
        result = analyzer.find_blast_radius("model.analytics.customers", ["customer_id"])

        # Check required keys
        assert "source_model" in result
        assert "source_columns" in result
        assert "affected_items" in result
        assert "summary" in result

        # Check summary keys
        summary = result["summary"]
        assert "affected_models_count" in summary
        assert "affected_columns_count" in summary
        assert "max_depth" in summary
        assert "total_downstream_items" in summary

        # Check affected item structure
        for item in result["affected_items"]:
            assert "model" in item
            assert "columns" in item
            assert "depth" in item
            assert "paths" in item
            assert isinstance(item["columns"], list)
            assert isinstance(item["paths"], list)

    def test_column_deduplication(self, analyzer):
        """Test that duplicate columns in affected items are removed."""
        result = analyzer.find_blast_radius("model.analytics.customers", ["customer_id"])

        for item in result["affected_items"]:
            # Each column should appear only once
            assert len(item["columns"]) == len(set(item["columns"]))

    def test_get_blast_radius_text(self, analyzer):
        """Test text output format."""
        text = analyzer.get_blast_radius_text("model.analytics.customers", ["customer_id"])

        assert "model.analytics.customers" in text
        assert "customer_id" in text
        assert "Affected Models:" in text or "Summary:" in text
        assert "📍" in text or "Depth" in text or "No downstream" in text

    def test_get_blast_radius_text_no_impact(self, analyzer):
        """Test text output when there's no impact."""
        text = analyzer.get_blast_radius_text("model.analytics.reporting", ["order_value"])

        assert "model.analytics.reporting" in text
        assert "No downstream impact" in text

    def test_complex_lineage_path(self, analyzer):
        """Test that paths are correctly tracked through multiple levels."""
        result = analyzer.find_blast_radius("model.analytics.customers", ["customer_id"])

        # Find the order_metrics item (should be at depth 2)
        order_metrics_item = next(
            (item for item in result["affected_items"]
             if item["model"] == "model.analytics.order_metrics"),
            None,
        )

        assert order_metrics_item is not None
        assert order_metrics_item["depth"] == 2
        assert len(order_metrics_item["paths"]) > 0
        # Path should go through orders
        assert any(
            "model.analytics.orders" in path for path in order_metrics_item["paths"]
        )


class TestBlastRadiusEdgeCases:
    """Test edge cases and error handling."""

    def test_circular_dependency_handling(self):
        """Test handling of circular dependencies."""
        # Create lineage with circular dependency
        circular_lineage = {
            "lineage": {
                "children": {
                    "model.a": {
                        "id": [{"model": "model.b", "column": "id"}]
                    },
                    "model.b": {
                        "id": [{"model": "model.c", "column": "id"}]
                    },
                    "model.c": {
                        "id": [{"model": "model.a", "column": "id"}]
                    },
                }
            }
        }

        analyzer = BlastRadiusAnalyzer(circular_lineage)
        result = analyzer.find_blast_radius("model.a", ["id"])

        # Should not crash and should have finite results
        assert result["summary"]["affected_models_count"] > 0
        # Maximum depth should be reasonable (not infinite)
        assert result["summary"]["max_depth"] < 100

    def test_empty_lineage_data(self):
        """Test with completely empty lineage data."""
        empty_lineage = {"lineage": {"children": {}, "parents": {}}}
        analyzer = BlastRadiusAnalyzer(empty_lineage)
        result = analyzer.find_blast_radius("model.a", ["col"])

        assert result["summary"]["affected_models_count"] == 0

    def test_logger_initialization(self):
        """Test that logger works correctly."""
        lineage = {"lineage": {"children": {}, "parents": {}}}
        logger = logging.getLogger("test_logger")

        analyzer = BlastRadiusAnalyzer(lineage, logger=logger)
        assert analyzer.logger is logger

        # Test with default logger
        analyzer2 = BlastRadiusAnalyzer(lineage)
        assert analyzer2.logger is not None
