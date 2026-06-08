from typing import List, Dict, Any
from abc import ABC, abstractmethod
from langchain_core.retrievers import BaseRetriever

# Definición de la clase abstracta para el almacenamiento de embeddings
class VectorStoreBase(ABC):
    @abstractmethod
    def connect(self) -> None:
        """Establece la conexión a la base de datos."""
        pass
    @abstractmethod
    def disconnect(self) -> None:
        """Cierra la conexión a la base de datos."""
        pass

    # Method to list all tables or indexes in the Vector Store
    @abstractmethod
    def get_info(self) -> List[Dict[str, Any]]:
        """Devuelve información sobre las tablas o índices en el Vector Store."""
        pass

    @abstractmethod
    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Ejecuta una consulta y devuelve los resultados."""
        pass

    @abstractmethod
    def store(self, data: List[Dict[str, Any]], index_name: str) -> None:
        """Añade embeddings a la base de datos."""
        pass

    """
    @abstractmethod
    def search(self, index_name: str, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        "Consulta los embeddings más cercanos al vector de consulta."
        pass
    """

    @abstractmethod
    def delete(self, index_name: str, query: str) -> None:
        """Elimina embeddings asociados a un proyecto específico."""
        pass
    
    @abstractmethod
    def get_retriever(self, index_name: str) -> BaseRetriever:
        """Devuelve un objeto de recuperación para el índice especificado."""
        raise NotImplementedError("Este método debe ser implementado en la subclase.")

    @abstractmethod
    def similarity_search(self, query: str, k: int = 4) -> List[Dict[str, Any]]:
        """Realiza una búsqueda de similitud en el vector store."""
        raise NotImplementedError("Este método debe ser implementado en la subclase.")
