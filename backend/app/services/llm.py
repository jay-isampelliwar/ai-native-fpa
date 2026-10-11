"""The one place the app gets a chat model from, with or without tools attached."""

from collections.abc import Sequence

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from app.core.config import get_settings


class LLMService:

    """Builds each chat model once and hands the same instance to every caller."""

    def __init__(self) -> None:

        """Start with no models built, so nothing is created until it is first needed."""

        self.models: dict[str, ChatOpenAI] = {}

    def get_model(self, model: str | None = None) -> ChatOpenAI:

        """Return the chat model by name, CHAT_MODEL by default, building it on first use."""

        settings = get_settings()

        name = model or settings.CHAT_MODEL

        if name not in self.models:
            self.models[name] = ChatOpenAI(model=name, api_key=settings.OPENAI_API_KEY)

        return self.models[name]

    def with_tools(
        self,
        tools: Sequence[BaseTool],
        model: str | None = None,
        ) -> Runnable[LanguageModelInput, AIMessage]:

        """Return the chat model with these tools attached, so the model can ask to call them."""

        return self.get_model(model).bind_tools(tools)


llm_service = LLMService()
