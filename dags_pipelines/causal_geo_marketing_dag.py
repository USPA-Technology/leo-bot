"""Independent geo-marketing simulation for coffee shops and O2O retail."""

import math

from dagster import Config, Definitions, OpExecutionContext, Out, job, op
from pydantic import Field


class MarketingSpendConfig(Config):
    thousands_usd: float = Field(default=10.0, ge=0, allow_inf_nan=False)


class SeasonalityConfig(Config):
    index: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)


class ProductQualityConfig(Config):
    index: float = Field(default=0.7, ge=0, le=1, allow_inf_nan=False)


class GeoAudienceConfig(Config):
    radius_km: float = Field(default=1.0, gt=0, allow_inf_nan=False)
    audience_per_square_km: float = Field(default=5000.0, ge=0, allow_inf_nan=False)
    eligible_fraction: float = Field(default=0.6, ge=0, le=1, allow_inf_nan=False)
    frequency_cap: float = Field(default=3.0, gt=0, allow_inf_nan=False)
    local_delivery_fraction: float = Field(default=0.8, ge=0, le=1, allow_inf_nan=False)
    cpm_usd: float = Field(default=10.0, gt=0, allow_inf_nan=False)


class O2OJourneyConfig(Config):
    online_order_share: float = Field(default=0.25, ge=0, le=1, allow_inf_nan=False)
    store_visit_rate: float = Field(default=0.2, ge=0, le=1, allow_inf_nan=False)


class StoreOperationsConfig(Config):
    baseline_walk_ins: float = Field(default=1000.0, ge=0, allow_inf_nan=False)
    purchase_capacity: float = Field(default=1500.0, ge=0, allow_inf_nan=False)


class CampaignEconomicsConfig(Config):
    online_basket_usd: float = Field(default=12.0, ge=0, allow_inf_nan=False)
    store_basket_usd: float = Field(default=8.0, ge=0, allow_inf_nan=False)
    gross_margin: float = Field(default=0.65, ge=0, le=1, allow_inf_nan=False)


@op
def geo_marketing_spend(
    context: OpExecutionContext, config: MarketingSpendConfig
) -> float:
    """Return marketing spend in thousands of USD."""
    context.log.info(
        "marketing_spend = %.2f thousand USD (exogenous input)",
        config.thousands_usd,
    )
    return config.thousands_usd


@op
def geo_seasonality_index(
    context: OpExecutionContext, config: SeasonalityConfig
) -> float:
    """Return a seasonality index between zero and one."""
    context.log.info(
        "seasonality_index = %.2f (exogenous input; range 0 to 1)",
        config.index,
    )
    return config.index


@op
def geo_product_quality_index(
    context: OpExecutionContext, config: ProductQualityConfig
) -> float:
    """Return a product quality index between zero and one."""
    context.log.info(
        "product_quality_index = %.2f (exogenous input; range 0 to 1)",
        config.index,
    )
    return config.index


@op
def geo_website_visits(
    context: OpExecutionContext,
    impressions_thousands: float,
    seasonality_index: float,
) -> float:
    """Estimate visits, in thousands, using a seasonal click-through rate."""
    click_through_rate = 0.02 + 0.03 * seasonality_index
    visits_thousands = impressions_thousands * click_through_rate
    context.log.info(
        "website_visits = %.2f thousand impressions * "
        "(0.02 + 0.03 * %.2f seasonality) = %.2f thousand visits "
        "(click-through rate: %.1f%%)",
        impressions_thousands,
        seasonality_index,
        visits_thousands,
        click_through_rate * 100,
    )
    return visits_thousands


@op
def online_purchases(
    context: OpExecutionContext,
    visits_thousands: float,
    seasonality_index: float,
    product_quality_index: float,
) -> float:
    """Estimate purchases, in thousands, using seasonal and quality effects."""
    conversion_rate = (
        0.02 + 0.03 * product_quality_index + 0.01 * seasonality_index
    )
    estimated_purchases = visits_thousands * conversion_rate
    context.log.info(
        "online_purchases = %.2f thousand visits * "
        "(0.02 + 0.03 * %.2f quality + 0.01 * %.2f seasonality) "
        "= %.2f thousand purchases (conversion rate: %.1f%%)",
        visits_thousands,
        product_quality_index,
        seasonality_index,
        estimated_purchases,
        conversion_rate * 100,
    )
    return estimated_purchases


@op
def geo_ad_impressions(
    context: OpExecutionContext,
    config: GeoAudienceConfig,
    spend_thousands_usd: float,
) -> float:
    """Estimate eligible local impressions in thousands, capped by catchment."""
    eligible_audience = (
        math.pi * config.radius_km**2
        * config.audience_per_square_km * config.eligible_fraction
    )
    budget_impressions = spend_thousands_usd * 1_000_000 / config.cpm_usd
    local_impressions = min(
        budget_impressions * config.local_delivery_fraction,
        eligible_audience * config.frequency_cap,
    )
    context.log.info(
        "geo_ad_impressions = %.2f thousand; radius = %.2f km; "
        "eligible audience = %.2f; frequency cap = %.2f. "
        "Full configured spend is charged even when local delivery is capped.",
        local_impressions / 1000,
        config.radius_km,
        eligible_audience,
        config.frequency_cap,
    )
    return local_impressions / 1000


@op(out={"online_visits": Out(float), "store_visits": Out(float)})
def o2o_journey(
    context: OpExecutionContext,
    config: O2OJourneyConfig,
    visits_thousands: float,
) -> tuple[float, float]:
    """Split online sessions into disjoint online-order and store-intent paths."""
    online_visits = visits_thousands * config.online_order_share
    store_visits = (
        visits_thousands * (1 - config.online_order_share) * config.store_visit_rate
    )
    context.log.info(
        "o2o_journey: %.4f thousand online-order sessions; "
        "%.4f thousand campaign store visits. Paths are assumed disjoint, "
        "not deduplicated observations.",
        online_visits,
        store_visits,
    )
    return online_visits, store_visits


@op
def store_purchases(
    context: OpExecutionContext,
    config: StoreOperationsConfig,
    store_visits_thousands: float,
    seasonality_index: float,
    product_quality_index: float,
) -> dict:
    """Estimate store transactions, reserving capacity for baseline demand."""
    conversion_rate = 0.35 + 0.2 * product_quality_index + 0.1 * seasonality_index
    baseline_demand = (
        config.baseline_walk_ins * (0.5 + seasonality_index) * conversion_rate
    )
    campaign_demand = store_visits_thousands * 1000 * conversion_rate
    baseline_purchases = min(baseline_demand, config.purchase_capacity)
    campaign_purchases = min(
        campaign_demand, config.purchase_capacity - baseline_purchases,
    )
    context.log.info(
        "store_purchases: %.2f baseline + %.2f campaign = %.2f transactions; "
        "capacity = %.2f; unserved campaign demand = %.2f.",
        baseline_purchases,
        campaign_purchases,
        baseline_purchases + campaign_purchases,
        config.purchase_capacity,
        campaign_demand - campaign_purchases,
    )
    return {
        "baseline_purchases": baseline_purchases,
        "campaign_purchases": campaign_purchases,
        "total_purchases": baseline_purchases + campaign_purchases,
        "unserved_campaign_purchases": campaign_demand - campaign_purchases,
    }


@op
def campaign_economics(
    context: OpExecutionContext,
    config: CampaignEconomicsConfig,
    spend_thousands_usd: float,
    online_purchases_thousands: float,
    store_sales: dict,
) -> dict:
    """Compare the assumed campaign scenario with a same-input no-ad baseline."""
    spend_usd = spend_thousands_usd * 1000
    online_count = online_purchases_thousands * 1000
    campaign_count = online_count + store_sales["campaign_purchases"]
    baseline_revenue = store_sales["baseline_purchases"] * config.store_basket_usd
    campaign_revenue = (
        online_count * config.online_basket_usd
        + store_sales["campaign_purchases"] * config.store_basket_usd
    )
    metrics = {
        "marketing_spend_usd": spend_usd,
        "online_purchase_count": online_count,
        "o2o_purchase_count": store_sales["campaign_purchases"],
        "baseline_store_purchase_count": store_sales["baseline_purchases"],
        "total_purchase_count": online_count + store_sales["total_purchases"],
        "unserved_campaign_purchase_count": store_sales["unserved_campaign_purchases"],
        "baseline_revenue_usd": baseline_revenue,
        "total_revenue_usd": baseline_revenue + campaign_revenue,
        "simulated_incremental_revenue_usd": campaign_revenue,
        "simulated_incremental_contribution_usd": (
            campaign_revenue * config.gross_margin - spend_usd
        ),
        "simulated_roas": campaign_revenue / spend_usd if spend_usd else None,
        "cost_per_campaign_purchase_usd": (
            spend_usd / campaign_count if campaign_count else None
        ),
    }
    context.log.info(
        "campaign_economics (simulation, not measured lift): %s. "
        "ROAS is undefined with zero spend; cost per purchase is undefined "
        "with zero campaign purchases.",
        metrics,
    )
    return metrics


@job
def geo_marketing_sales_dag():
    """Simulate a single store's geo campaign and online-to-offline sales."""
    spend = geo_marketing_spend.alias("marketing_spend")()
    seasonality = geo_seasonality_index.alias("seasonality_index")()
    quality = geo_product_quality_index.alias("product_quality_index")()
    impressions = geo_ad_impressions(spend)
    visits = geo_website_visits.alias("website_visits")(impressions, seasonality)
    online_visits, campaign_store_visits = o2o_journey(visits)
    online_sales = online_purchases(online_visits, seasonality, quality)
    store_sales = store_purchases(campaign_store_visits, seasonality, quality)
    campaign_economics(spend, online_sales, store_sales)


defs = Definitions(jobs=[geo_marketing_sales_dag])
