"""Indexer configuration from environment variables.

Secrets discipline: the RPC password is NEVER printed, logged, or echoed in
an exception body.  __repr__/__str__ mask it.  (Same house rule as
walletbench: credentials stay out of count-only log lines and out of error
messages.)
"""

import os

CHAIN_NAME = "main"

_DEFAULTS = {
    "MAZA_INDEXER_RPC_URL": "http://127.0.0.1:12832",
    "MAZA_INDEXER_RPC_USER": "",
    "MAZA_INDEXER_RPC_PASSWORD": "",
    "MAZA_INDEXER_DATADIR": "./maza-indexer-data",
    "MAZA_INDEXER_BIND": "127.0.0.1:18711",
    "MAZA_INDEXER_BATCH": "24",
    "MAZA_INDEXER_RATE": "60",
}


def _parse_bind(bind: str) -> tuple:
    """Strict MAZA_INDEXER_BIND parsing -> (host, port).

    Accepted forms: host:port (IPv4 or hostname) and bracketed IPv6
    [addr]:port (brackets stripped for the bind call).  Anything else --
    missing host, missing/non-integer/out-of-range port, unbracketed IPv6 --
    raises ValueError with a one-line reason naming the env key.  No raw
    int()/gaierror tracebacks reach the operator.
    """
    key = "MAZA_INDEXER_BIND"
    if bind.startswith("["):
        end = bind.find("]")
        if end < 0 or end + 1 >= len(bind) or bind[end + 1] != ":":
            raise ValueError(
                f"{key}: bracketed IPv6 must be [host]:port, got {bind!r}")
        host, port_s = bind[1:end], bind[end + 2:]
    else:
        if bind.count(":") != 1:
            raise ValueError(
                f"{key}: must be host:port (bracket [addr]:port for IPv6), "
                f"got {bind!r}")
        host, _, port_s = bind.partition(":")
    if not host:
        raise ValueError(f"{key}: missing host in {bind!r}")
    if not port_s.isdigit():
        raise ValueError(f"{key}: port must be an integer in {bind!r}")
    port = int(port_s)
    if not 1 <= port <= 65535:
        raise ValueError(f"{key}: port {port} out of range 1-65535 in {bind!r}")
    return host, port


class IndexerConfig:
    """All knobs in one object; password masked in repr/str."""

    def __init__(self, rpc_url, rpc_user, rpc_password, datadir, host,
                 port, batch, rate):
        self.rpc_url = rpc_url
        self.rpc_user = rpc_user
        self.rpc_password = rpc_password
        self.datadir = datadir
        self.host = host
        self.port = port
        self.batch = batch
        self.rate = rate

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        bind = env.get("MAZA_INDEXER_BIND", _DEFAULTS["MAZA_INDEXER_BIND"])
        host, port = _parse_bind(bind)
        return cls(
            rpc_url=env.get("MAZA_INDEXER_RPC_URL",
                            _DEFAULTS["MAZA_INDEXER_RPC_URL"]),
            rpc_user=env.get("MAZA_INDEXER_RPC_USER",
                             _DEFAULTS["MAZA_INDEXER_RPC_USER"]),
            rpc_password=env.get("MAZA_INDEXER_RPC_PASSWORD",
                                 _DEFAULTS["MAZA_INDEXER_RPC_PASSWORD"]),
            datadir=env.get("MAZA_INDEXER_DATADIR",
                            _DEFAULTS["MAZA_INDEXER_DATADIR"]),
            host=host,
            port=port,
            batch=int(env.get("MAZA_INDEXER_BATCH",
                              _DEFAULTS["MAZA_INDEXER_BATCH"])),
            rate=int(env.get("MAZA_INDEXER_RATE",
                             _DEFAULTS["MAZA_INDEXER_RATE"])),
        )

    @property
    def db_path(self) -> str:
        return os.path.join(self.datadir, "maza_indexer.db")

    @property
    def cursor_path(self) -> str:
        return os.path.join(self.datadir, "cursor.json")

    def __repr__(self):
        return ("IndexerConfig(rpc_url={!r}, rpc_user={!r}, rpc_password=***, "
                "datadir={!r}, bind={}:{})".format(
                    self.rpc_url, self.rpc_user, self.datadir,
                    self.host, self.port))

    __str__ = __repr__
