"""
This is the main script where the docs preprocess is executed. These are the main functions this script does:

1. Read all the text documents divide into chunks and create embeddings.
2. Save the embeddings into a VectorStore file so that it can be used in an assistant.
"""

# Import packages
import logging
import argparse
from dotenv import load_dotenv
import os
import shutil
import yaml
import json
import uuid

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

from modules.preprocess import Preprocess
from components.docs_connectors.confluence_ingestor import ConfluenceIngestor
from components.docs_connectors.sharepoint_ingestor import SharePointIngestor
from utils.manage_sql_tables import read_sql_table
from utils.general_utils import expand_prompts_with_info

logging.basicConfig(level = logging.INFO)

def main():

    # Argument parser
    parser = argparse.ArgumentParser(description = 'RAG documentation ingestor')

    # This argument will be ./data/text if the execution is locally, and /data/text if the execution is in AKS.
    # There must be a volume in FileShare to store documents in that folder. The AKS must be connected with this volume.
    parser.add_argument('-i', '--id_project', type = str, help = 'The ID of the project.', default = 'c7a17eb2-a64a-4ce9-a4f9-081502a17121')
    parser.add_argument('-p', '--files_path', type = str, help = 'The files path to read documents. It can be a whole folder or a single file.', default = './data/text')
    parser.add_argument('-e', '--external_ingestion', type = str, help = 'True if download files from external sources.', default = 'False')

    args = parser.parse_args()

    id_project = str(uuid.UUID(args.id_project))
    files_path = args.files_path
    external_ingestion = args.external_ingestion == 'True'

    load_dotenv()

    key_vault_url = os.getenv('KEYVAULT_URL')

    credential = DefaultAzureCredential()

    # Cliente para acceder al Key Vault
    client = SecretClient(vault_url = key_vault_url, credential = credential)

    # Read the environment variables
    PGHOST = os.getenv('PGHOST')
    PGUSER = os.getenv('PGUSER')
    PGPORT = os.getenv('PGPORT')
    PGDATABASE = os.getenv('PGDATABASE')
    PGPASSWORD = os.getenv('PGPASSWORD')

    # Ingestion config
    result_ingestion_config = read_sql_table(
        table="public.intelectia_projects",
        fields=[
            "public.intelectia_projects.project_uuid",
            "public.intelectia_config.config_json"
        ],
        joins=[
            {
                "type": "INNER JOIN",
                "table": "public.intelectia_config",
                "on": "public.intelectia_projects.config_uuid = public.intelectia_config.config_uuid"
            }
        ],
        where={
            "public.intelectia_projects.project_uuid": id_project
        },
        db_config={
            "host": PGHOST,
            "database": PGDATABASE,
            "user": PGUSER,
            "password": PGPASSWORD,
            "port": PGPORT
        }
    )

    json_config = result_ingestion_config[0]["config_json"]

    pg_collection_table_name = json_config['store']['config']['collection']
    pg_embeddings_table_name = json_config['store']['config']['embeddings']
    sslmode = json_config['store']['config']['sslmode']

    AZURE_OPENAI_API_KEY = os.getenv('AZURE_OPENAI_API_KEY')
    OPENAI_API_VERSION = json_config['models']['api_version']
    AZURE_OPENAI_ENDPOINT = json_config['models']['endpoint']
    # TODO: ponerlo con el model_manager
    AZURE_DEPLOYMENT_LLM_MODEL = json_config['models']['llms'][0]['model_name']
    AZURE_DEPLOYMENT_EMB_MODEL = json_config['models']['embeddings'][0]['model_name']

    project_name = json_config['project_name']

    id_prompts = json_config['ingestion']['prompts']
    id_prompts_list = list(id_prompts.values())
    id_prompts_list = [str(uuid.UUID(id)) for id in id_prompts_list if id is not None]
    
    retrieved_prompts = read_sql_table(
        table="public.prompts",
        fields=[
            "public.prompts.prompt_uuid",
            "public.prompts.text",
            "public.prompts.variables"
        ],
        where={
            "public.prompts.prompt_uuid": id_prompts_list
        },
        db_config={
            "host": PGHOST,
            "database": PGDATABASE,
            "user": PGUSER,
            "password": PGPASSWORD,
            "port": PGPORT
        }
    )
    
    prompts = expand_prompts_with_info(id_prompts, retrieved_prompts)
    
    # Create files folder if it does not exist
    if not os.path.exists(files_path):
        logging.error(f'Folder {files_path} does not exist. The folder will be created and you have to fill it with documents...')
        os.makedirs(files_path)
    
    
    # There are different paths depending on the chunk sizes
    parent_chunk_size = json_config['ingestion']['chunking_params']['parent_chunk_size']
    child_chunk_size = json_config['ingestion']['chunking_params']['child_chunk_size']
    chunk_overlap = int(round(0.1 * child_chunk_size))

    # Create folder for monitoring results
    output_check_path = json_config['ingestion']['paths']['output_check_path']
    if not os.path.exists(output_check_path):
        os.makedirs(output_check_path)

    # Config the path the images will be extracted to
    images_path = json_config['ingestion']['paths']['images_path']

    if external_ingestion:
        urls_dict = {}
        for s in json_config['ingestion']['sources']:
            if s['source_type'] == 'SharePoint':
                urls_dict[s['source_name']] = s['source_config']['url']
                
                # Leer secreto por nombre
                tenant_id = client.get_secret(s['tenant_id']).value
                client_id = client.get_secret(s['source_config']['client_id']).value
                client_secret = client.get_secret(s['source_config']['client_secret']).value

                sharepoint_ingestor = SharePointIngestor(
                    sharepoint_url=s['source_config']['url'],
                    client_id=client_id,
                    client_secret=client_secret,
                    tenant_id=tenant_id,
                    site_domain=s['site_domain'],
                    site_path=s['source_config']['root'],
                    scope=s['scope'],
                    cliente = s['client'],
                    librerias_ignorar = s['source_config']['library_ignore'],
                    carpetas_ignorar = s['source_config']['folder_ignore'],
                    to_azure_blob=False,
                    download_folder_name = f"{files_path}/{s['source_name']}"
                )
                    
                _ = sharepoint_ingestor.listar_bibliotecas()

                _ = sharepoint_ingestor.listar_ingestar(file_extensions = s['extensions'])
            
            elif s['source_type'] == 'Confluence':
                urls_dict[s['source_name']] = s['source_config']['url']

                # Initialize the ConfluenceProcessor
                confluence_ingestor = ConfluenceIngestor(
                    confluence_url = s['source_config']['url'],
                    user = s['source_config']['client_user'],
                    password = s['source_config']['client_password'],  # Password is not used when token is provided
                    token = s['source_config']['client_secret'],
                    blob_connection_string = None,
                    blob_container_name = None,
                    to_azure_blob = False
                )

                # Download the content
                _ = confluence_ingestor.download(output_base_path = files_path,
                                                subfolder = s['source_name'],
                                                extraction_type = s['extension'],
                                                include_space_keys = s['source_config']['include_space_keys'],
                                                exclude_space_keys = s['source_config']['exclude_space_keys'],
                                                include_page_ids = s['source_config']['include_page_ids'],
                                                exclude_page_ids = s['source_config']['exclude_page_ids'])
                
    else:
        urls_dict = None

    roles_list = json_config['ingestion']['roles_assignment']

    logging.info(f'Roles list: {roles_list}')

    ## Preprocess text documents
    preprocessor = Preprocess(azure_endpoint = AZURE_OPENAI_ENDPOINT,
                              deployment_name = AZURE_DEPLOYMENT_LLM_MODEL,
                              openai_api_version = OPENAI_API_VERSION,
                              embedding_model = AZURE_DEPLOYMENT_EMB_MODEL,
                              temperature = json_config['ingestion']['chunking_params']['model_temperature'],
                              system_prompt_describe_images_docx = prompts['id_prompt_describe_images_docx'],
                              system_prompt_describe_images_ppt = prompts['id_prompt_describe_images_ppt'],
                              system_prompt_create_summaries = prompts['id_prompt_create_summaries'],
                              output_check_path = output_check_path,
                              images_path = images_path,
                              id_project = id_project,
                              roles_list = roles_list,
                              urls_dict = urls_dict
                              )

    # Create the unique text variable with all the docs together
    by_sections = json_config['ingestion']['chunking_params']['by_sections']
    ppt_by_images = json_config['ingestion']['chunking_params']['ppt_by_images']
    docs = preprocessor.create_docs_from_files(files_path,
                                               by_sections = by_sections,
                                               regexp_section = json_config['ingestion']['chunking_params']['regexp_section'],
                                               ppt_by_images = ppt_by_images)

    # Create the embeddings for each chunk
    logging.info(f'Create the embeddings and saving them...')
    preprocessor.create_embeddings(
        docs,
        parent_chunk_size = parent_chunk_size,
        child_chunk_size = child_chunk_size,
        chunk_overlap = chunk_overlap,
        pg_host = PGHOST,
        pg_dbname = PGDATABASE,
        pg_user = PGUSER,
        pg_password = PGPASSWORD,
        pg_port = PGPORT,
        pg_collection_table_name = pg_collection_table_name,
        pg_embeddings_table_name = pg_embeddings_table_name,
        sslmode = sslmode,
        pg_collection_name = project_name,
        collection_uuid = id_project
    )
    
    logging.info(f'Embeddings saved...')

if __name__ == '__main__':
    main()