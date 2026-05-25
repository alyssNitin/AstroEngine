"""
backend/services
=================
Service-client layer for the NarayanAstroReader monolith.

When USE_MICROSERVICES=true each client calls the corresponding
microservice over HTTP. When false (default) it delegates to the
local implementation — no deployment changes required.

Usage::

    from backend.services import get_dasha_client

    client = get_dasha_client()
    result = client.calculate(birth_chart=chart, system="vimshottari")
"""
