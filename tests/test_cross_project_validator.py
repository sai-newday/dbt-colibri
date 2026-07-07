from dbt_colibri.lineage_extractor.cross_project_validator import validate_cross_project_lineage


def test_validator_accepts_source_only_when_no_matching_models():
    manifest = {
        "nodes": {
            "source.consumer.upstream_like.customers": {},
            "model.consumer.orders": {},
        },
        "lineage": {
            "edges": [
                {
                    "source": "source.consumer.upstream_like.customers",
                    "target": "model.consumer.orders",
                }
            ]
        },
    }

    result = validate_cross_project_lineage(manifest)

    assert result["summary"]["issue_count"] == 0
    assert "source.consumer.upstream_like.customers" in result["accepted_source_only_sources"]


def test_validator_flags_when_expected_upstream_missing_but_candidates_exist():
    manifest = {
        "nodes": {
            "source.consumer.wrong_project.customers": {},
            "model.actual.customers": {},
            "model.consumer.orders": {},
        },
        "lineage": {
            "edges": [
                {
                    "source": "source.consumer.wrong_project.customers",
                    "target": "model.consumer.orders",
                }
            ]
        },
    }

    result = validate_cross_project_lineage(manifest)

    assert result["summary"]["issue_count"] == 1
    issue = result["issues"][0]
    assert issue["source_id"] == "source.consumer.wrong_project.customers"
    assert "model.actual.customers" in issue["matching_models_in_other_projects"]