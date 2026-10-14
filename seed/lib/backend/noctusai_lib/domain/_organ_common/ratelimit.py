"""Rate-limit wrapper for the organs' PUBLIC routes.

`rate_limit` is the host's decorator factory (`(limit_string) -> decorator`, e.g. slowapi's `limiter.limit`).
Optional: a host without a limiter mounts unthrottled routes (the organ suites do).
"""
from __future__ import annotations

from typing import Callable, Optional, get_type_hints

#: `(limit_string) -> decorator`.
RateLimit = Callable[[str], Callable[[Callable], Callable]]


def apply_rate_limit(rate_limit: Optional[RateLimit], limit: str, fn: Callable) -> Callable:
    """Wrap `fn` with the host's rate-limit decorator, keeping its annotations resolvable.

    Organ router modules use `from __future__ import annotations`, so a handler's annotations are STRINGS resolved
    against the defining function's `__globals__`. A real decorator (slowapi's `limiter.limit`) returns a wrapper
    from ANOTHER module: FastAPI would then look the strings up in the wrapper's globals, not find `UUID` /
    `Request` / the body models, and every wrapped route would 500 ("TypeAdapter ... not fully defined"). Resolving
    them here, against the handler's OWN module, before wrapping makes the wrapper carry real types. A pass-through
    limiter never wrapped, so only a real one (prod) exposed it.
    """
    if rate_limit is None:
        return fn
    fn.__annotations__ = get_type_hints(fn, include_extras=True)
    return rate_limit(limit)(fn)


__all__ = ["RateLimit", "apply_rate_limit"]
