"""LLM-based paper summarization."""

import asyncio
import logging
from typing import Optional

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Settings

logger = logging.getLogger(__name__)

SUMMARIZATION_PROMPT = """Please summarize this research paper in 2-3 clear, concise sentences. Focus on:
1. What problem does the paper address?
2. What is the key approach or contribution?
3. What are the main results or findings?

Title: {title}

Abstract: {abstract}

Provide only the summary, no additional commentary."""


class Summarizer:
    """LLM-based paper summarizer with configurable provider."""

    def __init__(self, settings: Settings):
        """Initialize summarizer.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.provider = settings.get_llm_provider()

        if self.provider == "anthropic":
            if not settings.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY required for Claude models")
            self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        elif self.provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY required for OpenAI models")
            self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

        self.rate_limit_delay = 1.0 / settings.llm_rate_limit

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
    )
    async def summarize(self, title: str, abstract: str) -> str:
        """Generate summary for a paper.

        Args:
            title: Paper title
            abstract: Paper abstract

        Returns:
            Generated summary
        """
        prompt = SUMMARIZATION_PROMPT.format(title=title, abstract=abstract)

        try:
            if self.provider == "anthropic":
                summary = await self._summarize_anthropic(prompt)
            else:
                summary = await self._summarize_openai(prompt)

            # Rate limiting
            await asyncio.sleep(self.rate_limit_delay)

            return summary

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            raise

    async def _summarize_anthropic(self, prompt: str) -> str:
        """Generate summary using Claude.

        Args:
            prompt: Prompt text

        Returns:
            Generated summary
        """
        response = await self.client.messages.create(
            model=self.settings.summarization_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text

    async def _summarize_openai(self, prompt: str) -> str:
        """Generate summary using OpenAI.

        Args:
            prompt: Prompt text

        Returns:
            Generated summary
        """
        response = await self.client.chat.completions.create(
            model=self.settings.summarization_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.choices[0].message.content

    async def batch_summarize(
        self, papers: list[tuple[str, str]], batch_size: int = 10
    ) -> list[Optional[str]]:
        """Generate summaries for multiple papers in batches.

        Args:
            papers: List of (title, abstract) tuples
            batch_size: Number of papers to process in parallel

        Returns:
            List of summaries (None if generation failed)
        """
        summaries = []

        for i in range(0, len(papers), batch_size):
            batch = papers[i : i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(papers)-1)//batch_size + 1}")

            # Process batch in parallel
            tasks = [self.summarize(title, abstract) for title, abstract in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Convert exceptions to None
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"Failed to generate summary: {result}")
                    summaries.append(None)
                else:
                    summaries.append(result)

        return summaries
