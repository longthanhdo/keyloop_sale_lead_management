from contextvars import ContextVar

correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)
dealership_id_ctx: ContextVar[str | None] = ContextVar("dealership_id", default=None)


def get_correlation_id() -> str | None:
    return correlation_id_ctx.get()


def get_dealership_id_ctx() -> str | None:
    return dealership_id_ctx.get()
