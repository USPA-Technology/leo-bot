"""Independent, illustrative website sales funnel implemented as a Dagster job."""

from dagster import Config, Definitions, OpExecutionContext, job, op
from pydantic import Field


class MarketingSpendConfig(Config):
    thousands_usd: float = Field(default=10.0, ge=0)


class SeasonalityConfig(Config):
    index: float = Field(default=0.5, ge=0, le=1)


class ProductQualityConfig(Config):
    index: float = Field(default=0.7, ge=0, le=1)


@op
def marketing_spend(
    context: OpExecutionContext, config: MarketingSpendConfig
) -> float:
    """Return marketing spend in thousands of USD."""
    context.log.info(
        "marketing_spend = %.2f thousand USD (exogenous input)",
        config.thousands_usd,
    )
    return config.thousands_usd


@op
def seasonality_index(
    context: OpExecutionContext, config: SeasonalityConfig
) -> float:
    """Return a seasonality index between zero and one."""
    context.log.info(
        "seasonality_index = %.2f (exogenous input; range 0 to 1)",
        config.index,
    )
    return config.index


@op
def product_quality_index(
    context: OpExecutionContext, config: ProductQualityConfig
) -> float:
    """Return a product quality index between zero and one."""
    context.log.info(
        "product_quality_index = %.2f (exogenous input; range 0 to 1)",
        config.index,
    )
    return config.index


@op
def ad_impressions(
    context: OpExecutionContext, spend_thousands_usd: float
) -> float:
    """Estimate impressions, in thousands, from marketing spend."""
    impressions_thousands = spend_thousands_usd * 100
    context.log.info(
        "ad_impressions = 100 * %.2f thousand USD = %.2f thousand impressions",
        spend_thousands_usd,
        impressions_thousands,
    )
    return impressions_thousands


@op
def website_visits(
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
def purchases(
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
        "purchases = %.2f thousand visits * "
        "(0.02 + 0.03 * %.2f quality + 0.01 * %.2f seasonality) "
        "= %.2f thousand purchases (conversion rate: %.1f%%)",
        visits_thousands,
        product_quality_index,
        seasonality_index,
        estimated_purchases,
        conversion_rate * 100,
    )
    return estimated_purchases


@job
def causal_sales_dag():
    """Model assumed causal paths from inputs to estimated purchases."""
    spend = marketing_spend()
    seasonality = seasonality_index()
    quality = product_quality_index()
    impressions = ad_impressions(spend)
    visits = website_visits(impressions, seasonality)
    purchases(visits, seasonality, quality)


defs = Definitions(jobs=[causal_sales_dag])
