import math

import pytest
from dagster import Definitions, validate_run_config
from pydantic import ValidationError

from dags_pipelines import defs
from dags_pipelines.causal_geo_marketing_dag import (
    CampaignEconomicsConfig,
    GeoAudienceConfig,
    MarketingSpendConfig,
    O2OJourneyConfig,
    StoreOperationsConfig,
    defs as geo_marketing_defs,
)
from dags_pipelines.causal_sales_dag import defs as sales_defs
from dags_pipelines.geo_places_pipeline import weekly


def test_pipeline_definitions_load():
    Definitions.validate_loadable(defs)


def test_sales_and_geo_modules_define_independent_jobs_and_ops():
    assert [job.name for job in sales_defs.resolve_all_job_defs()] == ["causal_sales_dag"]
    assert [job.name for job in geo_marketing_defs.resolve_all_job_defs()] == [
        "geo_marketing_sales_dag",
    ]
    Definitions.validate_loadable(sales_defs)
    Definitions.validate_loadable(geo_marketing_defs)
    sales_job = sales_defs.resolve_job_def("causal_sales_dag")
    geo_job = geo_marketing_defs.resolve_job_def("geo_marketing_sales_dag")
    sales_op_names = {node.name for node in sales_job.graph.node_defs}
    geo_op_names = {node.name for node in geo_job.graph.node_defs}
    assert sales_op_names.isdisjoint(geo_op_names)
    assert geo_job.graph.node_named("marketing_spend").definition.name == "geo_marketing_spend"
    assert geo_job.graph.node_named("website_visits").definition.name == "geo_website_visits"


def test_pipeline_jobs_are_registered():
    assert {
        defs.resolve_job_def(name).name
        for name in (
        "leo_cdp_to_leo_bot_etl",
        "hello_world",
        "causal_sales_dag",
        "geo_marketing_sales_dag",
        "geo_places_pipeline",
        )
    }


def test_geo_places_pipeline_persists_to_postgres_without_csv_export():
    assert set(defs.resolve_job_def("geo_places_pipeline").graph.node_names()) == {
        "process_places",
        "process_brave_search",
        "process_mass_schedule",
        "process_knowledge",
    }


def test_geo_places_pipeline_runs_weekly():
    assert weekly.name == "geo_places_full_refresh_weekly"
    assert weekly.cron_schedule == "0 2 * * 0"


def test_arango_pipeline_contains_expected_ops():
    etl_job = defs.resolve_job_def("leo_cdp_to_leo_bot_etl")
    assert set(etl_job.graph.node_names()) == {
        "extract_profiles",
        "extract_transactions",
        "transform_and_embed_profiles",
        "transform_and_embed_txns",
        "load_profiles_to_pg",
        "load_txns_to_pg",
        "collect_tenants_from_profiles",
        "refresh_metrics_task",
    }
    dependencies = {
        node.name: {dependency.node for dependency in inputs.values()}
        for node, inputs in etl_job.graph.dependencies.items()
    }
    assert dependencies["extract_profiles"] == set()
    assert dependencies["extract_transactions"] == {"extract_profiles"}
    assert dependencies["transform_and_embed_profiles"] == {"extract_profiles"}
    assert dependencies["transform_and_embed_txns"] == {"extract_transactions"}
    assert dependencies["load_profiles_to_pg"] == {"transform_and_embed_profiles"}
    assert dependencies["load_txns_to_pg"] == {"transform_and_embed_txns"}
    assert dependencies["collect_tenants_from_profiles"] == {
        "transform_and_embed_profiles"
    }
    assert dependencies["refresh_metrics_task"] == {
        "collect_tenants_from_profiles",
        "load_profiles_to_pg",
        "load_txns_to_pg",
    }


def test_arango_pipeline_run_config_validates(monkeypatch):
    for variable in (
        "ARANGO_URL",
        "ARANGO_USERNAME",
        "ARANGO_PASSWORD",
        "PGSQL_DB_URL",
    ):
        monkeypatch.setenv(variable, "validation-placeholder")
    for variable in (
        "ARANGO_DATABASE",
        "ARANGO_PROFILE_COLLECTION",
        "ARANGO_TRANSACTION_COLLECTION",
    ):
        monkeypatch.delenv(variable, raising=False)

    validate_run_config(
        defs.resolve_job_def("leo_cdp_to_leo_bot_etl"),
        {
            "ops": {
                "extract_profiles": {
                    "config": {"segment_id": "test-segment", "batch_size": 5000}
                },
                "transform_and_embed_profiles": {"config": {"batch_size": 64}},
                "transform_and_embed_txns": {"config": {"batch_size": 64}},
            }
        },
    )


def test_hello_world_job_accepts_name_config():
    result = defs.resolve_job_def("hello_world").execute_in_process(
        run_config={"ops": {"hello": {"config": {"name": "Dagster"}}}}
    )
    assert result.success


def test_causal_sales_dag_has_expected_parent_relationships_and_runs():
    job = defs.resolve_job_def("causal_sales_dag")
    dependencies = {
        node.name: {dependency.node for dependency in inputs.values()}
        for node, inputs in job.graph.dependencies.items()
    }

    assert dependencies == {
        "marketing_spend": set(),
        "seasonality_index": set(),
        "product_quality_index": set(),
        "ad_impressions": {"marketing_spend"},
        "website_visits": {"ad_impressions", "seasonality_index"},
        "purchases": {
            "website_visits",
            "seasonality_index",
            "product_quality_index",
        },
    }

    result = job.execute_in_process(
        run_config={
            "ops": {
                "marketing_spend": {"config": {"thousands_usd": 10}},
                "seasonality_index": {"config": {"index": 0.5}},
                "product_quality_index": {"config": {"index": 0.7}},
            }
        }
    )
    assert result.success
    assert result.output_for_node("purchases") == pytest.approx(1.61)
    invalid_result = job.execute_in_process(
        run_config={
            "ops": {
                "seasonality_index": {"config": {"index": 1.5}},
            }
        },
        raise_on_error=False,
    )
    assert not invalid_result.success


def test_geo_marketing_dag_relationships_and_default_economics():
    job = defs.resolve_job_def("geo_marketing_sales_dag")
    dependencies = {
        node.alias: {dependency.node for dependency in inputs.values()}
        for node, inputs in job.graph.dependencies.items()
    }
    assert dependencies == {
        "marketing_spend": set(),
        "seasonality_index": set(),
        "product_quality_index": set(),
        "geo_ad_impressions": {"marketing_spend"},
        "website_visits": {"geo_ad_impressions", "seasonality_index"},
        "o2o_journey": {"website_visits"},
        "online_purchases": {
            "o2o_journey", "seasonality_index", "product_quality_index",
        },
        "store_purchases": {
            "o2o_journey", "seasonality_index", "product_quality_index",
        },
        "campaign_economics": {
            "marketing_spend", "online_purchases", "store_purchases",
        },
    }
    result = job.execute_in_process()
    assert result.success
    impressions = math.pi * 5000 * 0.6 * 3
    sessions = impressions * 0.035
    online_purchases = sessions * 0.25 * 0.046
    o2o_purchases = sessions * 0.75 * 0.2 * 0.54
    revenue = online_purchases * 12 + o2o_purchases * 8

    assert result.output_for_node("geo_ad_impressions") == pytest.approx(impressions / 1000)
    assert result.output_for_node("o2o_journey", "online_visits") == pytest.approx(
        sessions * 0.25 / 1000
    )
    assert result.output_for_node("o2o_journey", "store_visits") == pytest.approx(
        sessions * 0.75 * 0.2 / 1000
    )
    metrics = result.output_for_node("campaign_economics")
    assert metrics == pytest.approx({
        "marketing_spend_usd": 10000,
        "online_purchase_count": online_purchases,
        "o2o_purchase_count": o2o_purchases,
        "baseline_store_purchase_count": 540,
        "total_purchase_count": 540 + online_purchases + o2o_purchases,
        "unserved_campaign_purchase_count": 0,
        "baseline_revenue_usd": 4320,
        "total_revenue_usd": 4320 + revenue,
        "simulated_incremental_revenue_usd": revenue,
        "simulated_incremental_contribution_usd": revenue * 0.65 - 10000,
        "simulated_roas": revenue / 10000,
        "cost_per_campaign_purchase_usd": 10000 / (online_purchases + o2o_purchases),
    })
    assert metrics["simulated_incremental_contribution_usd"] < 0


@pytest.mark.parametrize(
    ("op_name", "config"),
    [
        ("marketing_spend", {"thousands_usd": 0}),
        ("geo_ad_impressions", {"audience_per_square_km": 0}),
        ("geo_ad_impressions", {"eligible_fraction": 0}),
        ("geo_ad_impressions", {"local_delivery_fraction": 0}),
    ],
)
def test_geo_campaign_without_exposure_retains_only_baseline(op_name, config):
    result = defs.resolve_job_def("geo_marketing_sales_dag").execute_in_process(
        run_config={"ops": {op_name: {"config": config}}},
    )
    assert result.success
    assert result.output_for_node("geo_ad_impressions") == 0
    metrics = result.output_for_node("campaign_economics")
    assert metrics["online_purchase_count"] == 0
    assert metrics["o2o_purchase_count"] == 0
    assert metrics["total_purchase_count"] == pytest.approx(540)
    assert metrics["total_revenue_usd"] == pytest.approx(4320)
    assert metrics["simulated_incremental_revenue_usd"] == 0
    assert metrics["simulated_incremental_contribution_usd"] == -metrics["marketing_spend_usd"]
    assert metrics["cost_per_campaign_purchase_usd"] is None
    if op_name == "marketing_spend":
        assert metrics["simulated_roas"] is None
    else:
        assert metrics["simulated_roas"] == 0


@pytest.mark.parametrize("online_share", [0.0, 1.0])
def test_geo_journey_extremes_do_not_double_count_sessions(online_share):
    result = defs.resolve_job_def("geo_marketing_sales_dag").execute_in_process(
        run_config={"ops": {"o2o_journey": {"config": {
            "online_order_share": online_share, "store_visit_rate": 1,
        }}}},
    )
    assert result.success
    sessions = result.output_for_node("website_visits")
    online = result.output_for_node("o2o_journey", "online_visits")
    offline = result.output_for_node("o2o_journey", "store_visits")
    assert online + offline == pytest.approx(sessions)
    assert online == pytest.approx(sessions * online_share)
    metrics = result.output_for_node("campaign_economics")
    if online_share == 0:
        assert metrics["online_purchase_count"] == 0
        assert metrics["o2o_purchase_count"] > 0
    else:
        assert metrics["online_purchase_count"] > 0
        assert metrics["o2o_purchase_count"] == 0


@pytest.mark.parametrize("capacity", [0.0, 500.0, 550.0])
def test_geo_store_capacity_reserves_baseline_before_campaign(capacity):
    result = defs.resolve_job_def("geo_marketing_sales_dag").execute_in_process(
        run_config={"ops": {"store_purchases": {"config": {"purchase_capacity": capacity}}}},
    )
    assert result.success
    sales = result.output_for_node("store_purchases")
    assert sales["baseline_purchases"] == pytest.approx(min(540, capacity))
    assert sales["campaign_purchases"] == pytest.approx(max(capacity - 540, 0))
    assert sales["total_purchases"] == pytest.approx(capacity)
    assert sales["unserved_campaign_purchases"] > 0


def test_geo_impressions_obey_budget_below_audience_cap():
    result = defs.resolve_job_def("geo_marketing_sales_dag").execute_in_process(
        run_config={"ops": {"marketing_spend": {"config": {"thousands_usd": 0.01}}}},
    )
    assert result.success
    # Ten dollars at ten-dollar CPM gives 1,000 impressions; 80% are local.
    assert result.output_for_node("geo_ad_impressions") == pytest.approx(0.8)
    assert result.output_for_node("campaign_economics")["marketing_spend_usd"] == 10


@pytest.mark.parametrize(
    ("config", "expected_impressions"),
    [
        ({"radius_km": 0.5}, math.pi * 0.5**2 * 5000 * 0.6 * 3),
        ({"frequency_cap": 1}, math.pi * 5000 * 0.6),
    ],
)
def test_geo_impressions_scale_with_catchment_and_frequency(config, expected_impressions):
    result = defs.resolve_job_def("geo_marketing_sales_dag").execute_in_process(
        run_config={"ops": {"geo_ad_impressions": {"config": config}}},
    )
    assert result.success
    assert result.output_for_node("geo_ad_impressions") == pytest.approx(
        expected_impressions / 1000
    )


@pytest.mark.parametrize(
    ("config_class", "values"),
    [
        (MarketingSpendConfig, {"thousands_usd": -1}),
        (MarketingSpendConfig, {"thousands_usd": float("inf")}),
        (GeoAudienceConfig, {"radius_km": 0}),
        (GeoAudienceConfig, {"cpm_usd": 0}),
        (GeoAudienceConfig, {"frequency_cap": 0}),
        (GeoAudienceConfig, {"eligible_fraction": 1.1}),
        (GeoAudienceConfig, {"local_delivery_fraction": -0.1}),
        (GeoAudienceConfig, {"audience_per_square_km": float("nan")}),
        (O2OJourneyConfig, {"online_order_share": 1.1}),
        (O2OJourneyConfig, {"store_visit_rate": -0.1}),
        (StoreOperationsConfig, {"purchase_capacity": -1}),
        (StoreOperationsConfig, {"baseline_walk_ins": -1}),
        (CampaignEconomicsConfig, {"gross_margin": 1.1}),
        (CampaignEconomicsConfig, {"online_basket_usd": -1}),
        (CampaignEconomicsConfig, {"store_basket_usd": float("inf")}),
    ],
)
def test_geo_simulation_rejects_invalid_config(config_class, values):
    with pytest.raises(ValidationError):
        config_class(**values)


def test_geo_job_invalid_run_config_fails_explicitly():
    result = defs.resolve_job_def("geo_marketing_sales_dag").execute_in_process(
        run_config={"ops": {"geo_ad_impressions": {"config": {"cpm_usd": 0}}}},
        raise_on_error=False,
    )
    assert not result.success
