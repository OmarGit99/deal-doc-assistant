"""Build the embedding model named in the settings."""

from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings

from app.config import Settings


def make_embeddings(settings: Settings) -> Embeddings:
    if settings.embedding_provider == "fake":
        # Same text -> same vector, no network. For tests only: it knows nothing of meaning.
        return DeterministicFakeEmbedding(size=settings.embedding_dimensions)

    if settings.embedding_provider == "openai":
        if settings.openai_api_key is None:
            raise RuntimeError("Set OPENAI_API_KEY in .env, or choose another EMBEDDING_PROVIDER")
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            openai_api_key=settings.openai_api_key,
            max_retries=3,
        )

    try:
        from langchain_huggingface import HuggingFaceEmbeddings  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "EMBEDDING_PROVIDER=local needs: uv add langchain-huggingface sentence-transformers"
        ) from exc
    embeddings: Embeddings = HuggingFaceEmbeddings(
        model_name=settings.embedding_model, encode_kwargs={"normalize_embeddings": True}
    )
    return embeddings
