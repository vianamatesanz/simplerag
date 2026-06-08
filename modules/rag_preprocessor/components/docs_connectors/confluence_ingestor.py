# Import libraries
import os
import requests
import pandas as pd
from bs4 import BeautifulSoup
from requests.auth import HTTPBasicAuth
import logging
import shutil

class ConfluenceIngestor:
    '''
    Confluence documentation downloader.
    '''

    def __init__(self, confluence_url=None, user=None, password=None, token=None, blob_connection_string=None, blob_container_name=None, to_azure_blob = False):#, page_ids_ignore=None, space_keys_ignore=None):
        """
        Inicializa el procesador de Confluence.
        """
        self.base_url = confluence_url
        self.user = user
        self.password = password
        self.token = token
        self.blob_connection_string = blob_connection_string
        self.blob_container_name = blob_container_name
        self.to_azure_blob = to_azure_blob

        if self.token:
            self.auth = None  # No usar auth de requests
            self._use_token = True
        elif self.user and self.password:
            self.auth = HTTPBasicAuth(self.user, self.password)
            self._use_token = False
        else:
            raise ValueError('Debes proporcionar usuario+clave o token (PAT)')
        

    def get_headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        else:
            return {"Accept": "application/json"}
        
    
    def get_confluence_spaces(self, base_url=None, start=0, limit=50):
        """
        Recupera todos los espacios de Confluence disponibles, con paginación.

        :param base_url: URL base de la instancia Confluence. Si no se da, se usa el de la clase.
        :param start: Índice inicial para paginación.
        :param limit: Número de resultados por página (máx 1000 en algunas instancias).
        :return: Lista de espacios (cada uno es un dict).
        """
        if base_url is None:
            base_url = self.base_url

        spaces = []
        while True:
            url = f"{base_url}/rest/api/space?limit={limit}&start={start}"
            print(f"Fetching spaces from {start} to {start + limit}")
            response = requests.get(url, headers=self.get_headers(), auth=self.auth)

            if response.status_code != 200:
                raise RuntimeError(f"Error al recuperar espacios: {response.status_code} - {response.text}")

            data = response.json()
            batch = data.get("results", [])
            if not batch:
                break

            spaces.extend(batch)
            start += limit

        return spaces
        

    def resolve_pages_to_download(self, include_space_keys=None, exclude_space_keys=None, include_page_ids=None, exclude_page_ids=None):
        """
        Determina qué páginas deben descargarse, según filtros de inclusión/exclusión.

        :param include_space_keys: List of space keys to include in the download.
        :type include_space_keys: list[str]
        :param exclude_space_keys: List of space keys to exclude from the download.
        :type exclude_space_keys: list[str]
        :param include_page_ids: List of specific page IDs to include in the download.
        :type include_page_ids: list[str]
        :param exclude_page_ids: List of specific page IDs to exclude from the download.
        :type exclude_page_ids: list[str]
        """
        final_page_ids = set()

        if include_page_ids:
            final_page_ids.update(include_page_ids)

        elif include_space_keys:
            for space_key in include_space_keys:
                page_ids = self.get_page_ids_in_space(self.base_url, space_key)
                final_page_ids.update(page_ids)

        else:
            # Obtener todos los espacios
            all_spaces = self.get_confluence_spaces(self.base_url)
            for space in all_spaces:
                key = space["key"]
                if exclude_space_keys and key in exclude_space_keys:
                    continue
                page_ids = self.get_page_ids_in_space(self.base_url, key)
                final_page_ids.update(page_ids)

        # Excluir páginas si se solicita
        if exclude_page_ids:
            final_page_ids.difference_update(exclude_page_ids)

        return list(final_page_ids)
    


    def get_page_ids_in_space(self, base_url, space_key, start=0, limit=50):
        base_url = base_url.rstrip("/")
        page_ids = []
        while True:
            url = f"{base_url}/rest/api/content?spaceKey={space_key}&type=page&limit={limit}&start={start}"
            print(f"Buscando páginas en el espacio '{space_key}', desde {start}")
            r = requests.get(url, headers=self.get_headers(), auth=self.auth)
            r.raise_for_status()
            data = r.json()
            pages = data.get("results", [])
            if not pages:
                break
            ids = [page["id"] for page in pages]
            page_ids.extend(ids)
            start += limit
        print(f"🔎 Total de páginas encontradas en '{space_key}': {len(page_ids)}")
        return page_ids
    

    def get_space_to_page_ids_map(self, include_space_keys=None, exclude_space_keys=None):
        """
        Devuelve un diccionario con la forma {space_key: [page_id1, page_id2, ...]}.
        Aplica filtros de inclusión/exclusión de espacios.

        :param include_space_keys: Lista de espacios a incluir (opcional).
        :param exclude_space_keys: Lista de espacios a excluir (opcional).
        :return: Diccionario con espacio -> lista de page_ids.
        """
        space_page_map = {}
        all_spaces = self.get_confluence_spaces(self.base_url)

        for space in all_spaces:
            key = space["key"]

            # Aplica lógica de filtros
            if include_space_keys and key not in include_space_keys:
                continue
            if exclude_space_keys and key in exclude_space_keys:
                continue

            # Obtener páginas del espacio
            page_ids = self.get_page_ids_in_space(self.base_url, key)
            space_page_map[key] = page_ids

        return space_page_map

    def download(self,
             output_base_path,
             subfolder = 'confluence_docs',
             extraction_type = 'pdf',
             include_space_keys=None,
             exclude_space_keys=None,
             include_page_ids=None,
             exclude_page_ids=None):
        
        '''
        Download Confluence content: either specific pages or all pages from a space.

        :param output_base_path: Base folder where documents will be saved.
        :type output_base_path: string
        :param subfolder: Subfolder to store the downloaded files.
        :type subfolder: string
        :param extraction_type: 'txt' or 'pdf'.
        :type extraction_type: string
        :param space_key: Key of the Confluence space (e.g., 'WKPLAIG').
        :type space_key: string
        :param page_ids: List of specific page IDs to download.
        :type page_ids: list[str]
        :param include_space_keys: List of space keys to include in the download.
        :type include_space_keys: list[str]
        :param exclude_space_keys: List of space keys to exclude from the download.
        :type exclude_space_keys: list[str]
        :param include_page_ids: List of specific page IDs to include in the download.
        :type include_page_ids: list[str]
        :param exclude_page_ids: List of specific page IDs to exclude from the download.
        :type exclude_page_ids: list[str]
        '''

        df_ingestion = pd.DataFrame(
            columns=['filename', 'directory', 'state_ingested', 'failure_reason']
        )

        print(f"include_space_keys: {include_space_keys}")

        # for space_key in include_space_keys or []:
        #     list_temp = self.get_page_ids_in_space(self.base_url, space_key)
        #     logging.info(f"id per space: {list_temp}")

        
        page_ids = self.resolve_pages_to_download(
            include_space_keys=include_space_keys,
            exclude_space_keys=exclude_space_keys,
            include_page_ids=include_page_ids,
            exclude_page_ids=exclude_page_ids
        )

        if not page_ids:
            logging.warning("No hay páginas para descargar.")
            return

        output_folder = os.path.join(output_base_path, subfolder)
        if os.path.exists(output_folder):
            shutil.rmtree(output_folder, ignore_errors = True)
        
        os.makedirs(output_folder, exist_ok = True)


        logging.info(f"Descargando {len(page_ids)} páginas...")

        for page_id in page_ids:
            if extraction_type == 'pdf':
                self._download_pdf(page_id, f'page_{page_id}',df_ingestion, output_folder)
            elif extraction_type == 'txt':
                url = f'{self.base_url}/rest/api/content/{page_id}?expand=body.storage'
                response = requests.get(url, headers=self.get_headers(), auth=self.auth)
                if response.status_code == 200:
                    page = response.json()
                    title = page['title'].replace(' ', '_').replace('/', '_')
                    self._download_txt(page, title, page_id, df_ingestion, output_folder)
                else:
                    logging.error(f'[ERROR] Page {page_id}: {response.status_code} - {response.text}')

        return df_ingestion
   
    def _download_txt(self, page: dict, title, page_id, df_ingestion, output_folder):
        """
        Download a Confluence document in plain text format.

        :param page: The Confluence page data containing the HTML content.
        :type page: dict
        :param title: The title of the Confluence page.
        :type title: string
        :param page_id: The ID of the Confluence page.
        :type page_id: string
        :param output_folder: The folder where the text file will be saved.
        :type output_folder: string
        """

        try:
            # Extraer contenido HTML y convertirlo a texto plano
            html_content = page['body']['storage']['value']
            text_content = BeautifulSoup(html_content, 'html.parser').get_text()

            # Normalizar el nombre del archivo
            filename = f'{title}_{page_id}.txt'.replace(" ", "_")
            blob_path = f"confluence_exports/{filename}"
            local_save_path = os.path.join(output_folder, blob_path.replace("/", os.sep))

            # Comprobar si ya existe
            ya_existe = False
            if self.to_azure_blob:
                blob_client = self.container_client.get_blob_client(blob_path)
                ya_existe = blob_client.exists()
            else:
                ya_existe = os.path.exists(local_save_path)

            if not ya_existe:
                if self.to_azure_blob:
                    blob_client.upload_blob(text_content.encode("utf-8"))
                    logging.info(f"[UPLOAD] TXT subido a Azure Blob: {blob_path}")
                    print(f"[UPLOAD] Subido: {blob_path}")
                    df_ingestion.loc[len(df_ingestion)] = [filename, blob_path, "success", None]
                else:
                    os.makedirs(os.path.dirname(local_save_path), exist_ok=True)
                    with open(local_save_path, 'w', encoding='utf-8') as f:
                        f.write(text_content)
                    logging.info(f"[SAVE] TXT guardado localmente en: {local_save_path}")
                    print(f"TXT guardado en: {local_save_path}")
                    df_ingestion.loc[len(df_ingestion)] = [filename, local_save_path, "success", None]
            else:
                logging.info(f"[SKIP] Ya existía: {blob_path}")
                print(f"[SKIP] Ya existe: {blob_path}")
        except Exception as e:
            error_message = f"Error al procesar TXT de la página {page_id}: {e}"
            logging.error(error_message)
            df_ingestion.loc[len(df_ingestion)] = [f'page_{page_id}.txt', output_folder, "failure", error_message]
            print(error_message)

        return df_ingestion
    
    
    def _download_pdf(self, page_id, fallback_title, df_ingestion, output_folder):
        # Build the URL to get page details (like the title)
        title_url = f'{self.base_url}/rest/api/content/{page_id}'

        headers = self.get_headers()
        if self.auth:
            title_response = requests.get(title_url, headers=headers, auth=self.auth)
        else:
            title_response = requests.get(title_url, headers=headers)

        if title_response.status_code == 200:
            page_title = title_response.json()['title'].replace(' ', '_').replace('/', '_')
        else:
            page_title = fallback_title or f'page_{page_id}'
            logging.warning(f'[WARN] Could not retrieve title for page {page_id}, using fallback.')

        # Build the URL to download the page as a PDF
        pdf_url = f'{self.base_url}/spaces/flyingpdf/pdfpageexport.action?pageId={page_id}'
        logging.info(f'Downloading PDF: {page_title} from {pdf_url}')
        #Solo headers, NO auth
        response = requests.get(pdf_url, headers={"Authorization": f"Bearer {self.token}"})

        if response.status_code == 200:
            filename = f'{page_title}_{page_id}.pdf'.replace(" ", "_")
            blob_path = f"confluence_exports/{filename}"
            local_save_path = os.path.join(output_folder, blob_path.replace("/", os.sep))

            ya_existe = False

            if self.to_azure_blob:
                blob_client = self.container_client.get_blob_client(blob_path)
                ya_existe = blob_client.exists()
            else:
                ya_existe = os.path.exists(local_save_path)

            if not ya_existe:
                if self.to_azure_blob:
                    blob_client.upload_blob(response.content)
                    logging.info(f"[UPLOAD] Subido a Azure Blob: {blob_path}")
                    print(f"[UPLOAD] Subido: {blob_path}")
                    df_ingestion.loc[len(df_ingestion)] = [filename, blob_path, "success", None]
                else:
                    os.makedirs(os.path.dirname(local_save_path), exist_ok=True)
                    with open(local_save_path, 'wb') as f:
                        f.write(response.content)
                    logging.info(f"[SAVE] Guardado localmente en: {local_save_path}")
                    print(f"PDF guardado en: {local_save_path}")
                    df_ingestion.loc[len(df_ingestion)] = [filename, local_save_path, "success", None]
            else:
                logging.info(f"[SKIP] Ya existía: {blob_path}")
                print(f"[SKIP] Ya existe: {blob_path}")
        else:
            error_message = f'Error al descargar PDF de la página {page_id}: {response.status_code} - {response.text}'
            logging.error(error_message)
            df_ingestion.loc[len(df_ingestion)] = [f'page_{page_id}.pdf', output_folder, "failure", error_message]
            print(error_message)