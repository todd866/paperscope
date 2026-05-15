"""Per-publisher adapters for PDF acquisition.

Dispatch order matters: publisher-specific adapters are checked first,
the generic fallback last. The driver iterates `ALL_ADAPTERS` and picks
the first whose `can_handle(doi, current_url)` returns True.
"""

from .base import HarvestAttempt, Outcome, PublisherAdapter, magic_bytes_ok, sha256_of, utc_now
from .elsevier import ElsevierAdapter
from .generic import GenericAdapter
from .jama_network import JamaNetworkAdapter
from .karger import KargerAdapter
from .lippincott import LippincottAdapter
from .scielo import SciELOAdapter
from .springer import SpringerAdapter
from .taylor_francis import TaylorFrancisAdapter
from .thieme import ThiemeAdapter
from .wiley import WileyAdapter


# Publisher-specific adapters first, generic last.
ALL_ADAPTERS: tuple[type[PublisherAdapter], ...] = (
    JamaNetworkAdapter,
    ElsevierAdapter,
    WileyAdapter,
    TaylorFrancisAdapter,
    SpringerAdapter,
    SciELOAdapter,
    KargerAdapter,
    ThiemeAdapter,
    LippincottAdapter,
    GenericAdapter,
)


def pick_adapter(doi: str, current_url: str) -> PublisherAdapter:
    """Pick the first adapter whose can_handle returns True. Always non-None;
    GenericAdapter is the last-resort fallback."""
    for cls in ALL_ADAPTERS:
        if cls.can_handle(doi, current_url):
            return cls()
    return GenericAdapter()


__all__ = [
    "ALL_ADAPTERS",
    "ElsevierAdapter",
    "GenericAdapter",
    "HarvestAttempt",
    "JamaNetworkAdapter",
    "KargerAdapter",
    "LippincottAdapter",
    "Outcome",
    "PublisherAdapter",
    "SciELOAdapter",
    "SpringerAdapter",
    "TaylorFrancisAdapter",
    "ThiemeAdapter",
    "WileyAdapter",
    "magic_bytes_ok",
    "pick_adapter",
    "sha256_of",
    "utc_now",
]
