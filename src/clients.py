"""Factories para los clientes de OpenSearch y Qdrant."""

from opensearchpy import OpenSearch
from qdrant_client import QdrantClient

from . import config


def get_opensearch() -> OpenSearch:
    return OpenSearch(
        hosts=[{"host": config.OPENSEARCH_HOST, "port": config.OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=config.OPENSEARCH_USE_SSL,
        verify_certs=False,
        ssl_show_warn=False,
        timeout=60,
        max_retries=3,
        retry_on_timeout=True,
    )


def get_qdrant() -> QdrantClient:
    return QdrantClient(url=config.QDRANT_URL)
