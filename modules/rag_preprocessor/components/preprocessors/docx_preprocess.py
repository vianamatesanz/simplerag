"""
This is the main class for processing Docx files. It does the following:

- Process all the text.
- Convert images to descriptions.
- Convert tables to a list format.

All the information is joined and converted into LangChain Documents.
"""

# Import libraries
import os
import base64
import docx
from langchain.docstore.document import Document
import openai
import logging
from pathlib import Path
import itertools
import re
from langsmith import traceable
import subprocess
import time
import shutil
import uuid
from docx.opc.exceptions import PackageNotFoundError


class DocxProcessor:
    '''
    Docxs preprocessor class.
    '''

    def __init__(self,
                 doc_path,
                 llm_images = None,
                 system_prompt_describe_images = None,
                 persist_files = True,
                 images_path = './data/extracted_images',
                 output_check_path = './data/output_check',
                 now = None,
                 monitorize = False):
        
        '''
        Initializes the class for preprocessing DOCX documents, extracting content such as sections, images, and tables, 
        and optionally persisting the extracted data to files.
        
        :param doc_path: Path to the DOCX document to be processed.
        :type doc_path: str
        :param llm_images: Optional language model for processing images.
        :type llm_images: object or None
        :param system_prompt_describe_images: Optional system prompt for describing images.
        :type system_prompt_describe_images: str or None
        :param persist_files: Flag to indicate whether to persist extracted files to disk.
        :type persist_files: bool
        :param images_path: Directory path where extracted images will be saved.
        :type images_path: str
        :param output_check_path: Directory path for saving output check files.
        :type output_check_path: str
        :param now: Optional timestamp or datetime for versioning or tracking.
        :type now: str or None
        :param monitorize: Flag to enable or disable monitoring during processing.
        :type monitorize: bool
        '''

        self.doc_path = doc_path
        self.llm = llm_images
        self.system_prompt_describe_images = system_prompt_describe_images
        self.persist_files = persist_files
        self.output_check_path = output_check_path
        self.now = now
        self.monitorize = monitorize

        # Variables to save documents content
        self.sections = None
        self.images_info = None
        self.tables_info = None
        self.image_text_info = None

        # Persist documents generated
        if self.persist_files:
            self.output_dir = Path(images_path) / os.path.basename(doc_path)

    def doc2docx(self):
        '''
        Function to convert a doc into a docx.
        '''

        # Detect the operating system in order to change the conversion method
        # Windows
        if os.name == 'nt':
            import win32com.client as win32
            import pywintypes
            word = win32.Dispatch("Word.Application")
            word.Visible = False
            abs_path = os.path.abspath(self.doc_path)
            try:
                doc = word.Documents.Open(abs_path)
                new_path = abs_path.replace('.doc', '.docx')
                doc.SaveAs(new_path, FileFormat=16)
                doc.Close()
            except pywintypes.com_error as e:
                # Make the name of the file shorter
                logging.warning(f'Name of the doc file too long to make the conversion. Shorting it... \n{e}')
                max_length = 20
                dir_path, filename = os.path.split(abs_path)
                base_name, ext = os.path.splitext(filename)

                truncated_name = (base_name[:max_length] + '...')

                new_filename = truncated_name + ext
                new_path_read = os.path.join(dir_path, f'temp_{uuid.uuid4().hex[:8]}_{new_filename}')
                # try:
                shutil.copy(abs_path, new_path_read)
                # except PermissionError:
                    # doc.Close()
                    # os.rename(abs_path, new_path_read)
                time.sleep(3)
                doc = word.Documents.Open(new_path_read)
                new_path = new_path_read.replace('.doc', '.docx')
                doc.SaveAs(new_path, FileFormat=16)
                doc.Close()
                os.remove(new_path_read)
            word.Quit()
        # Linux
        elif os.name == 'posix':
            subprocess.run(["libreoffice", "--headless", "--convert-to", "docx", os.path.abspath(self.doc_path)])
        
        else:
            logging.error('Your OS is not Windows nor Linux. Cannot convert doc to docx.')

        return new_path

    def extract_images_and_rels(self, doc):
        '''
        Extract images and relationship (rels) IDs from the document.

        :param doc: The docx document.
        :type doc: Docx Document.
        '''

        images_info = []  # Initialize a list to store info about images
        image_rels = {}   # Dictionary to store image relationship IDs and filenames

        # Loop through all the relationships (rels) in the document part
        for rel in doc.part.rels.values():
            if isinstance(rel._target, docx.parts.image.ImagePart):
                image_filename = os.path.basename(rel._target.partname)

                # If saving images to disk is enabled, write the image file
                if self.persist_files:
                    if not os.path.exists(self.output_dir):
                        os.makedirs(self.output_dir)
                    image_path = os.path.join(self.output_dir, image_filename)
                    with open(image_path, 'wb') as img_file:
                        img_file.write(rel._target.blob)

                # Store the relationship ID (rId) and associated image filename
                image_rels[rel.rId] = image_filename

                # Encode the image binary data as base64 and store the image info
                encoded_string = base64.b64encode(rel._target.blob).decode('utf-8')
                images_info.append({
                    'filename': image_filename,
                    'content_type': encoded_string
                })

        # Save the extracted image information to an instance variable
        self.images_info = images_info
        return image_rels

    def extract_and_number_tables(self, doc):
        '''
        Extract tables from the document and convert them into a list.

        :param doc: The docx document.
        :type doc: Docx Document.
        '''

        # Initialize a list to store the content of numbered tables
        numbered_tables_content = []
        
        # Loop through each table in the document, keeping track of the table index
        for table_index, table in enumerate(doc.tables):
            table_content = []
            
            # Loop through each row in the current table, tracking the row index
            for row_index, row in enumerate(table.rows):
                row_number = f'{row_index + 1}'
                # Get the text content of each cell, stripping any extra whitespace
                row_content = [row_number] + [cell.text.strip() for cell in row.cells]
                # Add the numbered row content to the table's content list
                table_content.append(row_content)
            
            # After processing all rows, add the table content to the overall list of tables
            numbered_tables_content.append(table_content)
        
        return numbered_tables_content


    def extract_text_image(self, doc, image_rels):
        '''
        Extract the text, images, and the paragraph immediately preceding the image from the document.

        :param doc: The docx document.
        :type doc: Docx Document.
        :param image_rels: Rel Ids for the images.
        :type image_rels: dict
        '''

        sections = {}  # Dictionary to store sections and their associated content
        current_section = None  # Variable to track the current section
        current_text = []  # List to accumulate text content for the current section
        section_count = {}  # Dictionary to track how many times each section name appears

        image_text_info = {}  # Dictionary to store information about paragraphs associated with images

        # Get all elements (paragraphs, tables, etc.) in the document body
        body_elements = list(doc.element.body)

        image_count = 0  # Counter to track the number of images

        # Loop through each element in the document's body
        for i, element in enumerate(body_elements):
            # Check if the element is a paragraph ('p')
            if element.tag.endswith('p'):
                paragraph = docx.text.paragraph.Paragraph(element, doc)

                # Check if the paragraph contains an image (based on 'Graphic' in the XML)
                if 'Graphic' or ':pict' in element.xml:
                    # Loop through image relationships to find matching images
                    for rId, filename in image_rels.items():
                        if rId in element.xml:
                            # Add a placeholder for the image to the current section's text
                            current_text.append(f'Imagen {image_count + 1}: {filename}')

                            # Extract the paragraph immediately preceding the image, if it exists
                            if i > 0 and body_elements[i-1].tag.endswith('p'):
                                prev_paragraph = docx.text.paragraph.Paragraph(body_elements[i-1], doc)
                                image_text_info[filename] = prev_paragraph.text.strip()
                            image_count += 1
                            break  # Stop after finding the image for this paragraph

                # If the paragraph is a heading, start a new section
                if paragraph.style.name.startswith('Heading'):
                    # If we're already in a section, save its content before starting a new one
                    if current_section:
                        sections[current_section] = '\n'.join(current_text).strip()
                    # Set the current section to the heading's text
                    # Verify if the section name already exists
                    base_section = paragraph.text.strip()
                    if base_section in section_count:
                        section_count[base_section] += 1
                        current_section = f'{base_section} ({section_count[base_section]})'
                    else:
                        section_count[base_section] = 1
                        current_section = base_section

                    current_text = []  # Clear the text list for the new section

                # If the paragraph is not a heading, add its text to the current section
                else:
                    if not current_section:
                        current_section = "Body"
                    current_text.append(paragraph.text.strip())

            # Check if the element is a table ('tbl')
            # Removed table extraction code, as we only extract the preceding paragraph for images

        # After the loop, save the last section's content
        if current_section:
            sections[current_section] = '\n'.join(current_text).strip()

        # Save the sections and return them
        self.sections = sections
        self.image_text_info = image_text_info


    @traceable
    def describe_image(self, image_base64, text_info = None):
        '''
        Describe the image using a Large Language Model (LLM).

        :param image_base64: Image in Base64.
        :type image_base64: string
        :param text_info: Table info associated with the image.
        :type text_info: list
        '''

        # Get table description
        if text_info:
            text_description = '\n'.join([f'Element {i+1}: {desc}' for i, desc in enumerate(text_info or [])])
        else:
            text_description = ''

        # Prepare the message to send to the LLM
        message = [
            {
                'role': 'system',
                'content': self.system_prompt_describe_images['text']  # Provide system-level prompt for describing images
            },
            {
                'role': 'user',
                'content': [
                    # Send the image as a base64-encoded string in a format that the LLM understands
                    {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{image_base64}'}},
                    {'type': 'text', 'text': text_description}
                ]
            }
        ]
        
        try:
            # Invoke the LLM API with the prepared message
            response = self.llm.invoke(message)
            return response.content
        except openai.APIStatusError as e:
            logging.info(f'Error processing the image: {e}')
            return ''
        
    def process_images(self):
        '''
        Generate image descriptions and save them.
        '''

        for i, image in enumerate(self.images_info):
            # Get table info below the image
            text_info = self.image_text_info.get(image['filename'], None)

            # Generate a description for the image based on its content type.
            description = self.describe_image(image['content_type'], text_info)
            
            # Store the generated description back in the images_info list.
            self.images_info[i]['description'] = description
            self.images_info[i]['text_info'] = text_info

            if self.persist_files:
                # Create a unique filename for each image description (e.g., 'image1.txt').
                image_filename = f'image{i+1}.txt'
                
                # Build the full file path for saving the description in the specified output directory.
                image_filepath = os.path.join(self.output_dir, image_filename)
                
                # Open the file in write mode and save the description in UTF-8 encoding.
                with open(image_filepath, 'w', encoding = 'utf-8') as f:
                    f.write(description)

        return self.images_info


    def replace_image_references(self):
        '''
        Replace the image references in the text with the corresponding descriptions.
        '''
        
        # Dictionary to store sections with updated content after replacing image references.
        updated_sections = {}
        
        # Loop through each section in the text.
        for section, content in self.sections.items():
            updated_content = content  # Start with the original content of the section.

            # Find the image placeholders and replace them
            matches = re.findall(r'Imagen \d+: (\S+)', updated_content)
            if matches:
                for image_filename in matches:
                    for image in self.images_info:
                        if image['filename'] == image_filename:
                            image_description = image['description']
                            updated_content = updated_content.replace(image_filename, image_description)
            
            # Store the updated content in the new dictionary under the same section key.
            updated_sections[section] = updated_content
        
        return updated_sections


    def process_document(self):
        '''
        Process the whole document.
        '''
        
        # Read document
        try:
            doc = docx.Document(self.doc_path)
        except PackageNotFoundError:
            doc = docx.Document()
            doc.save(self.doc_path)
            logging.info('Corrupted docx. Saving new one.')
        
        # Extract the images and their relationships (e.g., references within the document).
        image_rels = self.extract_images_and_rels(doc)
        
        # Extract text, images, and tables from the document, using the image relationships.
        self.extract_text_image(doc, image_rels)
        
        # Process each image by generating descriptions and saving them if required.
        self.process_images()
        
        # Replace any image references in the document's sections with their corresponding descriptions.
        updated_sections = self.replace_image_references()

        # If persist_files is True, save text file to monitorize chunking.
        if self.monitorize:
            # Create sep between sections
            sep = '\n' + '#' * 100 + '\n'
            output_text_path = f'{self.output_check_path}/monitoring_chunking_{self.now}.txt'
            for section, content in updated_sections.items():
                with open(output_text_path, 'a', encoding = 'utf-8') as f:
                    f.write(f'FILENAME: {os.path.basename(self.doc_path)}\n\n')
                    f.write(f'SECTION: {section}\n')
                    f.write(f'CONTENT: {content}\n')
                    f.write(sep)

        # Update the object's sections attribute with the new sections containing image descriptions
        self.sections = updated_sections


    def to_langchain_documents(self):
        '''
        Convert all the extracted content into LangChain documents.
        '''
        
        # Initialize an empty list to store the LangChain documents.
        documents = []
        
        # Loop through each section and its corresponding content.
        id_sibling = 0
        for section, content in self.sections.items():
            # Create metadata for the document, including the source file path, section name, and document type.
            metadata = {
                'section_name': section,
                'id_sibling': id_sibling
            }

            id_sibling += 1

            # Create a LangChain Document object with the section's content and its metadata.
            document = Document(page_content = f'{section} {content}', metadata = metadata)
            documents.append(document)

        return documents

