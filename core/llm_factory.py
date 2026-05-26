# from __future__ import annotations

import os
from dotenv import load_dotenv

from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from core.logger import logger

load_dotenv()


class LLMFactory:
    def __init__(self, organization: str | None = None):
        self._organization = organization or os.getenv("LLM_ORGANIZATION")

    def get_model(self, model: str | None = None):
        name = model or os.getenv("LLM_MODEL")
        logger.debug("LLMFactory | org=%s model=%s", self._organization, name)

        if self._organization == "gemini":
            return self._get_google_model(name)
        return self._get_openrouter_model(name)

    # -- private
    def _get_google_model(self, name: str) -> GoogleModel:
        return GoogleModel(
            model_name=name,
            provider=GoogleProvider(api_key=os.getenv("GEMINI_API_KEY")),
            settings=GoogleModelSettings(temperature=0.15),
        )

    def _get_openrouter_model(self, name: str) -> OpenRouterModel:
        return OpenRouterModel(
            model_name=name,
            provider=OpenRouterProvider(
                api_key=os.getenv("OPENROUTER_API_KEY"),
                app_url="https://openrouter.ai/api/v1",
            ),
            settings=OpenRouterModelSettings(
                # tool_choice="auto",
                temperature=0.15,
                openrouter_provider={
                    "require_parameters": True
                }
            ),
        )