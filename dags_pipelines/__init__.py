"""Dagster code location exposing all project pipelines."""

from dagster import Definitions

from . import arango_to_postgres_leo_cdp as _arango_pipeline
from . import causal_geo_marketing_dag as _causal_geo_marketing_pipeline
from . import causal_sales_dag as _causal_sales_pipeline
from . import hello_world_dag as _hello_pipeline
from . import geo_places_pipeline as _geo_places_pipeline

defs = Definitions.merge(
    _arango_pipeline.defs,
    _causal_geo_marketing_pipeline.defs,
    _causal_sales_pipeline.defs,
    _hello_pipeline.defs,
    _geo_places_pipeline.defs,
)

del (
    _arango_pipeline,
    _causal_geo_marketing_pipeline,
    _causal_sales_pipeline,
    _hello_pipeline,
    _geo_places_pipeline,
)
