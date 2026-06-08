import psycopg2
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from typing import List, Dict, Any
import uuid

# Importing the PostgresDB class to manage database connections
from .VSBase import VectorStoreBase
from .postgresdb import PostgresDB
from .CustomPGVectorStore import CustomPGVector


class PGVectorStore(VectorStoreBase):

    def __init__(self, 
                 host: str,
                 dbname: str,
                 user: str,
                 password: str,
                 sslmode: str,
                 port: int,
                 embeddings: Embeddings,
                 collection_name: str = "proyecto002",
                 collection_table: str = "project_collection",
                 embeddings_table: str = "project_embeddings",
                 collection_uuid: uuid = '34342-34234-234234'):
        self.pgdb = PostgresDB(host=host, dbname=dbname, user=user, 
                               password=password, sslmode=sslmode, port=port)
        try:
            self.pgdb.connect()
        except Exception as e:
            print("Error de conexión:", e)
        # Initialize the CustomPGVector instance
        self.pgvs = CustomPGVector(
            embeddings=embeddings,
            collection_name=collection_name,
            connection=self.pgdb.get_connection_string(),
            collection_table=collection_table,
            embeddings_table=embeddings_table,
            use_jsonb=True
        )
    def connect(self):
        try:
            self.pgdb.connect()
        except Exception as e:
            print("Error de conexión:", e)

    def get_connection_string(self) -> str:
        return self.pgdb.get_connection_string()

    def disconnect(self):
        self.pgdb.disconnect()

    def get_info(self):
        try:
            tables = self.pgdb.execute_query("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
            info = [{"table_name": table[0]} for table in tables]
            return info
        except Exception as e:
            print("Error al obtener información de las tablas:", e)
            return []
        
    def execute_query(self, query: str):
        try:
            return self.pgdb.execute_query(query)
        except Exception as e:
            print("Error al ejecutar la consulta:", e)
            return []
    
    def store(self, data: List[Dict[str, Any]], table_name: str = None) -> None:
        try:
            # check if data is a list of documents
            is_documents = isinstance(data, list) and all(isinstance(doc, Document) for doc in data)
            if is_documents:
                self.pgvs.add_documents(data)
            else:
                if not table_name:
                    raise ValueError("El nombre de la tabla es obligatorio si los datos no son documentos.")
                self.pgdb.store(data=data, 
                                table_name=table_name)
        except psycopg2.Error as e:
            print("Error al almacenar los datos:", e)
        except ValueError as ve:
            print("Error de validación:", ve)
        except Exception as e:
            print("Error inesperado al almacenar los datos:", e)
        finally:
            self.pgdb.disconnect()


    def delete(self, table_name: str = None, ids: List[int] = None, query: str = None) -> None:
        """Elimina embeddings asociados a un proyecto específico."""
        try:
            # Si se proporcionan IDs, eliminarlos
            if ids: # Elimina los IDs específicos (embeddings, por lo general)
                self.pgvs.delete(ids=ids, collection_only=True)
            elif query:  # Si se proporciona una consulta, eliminar según la consulta
                self.pgdb.delete(table_name=table_name, condition=query)

        except Exception as e:
            print("Error al eliminar los registros:", e)

    def get_retriever(self, search_kwargs: Dict[str, Any]) -> BaseRetriever:
        return self.pgvs.as_retriever(search_kwargs=search_kwargs)
    
    def similarity_search(self, query: str, k: int = 4) -> List[Document]:
        """Realiza una búsqueda de similitud en el vector store."""
        try:
            return self.pgvs.similarity_search(query=query, k=k)
        except Exception as e:
            print("Error al realizar la búsqueda de similitud:", e)
            return []