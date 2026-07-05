def try_get_port_from_upstream_host(upstream_host: str) -> int | None:
    if not upstream_host:
        return None

    loc = upstream_host.rfind(":")
    if loc == -1:
        return None
    port_str = upstream_host[loc + 1 :]

    try:
        # todo - can there be ipv6 without port?
        return int(port_str)
    except ValueError:
        return None
