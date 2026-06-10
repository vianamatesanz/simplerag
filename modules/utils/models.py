import os
from typing import Any, Dict, Mapping, Optional

import httpx

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

try:
	from langchain_huggingface import ChatHuggingFace, HuggingFaceEmbeddings, HuggingFaceEndpoint
except ImportError:  # Backward compatibility
	from langchain_community.chat_models import ChatHuggingFace
	from langchain_community.embeddings import HuggingFaceEmbeddings
	from langchain_community.llms import HuggingFaceEndpoint


class LangChainModelFactory:
	"""Build LangChain embeddings or chat models from a provider-based config."""

	def __init__(self, config: Mapping[str, Any]):
		if not config:
			raise ValueError("Configuration is required.")

		self.config: Dict[str, Any] = dict(config)
		self.provider = str(self.config.get("provider", "")).strip().lower()
		if not self.provider:
			raise ValueError("Missing 'provider' in configuration.")

	def build_embeddings(self) -> Embeddings:
		"""Return an Embeddings implementation based on the configured provider."""
		if self.provider == "huggingface":
			return self._build_huggingface_embeddings()
		if self.provider in {"azure_openai", "azure"}:
			return self._build_azure_embeddings()
		if self.provider in {"gemini", "google", "google_genai"}:
			return self._build_gemini_embeddings()
		raise ValueError(f"Unsupported provider for embeddings: {self.provider}")

	def build_llm(self) -> BaseChatModel:
		"""Return a chat LLM implementation based on the configured provider."""
		if self.provider == "huggingface":
			return self._build_huggingface_llm()
		if self.provider in {"azure_openai", "azure"}:
			return self._build_azure_llm()
		if self.provider in {"gemini", "google", "google_genai"}:
			return self._build_gemini_llm()
		raise ValueError(f"Unsupported provider for llm: {self.provider}")

	def _provider_config(self, *keys: str) -> Dict[str, Any]:
		for key in keys:
			value = self.config.get(key)
			if isinstance(value, Mapping):
				return dict(value)
		return {}

	def _read_secret(self, value: Optional[str], env_var: str) -> Optional[str]:
		return value or os.getenv(env_var)

	def _build_http_client(self, provider_cfg: Mapping[str, Any]) -> Optional[httpx.Client]:
		"""Build optional HTTP client for TLS/proxy customization.

		Supported provider-level keys:
		- ca_bundle_path: path to corporate/root CA bundle
		- ssl_no_verify: temporary diagnostic override (default false)
		
		Environment fallback:
		- REQUESTS_CA_BUNDLE
		- SSL_CERT_FILE
		"""
		ssl_no_verify = bool(provider_cfg.get("ssl_no_verify", False))
		ca_bundle_path = (
			provider_cfg.get("ca_bundle_path")
			or os.getenv("REQUESTS_CA_BUNDLE")
			or os.getenv("SSL_CERT_FILE")
		)

		if ssl_no_verify:
			return httpx.Client(verify=False, timeout=120.0)

		if ca_bundle_path:
			return httpx.Client(verify=ca_bundle_path, timeout=120.0)

		return None

	def _build_huggingface_embeddings(self) -> Embeddings:
		hf_cfg = self._provider_config("huggingface")
		emb_cfg = hf_cfg.get("embeddings", {})
		model_name = emb_cfg.get("model") or emb_cfg.get("model_name")
		if not model_name:
			raise ValueError("Hugging Face embeddings require 'huggingface.embeddings.model'.")

		return HuggingFaceEmbeddings(
			model_name=model_name,
			model_kwargs=emb_cfg.get("model_kwargs", {}),
			encode_kwargs=emb_cfg.get("encode_kwargs", {}),
		)

	def _build_huggingface_llm(self) -> BaseChatModel:
		hf_cfg = self._provider_config("huggingface")
		llm_cfg = hf_cfg.get("llm", {})

		repo_id = llm_cfg.get("repo_id") or llm_cfg.get("model")
		if not repo_id:
			raise ValueError("Hugging Face LLM requires 'huggingface.llm.repo_id'.")

		token = self._read_secret(
			llm_cfg.get("api_token"),
			llm_cfg.get("api_token_env", "HUGGINGFACEHUB_API_TOKEN"),
		)

		endpoint_kwargs = {
			"repo_id": repo_id,
			"task": llm_cfg.get("task", "text-generation"),
			"temperature": llm_cfg.get("temperature", 0),
			"max_new_tokens": llm_cfg.get("max_new_tokens", 512),
			"timeout": llm_cfg.get("timeout", 120),
		}
		if token:
			endpoint_kwargs["huggingfacehub_api_token"] = token

		endpoint = HuggingFaceEndpoint(**endpoint_kwargs)
		return ChatHuggingFace(llm=endpoint)

	def _build_azure_embeddings(self) -> Embeddings:
		azure_cfg = self._provider_config("azure_openai", "azure")
		emb_cfg = azure_cfg.get("embeddings", {})

		endpoint = self._read_secret(
			azure_cfg.get("endpoint"),
			azure_cfg.get("endpoint_env", "AZURE_OPENAI_ENDPOINT"),
		)
		api_key = self._read_secret(
			azure_cfg.get("api_key"),
			azure_cfg.get("api_key_env", "AZURE_OPENAI_API_KEY"),
		)
		api_version = azure_cfg.get("api_version", "2024-02-01")

		model = emb_cfg.get("model")
		deployment = emb_cfg.get("deployment_name")
		if not model and not deployment:
			raise ValueError(
				"Azure OpenAI embeddings require 'azure_openai.embeddings.model' "
				"or 'azure_openai.embeddings.deployment_name'."
			)

		kwargs: Dict[str, Any] = {
			"azure_endpoint": endpoint,
			"api_key": api_key,
			"api_version": api_version,
			"chunk_size": emb_cfg.get("chunk_size", 1000),
		}
		http_client = self._build_http_client(azure_cfg)
		if http_client is not None:
			kwargs["http_client"] = http_client
		if model:
			kwargs["model"] = model
		if deployment:
			kwargs["azure_deployment"] = deployment

		return AzureOpenAIEmbeddings(**kwargs)

	def _build_azure_llm(self) -> BaseChatModel:
		azure_cfg = self._provider_config("azure_openai", "azure")
		llm_cfg = azure_cfg.get("llm", {})

		endpoint = self._read_secret(
			azure_cfg.get("endpoint"),
			azure_cfg.get("endpoint_env", "AZURE_OPENAI_ENDPOINT"),
		)
		api_key = self._read_secret(
			azure_cfg.get("api_key"),
			azure_cfg.get("api_key_env", "AZURE_OPENAI_API_KEY"),
		)
		api_version = azure_cfg.get("api_version", "2024-02-01")

		model = llm_cfg.get("model")
		deployment = llm_cfg.get("deployment_name")
		if not model and not deployment:
			raise ValueError(
				"Azure OpenAI llm requires 'azure_openai.llm.model' "
				"or 'azure_openai.llm.deployment_name'."
			)

		kwargs: Dict[str, Any] = {
			"azure_endpoint": endpoint,
			"api_key": api_key,
			"api_version": api_version,
			"temperature": llm_cfg.get("temperature", 0),
		}
		http_client = self._build_http_client(azure_cfg)
		if http_client is not None:
			kwargs["http_client"] = http_client
		if model:
			kwargs["model"] = model
		if deployment:
			kwargs["azure_deployment"] = deployment

		return AzureChatOpenAI(**kwargs)

	def _build_gemini_embeddings(self) -> Embeddings:
		gemini_cfg = self._provider_config("gemini", "google", "google_genai")
		emb_cfg = gemini_cfg.get("embeddings", {})

		api_key = self._read_secret(
			gemini_cfg.get("api_key"),
			gemini_cfg.get("api_key_env", "GOOGLE_API_KEY"),
		)
		model = emb_cfg.get("model", "models/text-embedding-004")

		return GoogleGenerativeAIEmbeddings(
			model=model,
			google_api_key=api_key,
			task_type=emb_cfg.get("task_type"),
		)

	def _build_gemini_llm(self) -> BaseChatModel:
		gemini_cfg = self._provider_config("gemini", "google", "google_genai")
		llm_cfg = gemini_cfg.get("llm", {})

		api_key = self._read_secret(
			gemini_cfg.get("api_key"),
			gemini_cfg.get("api_key_env", "GOOGLE_API_KEY"),
		)

		return ChatGoogleGenerativeAI(
			model=llm_cfg.get("model", "gemini-1.5-flash"),
			google_api_key=api_key,
			temperature=llm_cfg.get("temperature", 0),
			max_output_tokens=llm_cfg.get("max_output_tokens"),
		)
