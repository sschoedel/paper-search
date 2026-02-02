"""Embedding generation for papers."""

import asyncio
import logging
from typing import Optional

import numpy as np
from openai import AsyncOpenAI
from sentence_transformers import SentenceTransformer
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Settings

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generate embeddings for papers with configurable provider."""

    def __init__(self, settings: Settings):
        """Initialize embedding generator.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.provider = settings.get_embedding_provider()

        if self.provider == "local":
            logger.info(f"Loading local embedding model: {settings.embedding_model}")
            model_name = settings.embedding_model.replace("sentence-transformers/", "")
            self.model = SentenceTransformer(model_name)
            self.client = None
        elif self.provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY required for OpenAI embeddings")
            self.client = AsyncOpenAI(api_key=settings.openai_api_key)
            self.model = None
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

        self.rate_limit_delay = 1.0 / settings.llm_rate_limit

    async def generate(self, text: str) -> bytes:
        """Generate embedding for text.

        Args:
            text: Text to embed

        Returns:
            Embedding as bytes (numpy array serialized)
        """
        if self.provider == "local":
            embedding = await self._generate_local(text)
        else:
            embedding = await self._generate_openai(text)

        # Convert to bytes for storage
        return embedding.astype(np.float32).tobytes()

    async def _generate_local(self, text: str) -> np.ndarray:
        """Generate embedding using local model.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(None, self.model.encode, text)
        return embedding

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
    )
    async def _generate_openai(self, text: str) -> np.ndarray:
        """Generate embedding using OpenAI API.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        response = await self.client.embeddings.create(
            model=self.settings.embedding_model,
            input=text,
        )

        # Rate limiting
        await asyncio.sleep(self.rate_limit_delay)

        return np.array(response.data[0].embedding)

    async def generate_for_paper(
        self, title: str, abstract: str, summary: Optional[str] = None
    ) -> bytes:
        """Generate embedding for a paper.

        Combines title, abstract, and optional summary.

        Args:
            title: Paper title
            abstract: Paper abstract
            summary: Optional AI-generated summary

        Returns:
            Embedding as bytes
        """
        # Combine fields with weights
        text_parts = [title, title, abstract]  # Title twice for emphasis
        if summary:
            text_parts.append(summary)

        combined_text = " ".join(text_parts)

        # Truncate to avoid token limits
        max_chars = 8000 if self.provider == "local" else 6000
        if len(combined_text) > max_chars:
            combined_text = combined_text[:max_chars]

        return await self.generate(combined_text)

    async def batch_generate(
        self, texts: list[str], batch_size: int = 32
    ) -> list[Optional[bytes]]:
        """Generate embeddings for multiple texts in batches.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts to process in parallel

        Returns:
            List of embeddings (None if generation failed)
        """
        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}")

            # Process batch in parallel
            tasks = [self.generate(text) for text in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Convert exceptions to None
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"Failed to generate embedding: {result}")
                    embeddings.append(None)
                else:
                    embeddings.append(result)

        return embeddings
