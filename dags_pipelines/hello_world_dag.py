"""A minimal Dagster job demonstrating runtime-configurable op input."""

from datetime import datetime

from dagster import Config, Definitions, OpExecutionContext, job, op


class GreetingConfig(Config):
    name: str = "World"


@op
def hello(context: OpExecutionContext, config: GreetingConfig) -> None:
    """Log a greeting using the configured name."""
    context.log.info("==========================================")
    context.log.info("Hello from Dagster!")
    context.log.info("The submitted name parameter is: %s", config.name)
    context.log.info("Today is %s", datetime.now())
    context.log.info("==========================================")


@job
def hello_world():
    hello()


defs = Definitions(jobs=[hello_world])
