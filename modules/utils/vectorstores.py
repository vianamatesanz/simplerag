from typing import Any, Dict, Mapping, Optional

from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore

from langchain_chroma import Chroma

try:
	from langchain_redis import RedisVectorStore
except ImportError:  # Fallback if langchain-redis is not installed
	RedisVectorStore = None

try:
	from langchain_community.vectorstores import Redis as CommunityRedis
except ImportError:  # Fallback if langchain-community redis backend is missing
	CommunityRedis = None

try:
	from langchain_core.vectorstores import InMemoryVectorStore
except ImportError:  # Backward compatibility
	InMemoryVectorStore = None


class LangChainVectorStoreFactory:
	"""Build LangChain vector stores from provider-based config."""

	def __init__(self, config: Mapping[str, Any], embeddings: Embeddings):
		if not config:
			raise ValueError("Configuration is required.")
		if embeddings is None:
			raise ValueError("An embeddings implementation is required.")

		self.config: Dict[str, Any] = dict(config)
		self.provider = str(self.config.get("provider", "")).strip().lower()
		if not self.provider:
			raise ValueError("Missing 'provider' in configuration.")

		self.embeddings = embeddings

	def build(self) -> VectorStore:
		"""Return a configured vector store instance."""
		if self.provider in {"chroma", "chromadb"}:
			return self._build_chroma()
		if self.provider == "redis":
			return self._build_redis()
		if self.provider in {"memory", "inmemory"}:
			return self._build_inmemory()
		raise ValueError(f"Unsupported vector store provider: {self.provider}")

	def as_retriever(
		self,
		search_type: str = "similarity",
		search_kwargs: Optional[Dict[str, Any]] = None,
	):
		"""Build vector store and return a retriever from it."""
		store = self.build()
		return store.as_retriever(
			search_type=search_type,
			search_kwargs=search_kwargs or {"k": 4},
		)

	def _provider_config(self, *keys: str) -> Dict[str, Any]:
		for key in keys:
			value = self.config.get(key)
			if isinstance(value, Mapping):
				return dict(value)
		return {}

	def _build_chroma(self) -> VectorStore:
		chroma_cfg = self._provider_config("chroma", "chromadb")
		collection_name = chroma_cfg.get("collection_name", "default_collection")
		persist_directory = chroma_cfg.get("persist_directory")

		kwargs: Dict[str, Any] = {
			"collection_name": collection_name,
			"embedding_function": self.embeddings,
		}
		if persist_directory:
			kwargs["persist_directory"] = persist_directory

		return Chroma(**kwargs)

	def _build_redis(self) -> VectorStore:
		redis_cfg = self._provider_config("redis")
		redis_url = redis_cfg.get("redis_url", "redis://localhost:6379")
		index_name = redis_cfg.get("index_name", "default_index")
		options = redis_cfg.get("options", {})

		if RedisVectorStore is not None:
			return RedisVectorStore(
				embeddings=self.embeddings,
				redis_url=redis_url,
				index_name=index_name,
				**options,
			)

		if CommunityRedis is not None:
			return CommunityRedis(
				embedding=self.embeddings,
				redis_url=redis_url,
				index_name=index_name,
				**options,
			)

		raise ImportError(
			"Redis provider requires either 'langchain-redis' or "
			"'langchain-community' with Redis support installed."
		)

	def _build_inmemory(self) -> VectorStore:
		if InMemoryVectorStore is None:
			raise ImportError(
				"In-memory vector store is unavailable in this LangChain version."
			)
		return InMemoryVectorStore(embedding=self.embeddings)
