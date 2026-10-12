import os
import base64
from functools import lru_cache
import logging
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.types import Schema
from google.api_core.exceptions import GoogleAPIError
from openai import OpenAI
import numpy as np
import json
from typing import Any, Dict, Literal, Sequence, overload

from leoai.ai_data_schema import WEATHER_FORECAST_SCHEMA, GEOLOCATION_SCHEMA
from leoai.domain.report_utils import generate_pie_chart
from leoai.domain.weather_utils import build_weather_prompt, enrich_weather_forecast

# Load environment variables from .env file
load_dotenv(override=True)

# Configure logging
logger = logging.getLogger(__name__)


def _google_response_schema(schema: Schema | dict | None) -> Schema | dict | None:
    """Convert common JSON Schema fields to Google response-schema fields."""
    if not isinstance(schema, dict):
        return schema

    def sanitize(value: Any) -> Any:
        if isinstance(value, dict):
            result = {
                key: sanitize(item)
                for key, item in value.items()
                if key != "additionalProperties"
            }
            schema_type = result.get("type")
            if isinstance(schema_type, list):
                nullable = "null" in schema_type
                non_null_types = [item for item in schema_type if item != "null"]
                if len(non_null_types) == 1:
                    result["type"] = str(non_null_types[0]).upper()
                    if nullable:
                        result["nullable"] = True
            elif isinstance(schema_type, str):
                result["type"] = schema_type.upper()
            return result
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        return value

    return sanitize(schema)

# Default provider/model configuration
AI_PROVIDER = (os.getenv("AI_PROVIDER") or "google").strip().lower()
EMBEDDING_PROVIDER = (os.getenv("EMBEDDING_PROVIDER") or AI_PROVIDER).strip().lower()
DEFAULT_EMBEDDING_MODEL_ID = os.getenv("EMBEDDING_MODEL") or (
    "gemini-embedding-001" if EMBEDDING_PROVIDER == "google"
    else "text-embedding-3-small" if EMBEDDING_PROVIDER == "openai"
    else "openai/text-embedding-3-small"
)
DEFAULT_EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TOUCHPOINT_EMBEDDING_PROVIDER = (
    os.getenv("TOUCHPOINT_EMBEDDING_PROVIDER") or EMBEDDING_PROVIDER
).strip().lower()
TOUCHPOINT_EMBEDDING_MODEL = os.getenv("TOUCHPOINT_EMBEDDING_MODEL") or (
    "gemini-embedding-001"
    if TOUCHPOINT_EMBEDDING_PROVIDER == "google"
    else "text-embedding-3-small"
    if TOUCHPOINT_EMBEDDING_PROVIDER == "openai"
    else "openai/text-embedding-3-small"
)
TOUCHPOINT_EMBEDDING_DIMENSIONS = int(
    os.getenv("TOUCHPOINT_EMBEDDING_DIMENSIONS", "768")
)

SUPPORTED_PROVIDERS = {"google", "openai", "openrouter"}
JSON_TYPE = "application/json"

AI_CHAT_TEMPERATURE = float(os.getenv("AI_CHAT_TEMPERATURE", "0.7"))

def _default_chat_model(provider: str) -> str:
    provider_default = {
        "google": os.getenv("GEMINI_TEXT_MODEL_ID") or "gemini-3.5-flash-lite",
        "openai": "gpt-4.1-mini",
        "openrouter": "openai/gpt-4.1-mini",
    }[provider]
    return os.getenv("AI_CHAT_MODEL") or provider_default

def _default_reasoning_model(provider: str) -> str:
    provider_default = {
        "google": os.getenv("GEMINI_TEXT_MODEL_ID") or "gemini-3.8-flash",
        "openai": "gpt-5.6-luna",
        "openrouter": "openai/gpt-5.6-luna",
    }[provider]
    return os.getenv("AI_REASONING_MODEL") or provider_default

@lru_cache(maxsize=1)
def get_embedding_model():
    """Return a lightweight adapter that requests embeddings from a configured API."""
    return RemoteEmbeddingModel()


@lru_cache(maxsize=1)
def get_touchpoint_embedding_model():
    """Return the dedicated touchpoint embedding adapter."""
    return RemoteEmbeddingModel(
        provider=TOUCHPOINT_EMBEDDING_PROVIDER,
        model_name=TOUCHPOINT_EMBEDDING_MODEL,
        dimensions=TOUCHPOINT_EMBEDDING_DIMENSIONS,
    )


@lru_cache(maxsize=1)
def _get_api_client(provider: str, api_key: str) -> Any:
    if provider == "google":
        return genai.Client(api_key=api_key)
    if provider == "openai":
        return OpenAI(api_key=api_key)
    if provider == "openrouter":
        return OpenAI(
            api_key=api_key,
            base_url=os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1",
        )
    raise ValueError(f"Unsupported AI provider '{provider}'.")


def _provider_api_key(provider: str, *, embedding: bool = False) -> str:
    if embedding and os.getenv("EMBEDDING_API_KEY"):
        return os.environ["EMBEDDING_API_KEY"]
    key_name = {
        "google": "GEMINI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }.get(provider)
    if key_name is None:
        raise ValueError(
            f"Unsupported AI provider '{provider}'. Choose google, openai, or openrouter."
        )
    api_key = os.getenv(key_name)
    if not api_key:
        raise ValueError(f"{key_name} must be set to use the {provider} provider.")
    return api_key


class RemoteEmbeddingModel:
    """Lightweight adapter over hosted embedding APIs."""

    @overload
    def encode(
        self,
        sentences: str,
        batch_size: int = 32,
        normalize_embeddings: bool = True,
        convert_to_numpy: Literal[True] = True,
        **kwargs: Any,
    ) -> np.ndarray: ...

    @overload
    def encode(
        self,
        sentences: Sequence[str],
        batch_size: int = 32,
        normalize_embeddings: bool = True,
        convert_to_numpy: Literal[True] = True,
        **kwargs: Any,
    ) -> np.ndarray: ...

    @overload
    def encode(
        self,
        sentences: str,
        batch_size: int = 32,
        normalize_embeddings: bool = True,
        convert_to_numpy: Literal[False] = False,
        **kwargs: Any,
    ) -> list[float]: ...

    @overload
    def encode(
        self,
        sentences: Sequence[str],
        batch_size: int = 32,
        normalize_embeddings: bool = True,
        convert_to_numpy: Literal[False] = False,
        **kwargs: Any,
    ) -> list[list[float]]: ...

    def __init__(
        self,
        provider: str = EMBEDDING_PROVIDER,
        model_name: str = DEFAULT_EMBEDDING_MODEL_ID,
        dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
    ):
        self.provider = provider
        self.model_name = model_name
        self.dimensions = dimensions

    def encode(
        self,
        sentences: str | Sequence[str],
        batch_size: int = 32,
        normalize_embeddings: bool = True,
        convert_to_numpy: bool = True,
        **_: Any,
    ):
        is_single = isinstance(sentences, str)
        texts = [sentences] if is_single else list(sentences)
        if not texts:
            empty = np.empty((0, self.dimensions), dtype=np.float32)
            return empty if convert_to_numpy else empty.tolist()
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Embedding inputs must be non-empty strings.")

        api_key = _provider_api_key(self.provider, embedding=True)
        client: Any = _get_api_client(self.provider, api_key)
        vectors: list[list[float]] = []
        for offset in range(0, len(texts), max(1, batch_size)):
            batch = texts[offset:offset + max(1, batch_size)]
            if self.provider == "google":
                for text in batch:
                    result = client.models.embed_content(
                        model=self.model_name,
                        contents=text,
                        config=types.EmbedContentConfig(
                            output_dimensionality=self.dimensions,
                        ),
                    )
                    if not result.embeddings or result.embeddings[0].values is None:
                        raise RuntimeError("Google GenAI returned an empty embedding.")
                    vectors.append(result.embeddings[0].values)
            else:
                response = client.embeddings.create(
                    model=self.model_name,
                    input=batch,
                    dimensions=self.dimensions,
                )
                vectors.extend(
                    item.embedding for item in sorted(response.data, key=lambda item: item.index)
                )

        if len(vectors) != len(texts):
            raise RuntimeError(
                f"Embedding provider returned {len(vectors)} vectors for {len(texts)} inputs."
            )
        embeddings = np.asarray(vectors, dtype=np.float32)
        if embeddings.shape != (len(texts), self.dimensions):
            raise RuntimeError(
                f"Expected embeddings shaped ({len(texts)}, {self.dimensions}), "
                f"got {embeddings.shape}."
            )
        if normalize_embeddings:
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            embeddings = np.divide(
                embeddings, norms, out=np.zeros_like(embeddings), where=norms != 0
            )

        result = embeddings[0] if is_single else embeddings
        return result if convert_to_numpy else result.tolist()


# the helper function for default embedding_model
def get_embed_texts(texts):
    """
    Embed a list of texts using the configured hosted embedding API.

    Args:
        texts (list[str]): List of text strings to embed.

    Returns:
        list[list[float]]: List of vector embeddings.
    """
    if not texts:
        logger.warning("embed_texts called with empty input list.")
        return []

    if isinstance(texts, str):
        texts = [texts]
    normalized_texts = [text.strip() for text in texts if text and text.strip()]
    if not normalized_texts:
        logger.warning("All input texts were empty or whitespace.")
        return []
    return get_embedding_model().encode(
        normalized_texts,
        batch_size=16,
        normalize_embeddings=True,
    ).tolist()


# check and init Google AI
def is_gemini_model_ready():
    return bool(GEMINI_API_KEY)


def is_ai_model_ready() -> bool:
    key_name = {
        "google": "GEMINI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }.get(AI_PROVIDER)
    return bool(key_name and os.getenv(key_name))


class AIClient:
    """
    Provider-neutral text and multimodal generation client.
    """

    def __init__(
        self,
        model_name: str | None = None,
        reasoning_model_name: str | None = None,
        api_key: str | None = None,
        provider: str | None = None,
    ):
        self.provider = (provider or AI_PROVIDER).strip().lower()
        if self.provider not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported AI provider '{self.provider}'. Choose google, openai, or openrouter."
            )
        self.model_name = model_name or _default_chat_model(self.provider)
        self.reasoning_model_name = reasoning_model_name or _default_reasoning_model(self.provider)
        self.api_key = api_key or _provider_api_key(self.provider)
        self.client: Any = _get_api_client(self.provider, self.api_key)
        logger.info("%s AI client initialized with model '%s'", self.provider, self.model_name)

    def _generate_response(
        self,
        prompt: str,
        temperature: float = AI_CHAT_TEMPERATURE,
        json_schema: Schema | dict | None = None,
        image_bytes: bytes | None = None,
        max_output_tokens: int | None = None,
        system_instruction: str | None = None,
    ) -> str:
        if self.provider == "google":
            config = types.GenerateContentConfig.model_validate({
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
                "response_mime_type": JSON_TYPE if json_schema is not None else None,
                "response_schema": _google_response_schema(json_schema),
                "system_instruction": system_instruction,
            })
            contents: str | list[Any] = prompt
            if image_bytes is not None:
                contents = [
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    prompt,
                ]
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )
            return (response.text or "").strip()

        content: Any = prompt
        if image_bytes is not None:
            image_data = base64.b64encode(image_bytes).decode("ascii")
            content = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                },
            ]
        if json_schema is not None:
            schema_data = (
                json_schema.model_dump(mode="json", exclude_none=True)
                if isinstance(json_schema, Schema)
                else json_schema
            )
            content = (
                f"{prompt}\n\nReturn a JSON object conforming to this schema:\n"
                f"{json.dumps(schema_data, ensure_ascii=False)}"
                if image_bytes is None
                else [
                    {
                        "type": "text",
                        "text": (
                            f"{prompt}\n\nReturn a JSON object conforming to this schema:\n"
                            f"{json.dumps(schema_data, ensure_ascii=False)}"
                        ),
                    },
                    content[1],
                ]
            )
        request: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": content}],
            "temperature": temperature,
        }
        if system_instruction:
            request["messages"].insert(0, {
                "role": "system", "content": system_instruction,
            })
        if json_schema is not None:
            request["response_format"] = {"type": "json_object"}
        if max_output_tokens is not None:
            request["max_tokens"] = max_output_tokens
        response = self.client.chat.completions.create(**request)
        return (response.choices[0].message.content or "").strip()

    # text to text
    def generate_content(
        self,
        prompt: str,
        temperature: float = AI_CHAT_TEMPERATURE,
        on_error: str = '',
        max_output_tokens: int | None = None,
        *,
        system_instruction: str | None = None,
    ) -> str:
        """
        Generate text from a prompt using the configured AI provider.

        Args:
            prompt (str): The input prompt to send to the model.
            temperature (float): Sampling temperature for creativity.
            on_error (str): Fallback string if generation fails.

        Returns:
            str: Generated content or fallback string.
        """
        try:
            text = self._generate_response(
                prompt,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                system_instruction=system_instruction,
            )
            if text:
                return text
            else:
                logger.warning("Empty response received from %s.", self.provider)
                return on_error

        except GoogleAPIError as e:
            logger.error(f"Google API error during content generation: {e}")
            return on_error
        except Exception as e:
            logger.exception("Unexpected error during content generation.")
            return on_error

    # text to JSON
    def generate_json(
        self,
        prompt: str,
        json_schema: Schema | dict[str, Any],
        *,
        system_instruction: str | None = None,
    ) -> Dict[str, Any]:
        """
        Generates a structured JSON object from a prompt based on a provided schema.

        Args:
            prompt: Input prompt for the model.
            json_schema: Google GenAI schema or JSON schema dictionary.

        Returns:
            A dictionary parsed from the model's JSON response, or an empty dict on error.
        """
        try:
            response_text = self._generate_response(
                prompt,
                json_schema=json_schema,
                system_instruction=system_instruction,
            )
            return json.loads(response_text)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON from model response: {e}")
            return {}
        except GoogleAPIError as e:
            logger.error(f"A Google API error occurred: {e}")
            return {}
        except Exception as e:
            logger.exception(
                f"An unexpected error occurred in generate_json: {e}")
            return {}

    def generate_geolocation_from_image(
        self,
        text_prompt: str,
        image_bytes: bytes,
        json_schema: Schema | None = None,
        temperature: float = 0.25,
        on_error: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Generate structured geolocation JSON using text + image input.

        Args:
            text_prompt (str): Natural language prompt describing what to extract.
            image_bytes (bytes): Raw image file content.
            json_schema (Schema): Output schema (GEOLOCATION_SCHEMA schema).
            temperature (float): Model creativity level.
            on_error (dict): Fallback dict if generation fails.

        Returns:
            dict: Parsed JSON adhering to GEOLOCATION_SCHEMA schema.
        """
        # Nếu on_error là None, khởi tạo nó là một dictionary rỗng
        if on_error is None:
            on_error = {}

        # Kiểm tra và sử dụng schema mặc định nếu chưa được cung cấp
        if json_schema is None:
            # Giả định GEOLOCATION_SCHEMA đã được import và là một object Schema hợp lệ
            json_schema = GEOLOCATION_SCHEMA
            logger.debug("Using default GEOLOCATION_SCHEMA.")

        try:
            response_text = self._generate_response(
                text_prompt,
                temperature=temperature,
                json_schema=json_schema,
                image_bytes=image_bytes,
            )

            if not response_text:
                logger.warning(
                    "Empty JSON response received from %s.", self.provider)
                return on_error

            return json.loads(response_text)

        except GoogleAPIError as e:
            logger.error("Google API error in geolocation generation: %s", e)
            return on_error

        except json.JSONDecodeError as e:
            logger.error(
                f"JSON decode failed. Model response was not valid JSON: {e}")
            return on_error

        except Exception:
            logger.exception("Unexpected error in geolocation generation.")
            return on_error

    def generate_weather_info_from_text(
        self,
        raw_weather_text: str,
        json_schema: Schema | None = None,
        temperature: float = 0.2,
        limit_days: int = 0,
        on_error: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Convert raw Windy.com scraped text into structured JSON weather info.

        Args:
            raw_weather_text (str): The extracted innerText from Windy (file.txt).
            model (AIClient): Optional injected AI client.
            json_schema (Schema): Output schema for structured weather forecasting.
            temperature (float): Model creativity level.
            on_error (dict): Fallback dictionary.

        Returns:
            dict: Weather forecast JSON following WEATHER_FORECAST_SCHEMA.
        """
        if on_error is None:
            on_error = {}

        # Use default weather schema if not provided
        if json_schema is None:
            json_schema = WEATHER_FORECAST_SCHEMA

        # Clean & normalize the raw text
        if not isinstance(raw_weather_text, str) or not raw_weather_text.strip():
            logger.warning(
                "generate_weather_info_from_text received empty input text.")
            return on_error

        cleaned_text = raw_weather_text.strip()

        # Prompt for the LLM
        prompt = build_weather_prompt(json_schema, cleaned_text, limit_days)
        try:
            text = self._generate_response(
                prompt,
                temperature=temperature,
                json_schema=json_schema,
            )
            if not text:
                logger.error(
                    "Empty JSON response in generate_weather_info_from_text.")
                return on_error

            weather_info = enrich_weather_forecast(text)
            return weather_info

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode failed from model response: {e}")
            return on_error

        except GoogleAPIError as e:
            logger.error(f"Google API error: {e}")
            return on_error

        except Exception:
            logger.exception("Unexpected error in generate_weather_info_from_text.")
            return on_error

    def get_embedding(self, text: str) -> list[float]:
        """ get embedding of text

        Args:
            text (str): input text

        Returns:
            list[float]: embedding of text
        """
        return get_embedding_model().encode(
            text, normalize_embeddings=True
        ).tolist()

    def generate_report(self, prompt: str, temperature: float = 0.6, on_error: str = '') -> str:
        return generate_pie_chart()


GeminiClient = AIClient
