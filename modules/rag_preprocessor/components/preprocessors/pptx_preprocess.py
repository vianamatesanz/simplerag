"""
This is the main class for processing PPTx files. It does the following:

- Convert Slides into images.
- Describe every image.

All the information is joined and converted into LangChain Documents.

There are some commented functions to create a summary by section. They are commented
because the section split method was very ad-hoc to a use case. It must be configured
so that it can be generalized for every section split method.
"""

# Import libraries
import os
import base64
from langchain.docstore.document import Document
from langsmith import traceable
from pathlib import Path


class PptxProcessor:
    '''
    PPTx preprocessor class.
    '''

    def __init__(self,
                 pptx_path,
                 llm_images,
                 system_prompt_describe_images,
                 system_prompt_create_summaries,
                 persist_files = True,
                 images_path = None):
        '''
        Init function.

        :param pptx_path: PPTx path.
        :type pptx_path: string
        :param llm_images: LLM model to describe images.
        :type llm_images: OpenAIModel
        :param system_prompt_describe_images: Prompt to describe images.
        :type system_prompt_describe_images: string
        :param system_prompt_create_summaries: Prompt to create summaries of the document.
        :type system_prompt_create_summaries: string
        :param persist_files: True if files with descriptions should be saved.
        :type persist_files: boolean
        :param images_path: Path to save images.
        :type images_path: string
        '''

        self.pptx_path = pptx_path
        self.llm = llm_images
        self.system_prompt_describe_images = system_prompt_describe_images
        self.system_prompt_create_summaries = system_prompt_create_summaries
        self.persist_files = persist_files

        # Variables to save documents content
        self.slides_info = []

        # Persist documents generated
        self.images_path = Path(images_path) / os.path.basename(self.pptx_path)
        if not os.path.exists(self.images_path):
            os.makedirs(self.images_path)

    def export_slide_as_blob(self, slide):
        '''
        Function to export the slide to a blob.

        :param slide: A PPTx slide.
        :type slide: PowerPoint Slide
        '''

        # Create a temporary file path for saving the slide as a PNG image
        temp_image_path = os.path.join(self.images_path, 'temp_image.png')
        
        # Export the slide to the temporary file in PNG format
        slide.Export(os.path.abspath(temp_image_path), 'PNG')
        
        # Open the temporary PNG file in binary mode and read its contents into a blob
        with open(temp_image_path, 'rb') as temp_image_file:
            slide_blob = temp_image_file.read()
        
        # Remove the temporary file after reading its contents
        os.remove(temp_image_path)
        
        # Return the binary content (blob) of the slide
        return slide_blob

    def pptx_to_png_windows(self):
        '''
        Convert every pptx slide to png file.
        '''

        import comtypes.client
        # Initialize the COM library for PowerPoint automation
        comtypes.CoInitialize()
        
        # Create a PowerPoint application object
        powerpoint = comtypes.client.CreateObject('PowerPoint.Application')
        
        # # Open the PowerPoint presentation file
        presentation = powerpoint.Presentations.Open(os.path.abspath(self.pptx_path))
        
        # Initialize a list to store slide numbers with 'Índex' text to create summaries in the next step
        self.slide_index_numbers = []
        
        # Loop through each slide in the presentation
        for i, slide in enumerate(presentation.Slides):

            # Loop through each shape on the slide
            for shape in slide.Shapes:
                if shape.HasTextFrame:  # Check if the shape contains a text frame
                    if shape.TextFrame.HasText:  # Check if the text frame contains text
                        text = shape.TextFrame.TextRange.Text
                        if text == 'Índex':  # If the text is 'Índex', save the slide number
                            self.slide_index_numbers.append(i + 1)

            # Generate a filename for the slide image
            image_filename = f'{os.path.basename(self.pptx_path)}_slide_{i+1}.png'
            
            # Create the full path for the image
            image_path = os.path.join(self.images_path, image_filename)
            
            if self.persist_files:
                # If the persist_files flag is set, export the slide as a PNG file
                slide.Export(os.path.abspath(image_path), 'PNG')
                
                # Read the PNG file and store its binary data in slide_blob
                with open(image_path, 'rb') as img_file:
                    slide_blob = img_file.read()
            else:
                # If not persisting files, export the slide to a blob directly
                slide_blob = self.export_slide_as_blob(slide)

            # Encode the slide blob as a base64 string
            encoded_string = base64.b64encode(slide_blob).decode('utf-8')

            # Create a dictionary with slide information
            slide_info = {
                'slide_number': i + 1,
                'image_filename': image_filename,
                'image_base64': encoded_string
            }
            
            # Add the slide info to the slides_info list
            self.slides_info.append(slide_info)

        # Close the PowerPoint presentation and quit the application
        presentation.Close()
        powerpoint.Quit()
        
        # Uninitialize the COM library
        comtypes.CoUninitialize()

    def pptx_to_png_linux(self):
        """
        Convert every pptx slide to png file (Linux/Docker compatible).
        """

        import subprocess
        from pdf2image import convert_from_path

        pptx_abs_path = os.path.abspath(self.pptx_path)
        pdf_path = os.path.join(self.images_path, "temp_presentation.pdf")

        # ⚠️ Trucar nombre si es muy largo o tiene caracteres raros
        safe_pptx_path = os.path.join(
            os.path.dirname(pptx_abs_path),
            "temp_input.pptx"
        )
        if pptx_abs_path != safe_pptx_path:
            import shutil
            shutil.copy(pptx_abs_path, safe_pptx_path)
            pptx_abs_path = safe_pptx_path

        # 1. Convert PPTX to PDF with LibreOffice
        subprocess.run([
            "soffice", "--headless", "--convert-to", "pdf",
            "--outdir", str(self.images_path),
            str(pptx_abs_path)
        ], check=True)

        # El PDF se genera con el mismo nombre que el PPTX, pero extensión .pdf
        generated_pdf = os.path.join(
            self.images_path,
            Path(pptx_abs_path).stem + ".pdf"
        )

        # Renombramos/movemos a temp_presentation.pdf para evitar errores
        os.rename(generated_pdf, pdf_path)

        # 2. Convert PDF pages to PNG
        pages = convert_from_path(pdf_path, dpi=150, output_folder=self.images_path)

        self.slide_index_numbers = []
        for i, page in enumerate(pages):
            image_filename = f"{os.path.basename(self.pptx_path)}_slide_{i+1}.png"
            image_path = os.path.join(self.images_path, image_filename)

            page.save(image_path, "PNG")

            with open(image_path, "rb") as img_file:
                slide_blob = img_file.read()

            encoded_string = base64.b64encode(slide_blob).decode("utf-8")

            slide_info = {
                "slide_number": i + 1,
                "image_filename": image_filename,
                "image_base64": encoded_string,
            }
            self.slides_info.append(slide_info)

        os.remove(pdf_path)


    def group_descriptions_by_section(self, slides_descriptions, section_indexes):
        '''
        Function to group the obtained descriptions by section. Every
        section starts when the "Índex" slide appears.

        :param slides_descriptions: Slide descriptions.
        :type slides_descriptions: dict
        :param section_indexes: List of indexes where "Índex" slides are located.
        :type section_indexes: list
        '''

        # Dictionary to store the grouped descriptions by section
        sections_descriptions = {}
        
        # Total number of sections based on the provided section indexes
        sections_num = len(section_indexes)

        # Loop through each slide description
        for i, description_dict in enumerate(slides_descriptions):
            
            # Loop through each section index to determine which section the description belongs to
            for j, init_section in enumerate(section_indexes):
                
                # If it's the last section, append all remaining descriptions to it
                if j == sections_num - 1:
                    section_name = f'Sección {j + 1}'  # Name of the section (e.g., "Sección 1")
                    
                    # Create the section in the dictionary if it doesn't exist
                    if section_name not in sections_descriptions:
                        sections_descriptions[section_name] = []
                    
                    # Add the current slide's description to the section
                    sections_descriptions[section_name].append(description_dict['description'])
                
                # If not the last section, check if the current slide index falls between two section boundaries
                else:
                    if init_section <= i + 1 < section_indexes[j + 1]:
                        section_name = f'Sección {j + 1}'
                        
                        # Create the section in the dictionary if it doesn't exist
                        if section_name not in sections_descriptions:
                            sections_descriptions[section_name] = []
                        
                        # Add the current slide's description to the section
                        sections_descriptions[section_name].append(description_dict['description'])
                        break  # Move to the next slide after assigning it to a section
        
        # Return the dictionary with descriptions grouped by section
        return sections_descriptions

    @traceable
    def get_section_summaries(self, sections_descriptions):
        '''
        Function to get the summaries from the sections.

        :param sections_descriptions: Section descriptions.
        :type sections_descriptions: dict
        '''

        # Initialize an empty dictionary to store summaries for each section
        summaries = {}
        
        # Loop through each section and its corresponding descriptions
        for i, (section, descriptions) in enumerate(sections_descriptions.items()):
            
            # Concatenate all descriptions of the section into a single text string
            text = ' '.join(descriptions)
            
            # Prepare messages for the LLM (Large Language Model) to generate the summary
            messages = [
                {
                    'role': 'system',
                    'content': self.system_prompt_create_summaries
                },
                {
                    'role': 'user',
                    'content': text
                }
            ]
            
            # Use the OpenAI callback to invoke the LLM and generate the summary
            summary = self.llm.invoke(messages)

            # Create a dictionary entry for the summary with slide number and summary content
            summary_info = {
                'slide_number': f'{self.slide_index_numbers[i]}_sum',
                'description': summary.content
            }

            # Store the summary in the summaries dictionary using the section name as the key
            summaries[section] = summary.content
            
            # Append the summary info to the slides_info list for further use
            self.slides_info.append(summary_info)

            # Generate a filename for saving the summary
            base_filename = os.path.splitext(os.path.basename(self.pptx_path))[0]
            summary_filename = f'summary_{base_filename}_{section}.txt'
            
            # Create the full path for the summary file
            summary_path = os.path.join(self.images_path, summary_filename)
            
            # Write the summary to a text file, including the section name and summary content
            with open(summary_path, 'w', encoding='utf-8') as file:
                file.write(f'Sección: {section}\n')
                file.write(f'{summary.content}\n\n')

    @traceable
    def describe_slide(self, image_base64):
        '''
        Describe the slide by using a computer vision LLM.

        :param image_base64: Image in Base64.
        :type image_base64: string
        '''
        
        # Prepare the message payload for the LLM to describe the image
        messages = [
            {
                'role': 'system',
                'content': self.system_prompt_describe_images['text']  # System prompt guiding how the image should be described
            },
            {
                'role': 'user',
                'content': [{'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{image_base64}'}}]  # Base64 encoded image as input
            }
        ]
        
        # Invoke the LLM (large language model) with the prepared messages to generate the image description
        response = self.llm.invoke(messages)
        
        return response.content


    def process_slides(self):
        '''
        Function to process every image and generate a description. It also can save
        the description.
        '''

        # Loop through each slide's information in the list 'slides_info'
        for slide_info in self.slides_info:
            # Generate a description of the image from its base64 data
            description = self.describe_slide(slide_info['image_base64'])
            slide_info['description'] = description

            # If the 'persist_files' attribute is True, save the description to a text file
            if self.persist_files:
                base_filename = os.path.splitext(slide_info['image_filename'])[0]
                txt_filename = f'{base_filename}.txt'
                txt_path = os.path.join(self.images_path, txt_filename)
                with open(txt_path, 'w', encoding='utf-8') as file:
                    file.write(description)


    def process_presentation(self):
        '''
        Function to do all steps to process all ppt content.
        '''
        if os.name == 'nt':
            self.pptx_to_png_windows()
        elif os.name == 'posix':
            self.pptx_to_png_linux()

        self.process_slides()

        if self.system_prompt_create_summaries:
            sections_descriptions = self.group_descriptions_by_section(self.slides_info, self.slide_index_numbers)
            self.get_section_summaries(sections_descriptions)

    
    def to_langchain_documents(self):
        '''
        Convert all extracted content into Langchain Documents.
        '''

        # Initialize an empty list to store the Langchain Document objects
        documents = []
        
        # Loop through each slide's information in 'slides_info'
        id_sibling = 0
        for slide_info in self.slides_info:
            # Create a metadata dictionary with source information, slide number, and document type
            metadata = {
                'page_number': slide_info['slide_number'],
                'id_sibling': id_sibling
            }
            id_sibling += 1
            # Create a new Langchain Document object using the slide description and metadata
            document = Document(page_content=slide_info['description'], metadata=metadata)
            documents.append(document)
            
        return documents