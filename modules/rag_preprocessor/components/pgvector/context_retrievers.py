from enum import Enum
import uuid
from typing import Any, List, Optional, Sequence, Tuple, Dict

from langchain_core.documents import Document
from langchain_text_splitters import TextSplitter
from langchain_core.callbacks import (
    AsyncCallbackManagerForRetrieverRun,
    CallbackManagerForRetrieverRun,
)
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.stores import BaseStore, ByteStore
from langchain_core.vectorstores import VectorStore
from pydantic import Field, model_validator

from langchain.storage._lc_store import create_kv_docstore

from components.pgvector.postgresdb import PostgresDB

class SearchType(str, Enum):
    """Enumerator of the types of search to perform."""

    similarity = "similarity"
    """Similarity search."""
    similarity_score_threshold = "similarity_score_threshold"
    """Similarity search with a score threshold."""
    mmr = "mmr"
    """Maximal Marginal Relevance reranking of similarity search."""


class PGVContextRetriever(BaseRetriever):
    """PGV Retriever for chunked documents with role-based search."""

    store_table: str = "parent_documents"
    pgv_database: PostgresDB = Field(default_factory=PostgresDB)
    vectorstore: VectorStore = Field(default_factory=VectorStore)
    search_type: SearchType = SearchType.similarity
    """The type of search to perform."""

    id_key: str = "doc_id"
    search_kwargs: dict = Field(default_factory=dict)
    """Keyword arguments to pass to the search function."""
    search_type: SearchType = SearchType.similarity
    """Type of search to perform (similarity / mmr)"""

    """
    @model_validator(mode="before")
    @classmethod
    def shim_docstore(cls, values: Dict) -> Any:
        byte_store = values.get("byte_store")
        docstore = values.get("docstore")
        if byte_store is not None:
            docstore = create_kv_docstore(byte_store)
        elif docstore is None:
            raise Exception("You must pass a `byte_store` parameter.")
        values["docstore"] = docstore
        return values
    """
    @model_validator(mode="after")
    def validate_search_type(self) -> "PGVContextRetriever":
        if self.search_type not in SearchType:
            raise ValueError(f"Invalid search type: {self.search_type}")
        return self
    

    child_splitter: Optional[TextSplitter] = None
    """The text splitter to use to create child documents."""

    """The key to use to track the parent id. This will be stored in the
    metadata of child documents."""
    parent_splitter: Optional[TextSplitter] = None
    """The text splitter to use to create parent documents.
    If none, then the parent documents will be the raw documents passed in."""

    child_metadata_fields: Optional[Sequence[str]] = None
    """Metadata fields to leave in child documents. If None, leave all parent document 
        metadata.
    """

    def _split_docs_for_context(
          self,
          documents: List[Document],
          ids: Optional[List[str]] = None,
          split_ids: bool = True
    ) -> Tuple[List[Document], List[Tuple[str, Document]], List[str]]:
        docs = [doc for doc in documents if isinstance(doc, Document)]
    
        if self.parent_splitter is not None:
            docs = self.parent_splitter.split_documents(documents)
        
        if ids is None:
            doc_ids = [str(uuid.uuid4()) for _ in docs]
        else:
            doc_ids = [i for i in ids if i is not None]
        if len(docs) != len(doc_ids):
            if split_ids:
                doc_ids = [str(uuid.uuid4()) for _ in docs]
            else:
                raise ValueError(
                    f"Length mismatch: {len(docs)} documents vs {len(ids)} ids. "
                    "If `ids` is provided, should be same length as `documents` after splitting."
                )
            
        # Assert all doc_ids are unique
        if len(set(doc_ids)) != len(doc_ids):
            # Retry with new UUIDs until all doc_ids are unique
            doc_ids = [str(uuid.uuid4()) for _ in docs]
            while len(set(doc_ids)) != len(doc_ids):
                doc_ids = [str(uuid.uuid4()) for _ in docs]
                if len(set(doc_ids)) == len(doc_ids):
                    break
            
        
        full_docs = []
        child_docs = []
        for i, doc in enumerate(docs):
            _id = doc_ids[i]
            sub_docs = self.child_splitter.split_documents([doc])
            if self.child_metadata_fields is not None:
                for _doc in sub_docs:
                    _doc.metadata = {
                        k: _doc.metadata[k] for k in self.child_metadata_fields
                    }
            for _doc in sub_docs:
                _doc.metadata[self.id_key] = _id
            child_docs.extend(sub_docs)
            full_docs.append((_id, doc))

        return child_docs, full_docs, doc_ids
    

    def add_documents(
        self,
        documents: List[Document],
        ids: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Adds documents to the docstore and vectorstores.

        Args:
            documents: List of documents to add
            ids: Optional list of ids for documents. If provided should be the same
                length as the list of documents. Can be provided if parent documents
                are already in the document store and you don't want to re-add
                to the docstore. If not provided, random UUIDs will be used as
                ids.
            add_to_docstore: Boolean of whether to add documents to docstore.
                This can be false if and only if `ids` are provided. You may want
                to set this to False if the documents are already in the docstore
                and you don't want to re-add them.
        """
        if kwargs.get("split_documents", False):
            documents, full_docs, ids = self._split_docs_for_context(
                documents=documents, ids=ids
            )
        else:
            if ids is None:
                # Check if ids are part of the document metadata
                if all(self.id_key in doc.metadata for doc in documents):
                    ids = [doc.metadata[self.id_key] for doc in documents]
                else:
                    # If no ids are provided, generate new UUIDs
                    ids = [str(uuid.uuid4()) for _ in documents]
            elif len(documents) != len(ids):
                raise ValueError(
                    "Got uneven list of documents and ids. "
                    "If `ids` is provided, should be same length as `documents`."
                )
            
            # Update the document metadata with the ids
            for i, doc in enumerate(documents):
                # Update the metadata with the id
                doc.metadata[self.id_key] = ids[i]
        
        # Add documents to the docstore
        self.vectorstore.add_documents(
            documents=documents,
            **kwargs,
        )


    async def aadd_documents(
        self,
        documents: List[Document],
        ids: Optional[List[str]] = None,
        add_to_docstore: bool = True,
        **kwargs: Any,
    ) -> None:
        """
        Asynchronously adds documents to the docstore and vectorstore.
        """
        if kwargs.get("split_documents", False):
            documents, full_docs, ids = self._split_docs_for_context(
                documents=documents, ids=ids
            )
        else:
            if ids is None:
                if all(self.id_key in doc.metadata for doc in documents):
                    ids = [doc.metadata[self.id_key] for doc in documents]
                else:
                    ids = [str(uuid.uuid4()) for _ in documents]
            elif len(documents) != len(ids):
                raise ValueError(
                    "Got uneven list of documents and ids. "
                    "If `ids` is provided, should be same length as `documents`."
                )
            for i, doc in enumerate(documents):
                doc.metadata[self.id_key] = ids[i]

        # Add documents to the docstore/vectorstore asynchronously
        if hasattr(self.vectorstore, "aadd_documents"):
            await self.vectorstore.aadd_documents(
                documents=documents,
                **kwargs,
            )
        else:
            # Fallback: run sync method in thread
            import asyncio
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: self.vectorstore.add_documents(documents=documents, **kwargs)
            )


    def _get_context(self, ids: list[str]) -> dict:
        """        Retrieve the parent context for the given ids from the database."""
        if len(ids) == 0:
            print("No keys provided for retrieval.")
            return []
        # Execute a query to get the values from the database
        query_get = f"""SELECT doc_id, id, document, cmetadata FROM {self.store_table} 
            WHERE doc_id IN ('{"', '".join(ids) }') 
            ORDER BY doc_id;"""
        self.pgv_database.connect()
        values = self.pgv_database.execute_query(query_get)
        self.pgv_database.disconnect()
        # Create Documents from the values
        # Assuming the values are returned in the same order as the keys
        if values:
            dict_doc_ids = {k[0]: [] for k in values}
            for k in values:
                if k[0] in dict_doc_ids.keys():
                    dict_doc_ids[k[0]].append(Document(page_content=k[2], metadata=k[3]))
        # Append the documents to the store
            docs = [Document(page_content=''.join([doc.page_content for doc in documents]),
                             metadata= documents[0].metadata) for doc_id, documents in dict_doc_ids.items()]
        else:
            print("No values found for the provided keys.")
            docs = []        

        return docs


    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        """Get documents relevant to a query.
        Args:
            query: String to find relevant documents for
            run_manager: The callbacks handler to use
        Returns:
            List of relevant documents
        """
        if self.search_type == SearchType.mmr:
            sub_docs = self.vectorstore.max_marginal_relevance_search(
                query, **self.search_kwargs
            )
        elif self.search_type == SearchType.similarity_score_threshold:
            sub_docs_and_similarities = (
                self.vectorstore.similarity_search_with_relevance_scores(
                    query, **self.search_kwargs
                )
            )
            sub_docs = [sub_doc for sub_doc, _ in sub_docs_and_similarities]
        else:
            sub_docs = self.vectorstore.similarity_search(query, **self.search_kwargs)

        # We do this to maintain the order of the ids that are returned
        ids = []
        for d in sub_docs:
            if self.id_key in d.metadata and d.metadata[self.id_key] not in ids:
                ids.append(d.metadata[self.id_key])
        # Override the previous store.mget based retrieval for a custom one that returns the parent context
        docs = self._get_context(ids=ids)
        return [d for d in docs if d is not None]

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: AsyncCallbackManagerForRetrieverRun
    ) -> List[Document]:
        """Asynchronously get documents relevant to a query.
        Args:
            query: String to find relevant documents for
            run_manager: The callbacks handler to use
        Returns:
            List of relevant documents
        """
        if self.search_type == SearchType.mmr:
            sub_docs = await self.vectorstore.amax_marginal_relevance_search(
                query, **self.search_kwargs
            )
        elif self.search_type == SearchType.similarity_score_threshold:
            sub_docs_and_similarities = (
                await self.vectorstore.asimilarity_search_with_relevance_scores(
                    query, **self.search_kwargs
                )
            )
            sub_docs = [sub_doc for sub_doc, _ in sub_docs_and_similarities]
        else:
            sub_docs = await self.vectorstore.asimilarity_search(
                query, **self.search_kwargs
            )

        # We do this to maintain the order of the ids that are returned
        ids = []
        for d in sub_docs:
            if self.id_key in d.metadata and d.metadata[self.id_key] not in ids:
                ids.append(d.metadata[self.id_key])
        # TODO Implementar metodo asíncrono de contexto
        docs = await self._get_context(ids=ids)
        return [d for d in docs if d is not None]
