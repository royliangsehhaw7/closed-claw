import os
import httpx
from dotenv import load_dotenv

from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from core.logger import logger

load_dotenv()

class LLMFactory:
    _instance = None
    _shared_client = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(LLMFactory, cls).__new__(cls)
        return cls._instance

    def __init__(self, organization: str | None = None):
        if not hasattr(self, '_initialized'):
            self._organization = organization or os.getenv("LLM_ORGANIZATION")
            self._initialized = True

    @property
    def client(self) -> httpx.AsyncClient:
        if self._shared_client is None:
            self._shared_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=5.0),
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=20)
            )
        return self._shared_client

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
            provider=GoogleProvider(
                api_key=os.getenv("GEMINI_API_KEY"),
                http_client=self.client
            ),
            settings=GoogleModelSettings(temperature=0.15),
        )

    def _get_openrouter_model(self, name: str) -> OpenRouterModel:
        return OpenRouterModel(
            model_name=name,
            provider=OpenRouterProvider(
                api_key=os.getenv("OPENROUTER_API_KEY"),
                app_url="https://openrouter.ai/api/v1", # <--- RESTORED THIS
                http_client=self.client
            ),
            settings=OpenRouterModelSettings(
                tool_choice="auto",
                temperature=0.15,
                openrouter_provider={
                    "require_parameters": True
                }
            ),
        )




# # from __future__ import annotations

# import os
# from dotenv import load_dotenv

# from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
# from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
# from pydantic_ai.providers.google import GoogleProvider
# from pydantic_ai.providers.openrouter import OpenRouterProvider

# from core.logger import logger

# load_dotenv()


# class LLMFactory:
#     def __init__(self, organization: str | None = None):
#         self._organization = organization or os.getenv("LLM_ORGANIZATION")

#     def get_model(self, model: str | None = None):
#         name = model or os.getenv("LLM_MODEL")
#         logger.debug("LLMFactory | org=%s model=%s", self._organization, name)

#         if self._organization == "gemini":
#             return self._get_google_model(name)
#         return self._get_openrouter_model(name)

#     # -- private
#     def _get_google_model(self, name: str) -> GoogleModel:
#         return GoogleModel(
#             model_name=name,
#             provider=GoogleProvider(api_key=os.getenv("GEMINI_API_KEY")),
#             settings=GoogleModelSettings(temperature=0.15),
#         )

#     def _get_openrouter_model(self, name: str) -> OpenRouterModel:
#         return OpenRouterModel(
#             model_name=name,
#             provider=OpenRouterProvider(
#                 api_key=os.getenv("OPENROUTER_API_KEY"),
#                 app_url="https://openrouter.ai/api/v1",
#                 # app_name=os.getenv("OPENROUTER_APP_NAME") 
#                 # headers={"X-Title": os.getenv("OPENROUTER_APP_NAME", "closed-claw")},            
#             ),
#             settings=OpenRouterModelSettings(
#                 tool_choice="auto",
#                 temperature=0.15,
#                 openrouter_provider={
#                     "require_parameters": True
#                 }
#             ),
#         )