"""Key ideas extraction from papers."""

import asyncio
import logging
from typing import Optional

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Settings

logger = logging.getLogger(__name__)

KEY_IDEAS_PROMPT = """Extract 3-5 key ideas from this research paper. Each idea should be a concise bullet point (1 sentence).

Title: {title}

Abstract: {abstract}

Provide only the bullet points, one per line, without numbers or bullet symbols."""


class KeyIdeasExtractor:
    """Extract key ideas from papers using LLMs."""

    def __init__(self, settings: Settings):
        """Initialize extractor.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.provider = settings.get_llm_provider()

        if self.provider == "anthropic":
            self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        elif self.provider == "openai":
            self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

        self.rate_limit_delay = 1.0 / settings.llm_rate_limit

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
    )
    async def extract(self, title: str, abstract: str) -> list[str]:
        """Extract key ideas from a paper.

        Args:
            title: Paper title
            abstract: Paper abstract

        Returns:
            List of key ideas
        """
        prompt = KEY_IDEAS_PROMPT.format(title=title, abstract=abstract)

        try:
            if self.provider == "anthropic":
                text = await self._extract_anthropic(prompt)
            else:
                text = await self._extract_openai(prompt)

            # Parse bullet points
            ideas = [line.strip() for line in text.split("\n") if line.strip()]
            ideas = [idea.lstrip("•-*").strip() for idea in ideas]  # Remove bullet symbols
            ideas = [idea for idea in ideas if idea]  # Remove empty lines

            # Rate limiting
            await asyncio.sleep(self.rate_limit_delay)

            return ideas[:5]  # Max 5 ideas

        except Exception as e:
            logger.error(f"Error extracting key ideas: {e}")
            raise

    async def _extract_anthropic(self, prompt: str) -> str:
        """Extract using Claude.

        Args:
            prompt: Prompt text

        Returns:
            Generated text
        """
        response = await self.client.messages.create(
            model=self.settings.summarization_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text

    async def _extract_openai(self, prompt: str) -> str:
        """Extract using OpenAI.

        Args:
            prompt: Prompt text

        Returns:
            Generated text
        """
        response = await self.client.chat.completions.create(
            model=self.settings.summarization_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.choices[0].message.content

    async def batch_extract(
        self, papers: list[tuple[str, str]], batch_size: int = 10
    ) -> list[Optional[list[str]]]:
        """Extract key ideas for multiple papers in batches.

        Args:
            papers: List of (title, abstract) tuples
            batch_size: Number of papers to process in parallel

        Returns:
            List of key ideas lists (None if extraction failed)
        """
        all_ideas = []

        for i in range(0, len(papers), batch_size):
            batch = papers[i : i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(papers)-1)//batch_size + 1}")

            # Process batch in parallel
            tasks = [self.extract(title, abstract) for title, abstract in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Convert exceptions to None
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"Failed to extract key ideas: {result}")
                    all_ideas.append(None)
                else:
                    all_ideas.append(result)

        return all_ideas
