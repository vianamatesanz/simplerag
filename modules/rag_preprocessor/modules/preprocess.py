"""
This is the main class to preprocess text and create the Emeddings.
"""

# Import libraries
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import AzureOpenAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders import TextLoader
from langchain_community.document_loaders import UnstructuredPowerPointLoader
from langchain_core.documents import Document

from langchain_openai import AzureChatOpenAI

import time
import os
import logging
import fitz
from tqdm import tqdm
from datetime import datetime
import tiktoken
from openai import InternalServerError

from components.preprocessors.docx_preprocess import DocxProcessor
from components.preprocessors.pptx_preprocess import PptxProcessor
from components.preprocessors.pdf_preprocess import PDFProcessor
from components.pgvector.VSPostgre import PGVectorStore
from components.pgvector.pg_utils import add_collection

from components.pgvector.context_retrievers import PGVContextRetriever

logging.basicConfig(level = logging.INFO)

class Preprocess:
    '''
    Preprocess class.
    '''

    def __init__(self, azure_endpoint,
                       deployment_name,
                       openai_api_version,
                       embedding_model,
                       temperature,
                       output_check_path,
                       images_path,
                       id_project,
                       roles_list,
                       urls_dict,
                       system_prompt_describe_images_docx = None,
                       system_prompt_describe_images_ppt = None,
                       system_prompt_create_summaries = None):
        '''
        Init function.

        :param azure_endpoint: The Azure endpoint.
        :type azure_endpoint: string
        :param deployment_name: The deployment model name.
        :type deployment_name: string
        :param openai_api_version: The version of the OpenAI model.
        :type openai_api_version: string
        :param embedding_model: The embedding model to use.
        :type embedding_model: string
        :param temperature: The temperature of the model.
        :type temperature: int
        :param system_prompt_describe_images_docx: The prompt for describing images.
        :type system_prompt_describe_images_docx: string
        :param system_prompt_describe_images_ppt: The prompt for describing slides of a ppt.
        :type system_prompt_describe_images_ppt: string
        :param system_prompt_create_summaries: The prompt to create summaries from slides ppt.
        :type system_prompt_create_summaries: string.
        :param output_check_path: Output path to check results.
        :type output_check_path: string
        :param images_path: Output path to save images.
        :type images_path: string
        '''
        
        self.azure_endpoint = azure_endpoint
        self.deployment_name = deployment_name
        self.openai_api_version = openai_api_version
        self.embedding_model = embedding_model
        self.temperature = temperature
        self.system_prompt_describe_images_docx = system_prompt_describe_images_docx
        self.system_prompt_describe_images_ppt = system_prompt_describe_images_ppt
        self.system_prompt_create_summaries = system_prompt_create_summaries
        self.output_check_path = output_check_path
        self.images_path = images_path
        self.id_project = id_project
        self.roles_list = roles_list
        self.urls_dict = urls_dict

        self.llm_images = AzureChatOpenAI(
                azure_endpoint = self.azure_endpoint,
                deployment_name = self.deployment_name,
                model = self.deployment_name,
                openai_api_version = self.openai_api_version,
                temperature = self.temperature,
            )
        
        # Parameters to trace the langchain flow
        os.environ['LANGCHAIN_TRACING_V2'] = 'true'
        os.environ['LANGCHAIN_API_KEY'] = os.getenv('LANGCHAIN_API_KEY')

    def detect_role_from_path(self, document_path, roles_list):
        """
        Detects the role associated with a document based on the folder path,
        regardless of how deep the folder is nested in the path.
        """
        # Normalize and split the path into parts
        path_parts = document_path.replace("\\", "/").split("/")

        matching_roles = []

        for role, folders in roles_list.items():
            if not isinstance(folders, list):
                folders = [folders]
            if any(folder in path_parts for folder in folders):
                matching_roles.append(role)

        return matching_roles

    def get_root_folder_name(self, document_path, base_path="./data/text/"):
        """
        Returns the folder name that appears immediately after the base path.

        :param document_path: Full path to the document file.
        :type document_path: str
        :param base_path: The base path to remove from the document path.
        :type base_path: str
        :return: Name of the folder immediately after the base path.
        :rtype: str or None
        """

        path_parts = document_path.replace("\\", "/").split("/")
        base_parts = base_path.strip("/").split("/")

        for i in range(len(path_parts) - len(base_parts)):
            if path_parts[i:i+len(base_parts)] == base_parts:
                return path_parts[i + len(base_parts)]

        return None
    
    def add_metadata(self, tmp_docs, metadata):

        for doc_aux in tmp_docs:
            for metadata_name, metadata_value in metadata.items():
                doc_aux.metadata[metadata_name] = metadata_value

        return tmp_docs

    def create_docs_from_files(self, path, by_sections = False, regexp_section = None, ppt_by_images = False):
        '''
        Function to create the text object from the text files.

        :param path: The path where the text files are located.
        :type path: string
        :param by_sections: True if document must be chunked by sections.
        :type by_sections: boolean
        :param regexp_section: Regexp to apply in order to delete parts or detect section patterns.
        :type regext_section: dict
        :param ppt_by_images: True if every PPT slide must be processed as an image.
        :type ppt_by_images: boolean
        '''

        # Create a file to save all the documents that have been introduced in the model
        files_model_path = os.path.join(path, 'files_model.txt')
        if os.path.exists(files_model_path):
            os.remove(files_model_path)

        # Save the files paths depending on if it is already a file or a folder
        if os.path.isfile(path):
            file_path_list = [path]  
        elif os.path.isdir(path):
            file_path_list = []
            for root, dirs, files in os.walk(path):
                for file in files:
                    file_path_list.append(os.path.join(root, file))

        # Create the docs object
        files_model_list = []
        docs = []
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Param to monitorize chunking with txt files
        monitorize = True
        for f in tqdm(file_path_list):
            save_docs = True
            logging.info(f'Extracting text from {f}')
            id_roles = self.detect_role_from_path(f, self.roles_list)
            root_folder_name = self.get_root_folder_name(f, base_path = path)
            if self.urls_dict:
                base_url = self.urls_dict[root_folder_name]
            else:
                base_url = 'https://url_example.com'
            # PDF files
            if f.endswith('.pdf'):
                # If chunking by sections, then apply corresponding functions
                id_sibling = 0
                if by_sections:
                    pdf_processor = PDFProcessor(f,
                                                self.output_check_path,
                                                now,
                                                monitorize)

                    # Extract the sections with their metadata
                    sections_with_info = pdf_processor.extract_sections_from_pdf(regexp_section)
                    
                    # Add sections info to docs variable
                    tmp_docs = []
                    
                    for s in sections_with_info:
                        try:
                            pages = list(s['pages'])[0]
                        except IndexError as e:
                            logging.warning(f'This section page will not be the actual page. Please verify this file. Error:\n{e}')

                        tmp_docs.append(Document(page_content = s['content'], metadata = {'page': pages,
                                                                                        'section_name': s['section_name'],
                                                                                        'id_sibling': id_sibling}))

                        id_sibling += 1
                
                # If normal chunking, get only de text
                else:
                    loader = PyPDFLoader(f)
                    tmp_docs = loader.load()
                    pdf_fitz = fitz.open(f)
                    for i, _ in enumerate(tmp_docs):
                        tmp_docs[i].page_content = pdf_fitz[i].get_text()
                        tmp_docs[i].metadata['id_sibling'] = id_sibling
                        id_sibling += 1

            # Txt files
            elif f.endswith('.txt'):
                logging.info(f)
                loader = TextLoader(f, encoding = 'utf-8')
                tmp_docs = loader.load()

                id_sibling = 0
                for doc_aux in tmp_docs:
                    doc_aux.metadata['doc_type'] = 'txt'
                    doc_aux.metadata['id_sibling'] = id_sibling
                    id_sibling += 1

            # Docx files
            elif f.endswith('.docx') or f.endswith('.doc'):
                # If conversion to docx is necessary, the docx must be deleted after conversion
                delete_file = False
                # If it is 'doc', convert it to docx
                if f.endswith('.doc'):
                    f = DocxProcessor(f).doc2docx()
                    delete_file = True
                    time.sleep(5)
                docx_processor = DocxProcessor(f,
                                            self.llm_images,
                                            system_prompt_describe_images = self.system_prompt_describe_images_docx,
                                            persist_files = True,
                                            images_path = self.images_path,
                                            output_check_path = self.output_check_path,
                                            now = now,
                                            monitorize = monitorize)
                docx_processor.process_document()
                tmp_docs = docx_processor.to_langchain_documents()
                
                # Delete docx file
                if delete_file:
                    os.remove(f)

            # Pptx files
            elif f.endswith('.pptx'):
                # It is posible to read PPT as images and as plain text
                if ppt_by_images:
                    pptx_processor = PptxProcessor(f,
                                                self.llm_images,
                                                system_prompt_describe_images = self.system_prompt_describe_images_ppt,
                                                system_prompt_create_summaries = self.system_prompt_create_summaries,
                                                persist_files = True,
                                                images_path = self.images_path)
                    pptx_processor.process_presentation()
                    tmp_docs = pptx_processor.to_langchain_documents()

                else:
                    loader = UnstructuredPowerPointLoader(f, mode = 'paged')

                    tmp_docs = loader.load()

                for doc_aux in tmp_docs:
                    if 'languages' in doc_aux.metadata:
                        del doc_aux.metadata['languages']
                
                # Generate monitoring file if enabled
                if monitorize:
                    sep = '\n' + '#' * 100 + '\n'
                    with open(f'{self.output_check_path}/monitoring_chunking_{now}.txt', 'a', encoding = 'utf-8') as file:
                        file.write(f'FILENAME: {os.path.basename(f)}\n\n')
                        for doc_aux in tmp_docs:
                            title = doc_aux.metadata['page_number']
                            content = doc_aux.page_content

                            file.write(f'SLIDE: {title}\n')
                            file.write(f'CONTENT: {content}\n')
                            file.write(sep)

            else:
                logging.info('This file has not any admitted format.')
                save_docs = False

            new_metadata = {'source': f,
                            'doc_type': os.path.splitext(f)[1][1:],
                            'role_list': id_roles,
                            'url': f"{base_url}/{f.replace(path, '')}"}
            
            tmp_docs = self.add_metadata(tmp_docs, new_metadata)

            if save_docs:
                # Append docs to the list
                files_model_list.append(f)
                docs.extend(tmp_docs)
        
        # Save the file_path_list into a txt file to know
        # the data that has been used in the model
        with open(files_model_path, 'w', encoding = "utf-8") as file:
            for file_path_aux in files_model_list:
                file.write(f'{file_path_aux}\n')

        # Tokenizer to calculate tokens
        tokenizer = tiktoken.encoding_for_model(self.deployment_name)
        # Remove base path string from source
        for doc in docs:
            source = doc.metadata['source'].replace(path, '')
            doc.metadata['source'] = source
            doc.page_content += f'\nFont: {source}'
            # TODO: Add extra metadata
            doc.metadata['id_project'] = self.id_project
            doc.metadata['tokens'] = len(tokenizer.encode(doc.page_content))

        return docs
    
    def create_embeddings(self,
                          docs,
                          parent_chunk_size,
                          child_chunk_size,
                          chunk_overlap,
                          pg_host,
                          pg_dbname,
                          pg_user,
                          pg_password,
                          pg_port,
                          pg_collection_table_name,
                          pg_embeddings_table_name,
                          sslmode,
                          pg_collection_name,
                          collection_uuid
                          ):
        '''
        Function to create the embeddings for each text chunk.

        :param docs: The documents splits loaded from the raw documentation.
        :type docs: list
        :param child_docs_path: The path where to save child texts.
        :type child_docs_path: string
        :param persist_directory_path: The path where to save Chroma data.
        :type persist_directory_path: string
        :param parent_chunk_size: The chunk size for the parent documents.
        :type parent_chunk_size: int
        :param child_chunk_size: The chunk size for the child documents.
        :type child_chunk_size: int
        :param chunk_overlap: The overlap between chunks.
        :type chunk_overlap: integer
        '''
        
        # Init embedding model
        embeddings = AzureOpenAIEmbeddings(
            azure_endpoint=self.azure_endpoint,
            api_version=self.openai_api_version,
            model=self.embedding_model
        )

        child_splitter = RecursiveCharacterTextSplitter(chunk_size = child_chunk_size)
        parent_splitter = RecursiveCharacterTextSplitter(chunk_size = parent_chunk_size)

        pgv = PGVectorStore(
            host=pg_host,
            dbname=pg_dbname,
            user=pg_user,
            password=pg_password,
            sslmode=sslmode,
            port=pg_port,
            embeddings=embeddings,  # Aquí deberías pasar tu objeto de embeddings
            collection_name=pg_collection_name,
            collection_uuid = collection_uuid,
            collection_table=pg_collection_table_name,
            embeddings_table=pg_embeddings_table_name
        )

        pgvretriever = PGVContextRetriever(
            store_table=pg_embeddings_table_name, # 
            pgv_database= pgv.pgdb,
            vectorstore=pgv.pgvs, # Aquí deberías pasar tu objeto de vector store
            child_splitter=child_splitter,
            parent_splitter=parent_splitter,
            search_kwargs = {}  # Ajusta los parámetros según tus necesidades
        )

        connection_string = (
            f"host={pg_host} "
            f"port={pg_port} "
            f"dbname={pg_dbname} "
            f"user={pg_user} "
            f"password={pg_password} "
            f"sslmode={sslmode}"
        )

        add_collection(connection_string = connection_string,
                       table_name = pg_collection_table_name,
                       collection_name = pg_collection_name,
                       collection_uuid = collection_uuid)

        # while True:
        #     try:

        pgvretriever.add_documents(
            documents=docs,
            add_to_docstore=False,
            split_documents=True
        )
                # break
            # except InternalServerError as e:
            #     logging.info(e)
            #     time.sleep(20)
            

        return None