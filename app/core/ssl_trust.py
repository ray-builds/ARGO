"""TLS trust: use the OS certificate store with Python (fixes MSAL on Windows / many proxies).

By default we call ``truststore.inject_into_ssl()`` at app startup so ``requests`` /
MSAL validate chains against the same roots as the browser (e.g. Windows Certificate
Store), not only certifi's bundle — the usual fix for
``SSLCertVerificationError: unable to get local issuer certificate``.
"""
from __future__ import annotations

import sys

from loguru import logger

_PATCHED = False


def inject_os_ssl_context() -> None:
    """Patch Python's SSL stack to use the OS trust store (Windows / macOS / Linux).

    No-op if ``USE_OS_SSL_TRUST=false`` in settings, or if ``truststore`` is missing.
    Safe to call multiple times (injects once per process).
    """
    global _PATCHED
    from app.config import get_settings

    settings = get_settings()
    if not settings.use_os_ssl_trust:
        logger.info("OS SSL trust injection disabled (use_os_ssl_trust=false)")
        return

    if _PATCHED:
        return

    try:
        import truststore
    except ImportError:
        logger.warning(
            "truststore is not installed — Microsoft login may fail with SSL errors on "
            "Windows or behind a corporate proxy. Run: pip install truststore"
        )
        return

    truststore.inject_into_ssl()
    _PATCHED = True
    logger.info("TLS: using OS certificate store via truststore (platform={})", sys.platform)
