"""
This is the Ingester. It takes all documentation from a Sharepoint and dumps it into a Blob Storage.
"""

# Import packages
import logging
import os
import pandas as pd
import urllib.parse
import traceback

#import modules.sql.sql_functions as sqlf
import traceback
from azure.storage.blob import BlobServiceClient
from msal import ConfidentialClientApplication
import datetime
import requests
#from .config_sharepoint import librerias_a_ignorar
from docx import Document
from io import BytesIO


class SharePointIngestor:
    def __init__(self,
                 sharepoint_url,
                 client_id,
                 client_secret,
                 tenant_id,
                 site_domain,
                 site_path,
                 scope,
                 cliente,
                 librerias_ignorar,
                 carpetas_ignorar,
                 to_azure_blob,
                 download_folder_name,
                 blob_connection_string= None,
                 blob_container_name=None):
        #self.ctx = ClientContext(sharepoint_url).with_credentials(ClientCredential(client_id, client_secret))
        #self.ctx_list = self.ctx.web.lists
        self.site_url = sharepoint_url
        self.client_id = client_id
        self.secret = client_secret
        self.tenant_id = tenant_id
        self.site_domain = site_domain
        self.site_path = site_path
        self.download_folder_name = download_folder_name
        # Define el alcance del token: Graph API (no el dominio de SharePoint directamente)
        self.scope = [scope]
        # Construye la URL de autoridad (punto de autenticación del tenant en Entra ID)
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"

        # Inicializa el cliente MSAL con client_id y client_secret registrados en Entra
        self.app =ConfidentialClientApplication(self.client_id,
                                            authority=self.authority,
                                            client_credential=self.secret)
        # Solicita un token de acceso usando el flujo client credentials
        self.token = self.app.acquire_token_for_client(scopes=self.scope)
        self.token_obtenido_en = datetime.datetime.utcnow()
        self.token_duracion = self.token.get("expires_in", 3600) 

        #blobstorage
        self.blob_connection_string = blob_connection_string
        self.blob_container_name = blob_container_name

        self.cliente = cliente
        self.librerias_ignorar = librerias_ignorar
        self.to_azure_blob = to_azure_blob
        self.carpetas_ignorar = carpetas_ignorar or []

    def token_expirado(self):
        ahora = datetime.datetime.utcnow()
        expiracion = self.token_obtenido_en + datetime.timedelta(seconds=self.token_duracion)
        return ahora >= expiracion

    def renovar_token_si_necesario(self):
        if self.token_expirado():
            print("[INFO] 🔄 Token expirado. Renovando...")
            token_result = self.app.acquire_token_for_client(scopes=self.scope)
            if "access_token" not in token_result:
                print(f"[ERROR] Respuesta MSAL: {token_result}")
                raise Exception("❌ No se pudo renovar el token")
            self.token_obtenido_en = datetime.datetime.utcnow()
            self.token_duracion = token_result.get("expires_in", 3600)
            self.access_token = token_result["access_token"]  # <-- útil si lo usas en otros sitios
            self.headers = {"Authorization": f"Bearer {self.access_token}"}
            print("[INFO] ✅ Token renovado con éxito.")
            return True  # Opcional: indicar si se renovó
        return False

    def subir_a_blob(self,blob_path, file_bytes):
        """
        Sube un archivo al Blob Storage conservando la ruta del SharePoint.
        blob_path puede ser: 'subcarpeta1/subcarpeta2/archivo.pdf'
        """
        blob_service_client = BlobServiceClient.from_connection_string(self.blob_connection_string)
        blob_client = blob_service_client.get_blob_client(container=self.blob_container_name, blob=blob_path)

        # Crea contenedor si no existe (opcional)
        try:
            blob_service_client.create_container( self.blob_container_name)
        except Exception:
            pass  # ya existe

        # Subida del contenido binario
        blob_client.upload_blob(file_bytes, overwrite=True)
        print(f"☁️ Subido a blob: {blob_path}")

    
    def test_sharepoint_connection(self):
        """
        Verifica la conexión a SharePoint:
        - Obtiene un token de acceso usando Microsoft Entra ID (MSAL)
        - Hace una llamada real al sitio SharePoint mediante Microsoft Graph
        - Imprime el nombre del sitio si la conexión es exitosa
        """

        # 1. Verifica si tienes token
        if "access_token" not in self.token:
            print("❌ No se pudo obtener token:", self.token.get("error_description"))
            return False

        access_token = self.token["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        print("✅ Token obtenido con éxito")

        site_url = f"https://graph.microsoft.com/v1.0/sites/{self.site_domain}:{self.site_path}"

        # 2. Intenta la petición
        self.renovar_token_si_necesario()
        response = requests.get(site_url, headers=headers)

        # 3. Si da 401, renueva token UNA VEZ y reintenta
        if response.status_code == 401:
            print("[INFO] Token expirado, solicitando nuevo...")
            self.token = self.app.acquire_token_for_client(scopes=self.scope)
            if "access_token" not in self.token:
                print("❌ No se pudo renovar el token.")
                return False
            headers["Authorization"] = f"Bearer {self.token['access_token']}"
            self.renovar_token_si_necesario()
            response = requests.get(site_url, headers=headers)

        # 4. Si sigue fallando, reporta el error
        if response.status_code != 200:
            print("❌ Error al acceder al sitio SharePoint:", response.status_code, response.text)
            return False

        # 5. OK!
        site_data = response.json()
        print(f"📡 Conexión correcta a SharePoint. Título del sitio: {site_data.get('displayName')}")
        return {"response": response, "headers": headers}
    
    def listar_ingestar(self, file_extensions: list,):
        """
        Lista las bibliotecas de documentos en un sitio SharePoint y procesa recursivamente
        los archivos que coincidan con ciertas extensiones, subiéndolos a Azure Blob Storage.
        Guarda los resultados en un DataFrame (sin Redis).
        """
        df_ingestion = pd.DataFrame(
            columns=['filename', 'directory', 'state_ingested', 'failure_reason']
        )

        response_data_dict = self.test_sharepoint_connection()
        if not response_data_dict:
            print("❌ Conexión a SharePoint fallida. Abortando ingestión.")
            return None

        site_id = response_data_dict['response'].json().get("id")
        if not site_id:
            print("❌ No se pudo obtener el ID del sitio.")
            return None

        lists_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists"
        self.renovar_token_si_necesario()
        response = requests.get(lists_url, headers=response_data_dict['headers'])
        if response.status_code != 200:
            print("❌ Error al obtener listas:", response.status_code, response.text)
            return None

        listas = response.json().get("value", [])
        if not listas:
            print("⚠️ No se encontraron listas en el sitio.")
            return None

        for lista in listas:
            list_name = lista.get("name")
            list_id = lista.get("id")
            is_document_library = lista.get("list", {}).get("template") == "documentLibrary"

            if not is_document_library:
                continue

            print("LISTA_NAME:", list_name  )

            if list_name in self.librerias_ignorar:
                print(f"[KO] Librería '{list_name}' está en la lista de exclusión. Saltando.")
                continue

            print(f"[OK] Intentando acceder a la librería '{list_name}'...")

            try:
                drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_id}/drive"
                drive_resp = requests.get(drive_url, headers=response_data_dict['headers'])

                if drive_resp.status_code != 200:
                    print(f"[WARN] No se encontró el drive para '{list_name}':", drive_resp.text)
                    continue

                drive = drive_resp.json()
                drive_id = drive.get("id")
                if not drive_id:
                    print(f"[WARN] Drive sin ID en '{list_name}'")
                    continue

                self._listar_contenido(
                    drive_id=drive_id,
                    folder_path="",
                    file_extensions=file_extensions,
                    df_ingestion=df_ingestion,
                    headers=response_data_dict['headers'],
                    library_name=list_name
                )

            except Exception as e:
                print(f"[ERROR] Fallo procesando '{list_name}': {type(e).__name__}: {e}")
                continue

        print("[OK] Ingesta completada.")
        df_ingestion.to_csv("resumen_ingesta.csv", index=False)
        return df_ingestion



    def _listar_contenido(self, drive_id, folder_path, file_extensions, df_ingestion, headers,library_name):
        """
        Recorre recursivamente las carpetas de una biblioteca de documentos, 
        ignorando aquellas cuya ruta completa esté en la lista negra (self.carpetas_ignorar).
        """
        try:
            base_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root"
            if folder_path:
                url = f"{base_url}:/{folder_path}:/children"
                path_actual = folder_path
            else:
                url = f"{base_url}/children"
                path_actual = ""

            # --- FILTRO DE RUTA COMPLETA ---
            def normaliza(ruta):
                """Normaliza separadores, minúsculas y quita barras iniciales/finales."""
                return ruta.replace("\\", "/").lower().strip().strip("/")

            path_actual_norm = normaliza(path_actual)
            library_name_norm = normaliza(library_name)
            # Si tienes rutas relativas al nombre de la biblioteca:
            ruta_completa = f"{library_name_norm}/{path_actual_norm}".strip("/")

            ignorar = False
            for ruta_ignorar in self.carpetas_ignorar:
                ruta_ignorar_norm = normaliza(ruta_ignorar)
                # Coincidencia exacta o como prefijo (todas sus subcarpetas)
                if ruta_completa == ruta_ignorar_norm or ruta_completa.startswith(ruta_ignorar_norm + "/"):
                    print(f"[IGNORADO] Carpeta ignorada por filtro de ruta: {ruta_completa}")
                    ignorar = True
                    break

            if ignorar:
                return  # No bajas ni procesas nada dentro de esta carpeta
            self.renovar_token_si_necesario()
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                print(f"[ERROR] Error accediendo a '{path_actual}':", response.status_code, response.text)
                return

            items = response.json().get("value", [])
            print(f"[DEBUG] 📁 {len(items)} ítems encontrados en {path_actual}")

            for item in items:
                name = item.get("name", "SinNombre")
                item_path = f"{path_actual}/{name}" if path_actual else name

                if "folder" in item:
                    print(f"[DEBUG] Subcarpeta: {name}")
                    self._listar_contenido(
                        drive_id=drive_id,
                        folder_path=item_path,
                        file_extensions=file_extensions,
                        df_ingestion=df_ingestion,
                        headers=headers,
                        library_name=library_name
                    )
                elif "file" in item:
                    file_type = name.split('.')[-1].lower() if '.' in name else 'unknown'
                    print(f"[DEBUG] Archivo encontrado: {name} ({file_type})")

                    if "." + file_type not in file_extensions:
                        print(f"[DEBUG] Archivo {name} saltado por extensión.")
                        continue

                    # Calcula ruta relativa para Azure Blob
                    relative_path = item_path.replace("\\", "/")
                    blob_path = f"{self.cliente}/{library_name}/{relative_path}".lstrip("/")

                    local_save_dir = self.download_folder_name
                    local_save_path = os.path.join(local_save_dir, blob_path.replace("/", os.sep))

                    ya_existe = False

                    if self.to_azure_blob:
                        if not self.blob_connection_string or not self.blob_container_name:
                            raise ValueError("Falta blob_connection_string o blob_container_name")
                        
                        blob_service_client = BlobServiceClient.from_connection_string(self.blob_connection_string)

                        try:
                            blob_client = blob_service_client.get_blob_client(
                                container=self.blob_container_name,
                                blob=blob_path
                            )
                            ya_existe = blob_client.exists()
                        except Exception as e:
                            print(f"[ERROR] No se pudo acceder al blob {blob_path}: {e}")
                            ya_existe = False
                    else:
                        ya_existe = os.path.exists(local_save_path)

                    if not ya_existe:
                        try:
                            download_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item['id']}/content"
                            download_resp = requests.get(download_url, headers=headers)

                            if download_resp.status_code != 200:
                                print(f"[ERROR] No se pudo descargar {name}: {download_resp.status_code}")
                                df_ingestion.loc[len(df_ingestion)] = [name, path_actual, "error", f"Descarga fallida ({download_resp.status_code})"]
                                continue

                            # Sube archivo al Blob

                            if self.to_azure_blob:
                                blob_client.upload_blob(download_resp.content)
                                print(f"[UPLOAD] Subido: {blob_path}")

                            else:
                                print(f"[DEBUG] Simulación de subida a blob: {blob_path}")

                            local_save_dir = self.download_folder_name
                            os.makedirs(local_save_dir, exist_ok=True)
                            local_save_path = os.path.join(local_save_dir, blob_path.replace("/", os.sep))
                            os.makedirs(os.path.dirname(local_save_path), exist_ok=True)
                            with open(local_save_path, "wb") as f:
                                f.write(download_resp.content)
                            print(f"[SAVE] Guardado en local: {local_save_path}")
                            df_ingestion.loc[len(df_ingestion)] = [name, path_actual, "uploaded", ""]

                        except Exception as e:
                            print(f"[ERROR] No se pudo subir {blob_path} al blob: {e}")
                            df_ingestion.loc[len(df_ingestion)] = [name, path_actual, "error", str(e)]
                    else:
                        print(f"[SKIP] Ya existe: {blob_path}")
                        df_ingestion.loc[len(df_ingestion)] = [name, path_actual, "ya_existia", ""]

        except Exception as e:
            print(f"[!] Error accediendo a carpeta '{folder_path}': {e}")

    def listar_bibliotecas(self):
            """
            Devuelve una lista de bibliotecas de documentos (nombre e id) del sitio SharePoint configurado.
            """
            # 1. Verifica el token
            if "access_token" not in self.token:
                print("❌ No se pudo obtener token:", self.token.get("error_description"))
                return None

            access_token = self.token["access_token"]
            headers = {"Authorization": f"Bearer {access_token}"}
            site_url = f"https://graph.microsoft.com/v1.0/sites/{self.site_domain}:{self.site_path}"

            # 2. Obtiene el ID del sitio
            self.renovar_token_si_necesario()
            response = requests.get(site_url, headers=headers)
            if response.status_code != 200:
                print("❌ Error al acceder al sitio SharePoint:", response.status_code, response.text)
                return None
            site_id = response.json().get("id")
            if not site_id:
                print("❌ No se pudo obtener el ID del sitio.")
                return None

            # 3. Pide la lista de "lists" (listas y bibliotecas)
            lists_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists"
            self.renovar_token_si_necesario()
            response = requests.get(lists_url, headers=headers)
            if response.status_code != 200:
                print("❌ Error al obtener listas:", response.status_code, response.text)
                return None

            listas = response.json().get("value", [])
            # 4. Filtra solo las de tipo 'documentLibrary'
            bibliotecas = [
                {"name": l.get("name"), "id": l.get("id")}
                for l in listas if l.get("list", {}).get("template") == "documentLibrary"
            ]

            # 5. Imprime y retorna
            if not bibliotecas:
                print("⚠️ No se encontraron bibliotecas de documentos en el sitio.")
                return []
            print("Bibliotecas de documentos encontradas:")
            for b in bibliotecas:
                print(f"- {b['name']} (ID: {b['id']})")
            return bibliotecas