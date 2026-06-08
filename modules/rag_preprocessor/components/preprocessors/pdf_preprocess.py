"""
This module extracts the text from the pdf.
"""

# Import libraries
import fitz
import re
from difflib import SequenceMatcher
import logging
import nltk
import os
nltk.download('punkt_tab')

class PDFProcessor:
    '''
    Extract Relevant Sections class.
    '''

    def __init__(self, pdf_path, output_check_path, now, monitorize):
        '''
        Initializes the class with the provided parameters.

        :param pdf_path: The path to the PDF file to be processed.
        :type pdf_path: str
        :param output_check_path: The path where the output check file will be stored.
        :type output_check_path: str
        :param now: The current timestamp or datetime object.
        :type now: datetime or str
        :param monitorize: A flag indicating whether to enable monitoring.
        :type monitorize: bool
        '''
        
        self.pdf_path = pdf_path
        self.output_check_path = output_check_path
        self.now = now
        self.monitorize = monitorize

    def pdf_to_text(self):
        '''
        Function to convert a PDF to text.
        '''

        text = ''
        pdf_fitz = fitz.open(self.pdf_path)

        # Extract all text from the PDF
        for page_num in range(pdf_fitz.page_count):
            page = pdf_fitz.load_page(page_num)
            page_text = page.get_text('text')

            lines = page_text.splitlines()
            #add corresponding page to the end of each line
            for line in lines:
                text += line + f' pg:{page_num + 1}\n'

        pdf_fitz.close()

        with open(f'{self.output_check_path}/output_{os.path.basename(self.pdf_path)}_{self.now}.txt', 'w', encoding='utf-8') as file:
            # Write the content of 'text' to the file
            file.write(text)

        return text

    def extract_sections_from_pdf(self, regexp_section):
        '''
        Extracts sections from a PDF document based on a given regular expression pattern.
        This function processes the text extracted from a PDF file, applies filters to remove unwanted content, 
        and identifies sections based on a provided regular expression pattern. It further splits large sections 
        into smaller chunks, cleans up page numbers, and organizes the extracted sections with relevant metadata.
        
        :param regexp_section: A dictionary containing regular expressions for filtering text and identifying sections.
                               Keys include 'regexp_delete_text' (list of patterns to remove unwanted text) and 
                               'regexp_sections_filter' (pattern to identify section titles).
        :type regexp_section: dict
        '''
        ''

        text = self.pdf_to_text()
        filename = os.path.basename(self.pdf_path)
        # Filters
        # Delete parts of the text we do not want
        for reg in regexp_section['regexp_delete_text']:
            text = re.sub(rf'{reg}', '', text)
        # with open(f'{output_check_path}/output_test.txt', 'w', encoding='utf-8') as file:
        #     # Write the content of 'text' to the file
        #     file.write(text)

        # Split the text into lines
        lines = text.split('\n')
        # List to store extracted sections
        sections = []
        current_section = []

        # Improved regular expression to detect a potential section title:
        # - Starts at the beginning of the line
        # - Contains numbers separated by dots or uppercase letters followed by a dot
        # - Must have meaningful text after the numbers or letter

        section_pattern = re.compile(
            regexp_section['regexp_sections_filter']
        )

        # Iterate over each line
        for line in lines:
            # If the line matches the section title pattern
            if section_pattern.match(line.replace('%', '')) and current_section:
                # Save the current section and start a new one
                sections.append('\n'.join(current_section))
                current_section = [line]
            else:
                current_section.append(line)
        # Append the last section if not empty
        if current_section:
            sections.append('\n'.join(current_section))

        sections_with_info = []
        for section in sections:
            #store title of the section, cleaning the pg
            title = self.extract_section_title(section)
            title = re.sub(r'pg:\d+', '', title)

            #split the larger sections into smaller ones
            section_chunks = self.split_text(section)
            for sec in section_chunks:
                #store and erase all the page numbers from each section
                page_numbers = [int(num) for num in re.findall(r'pg:(\d+)', sec)]
                unique_page_numbers = set(page_numbers)
                sec_cleaned = re.sub(r'pg:\d+', '', sec)
                #specify the relevant information from each section
                if sec_cleaned != '':
                    section_aux = {'content': sec_cleaned, 'filename': filename, 'section_name': title, 'pages': unique_page_numbers}
                    sections_with_info.append(section_aux)

        # Create a txt file with sections for all the documents to monitor if they are well extracted
        if self.monitorize:
            self.monitoring_chunking(sections_with_info, filename, self.now)
        
        return sections_with_info

    def split_text(self, section, max_length = 7000):
        '''
        Function to split text if the section length is longer than max_length.

        :param section: The section text.
        :type section: string
        :param max_length: The max length to set the threshold in characters.
        :type max_length: integer
        '''
        if len(section) > max_length:
            # Tokenize the text into sentences using NLTK's sentence tokenizer.
            sentences = nltk.sent_tokenize(section)

            chunks = []
            current_chunk = ''
            
            # Loop through each sentence.
            for sentence in sentences:
                # Check if adding the next sentence would keep the chunk under the max length.
                if len(current_chunk) + len(sentence) <= max_length:
                    # If yes, add the sentence to the current chunk.
                    current_chunk += ' ' + sentence
                else:
                    # If the chunk is too long, save the current chunk and start a new one.
                    chunks.append(current_chunk.strip())
                    current_chunk = sentence
            
            # After the loop, check if there's any remaining text in the current chunk.
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            return chunks

        else:
            return [section]
    
    def extract_section_title(self, section):
        '''
        Function to extract the section title.

        :param section: The section text.
        :type section: string
        '''
        
        # If the section has a type of 6.2\nSection Name, then the two first lines are joined.
        # In other cases, only first line is considered. This is detected by checking if there is
        # only numbers in the first line
        lines = section.split('\n', 2)
        first_line = lines[0].strip()
        if not any(char.isalpha() for char in re.sub(r'pg:\d+', '', first_line)) and len(lines) > 1:
            first_line = re.sub(r'pg:\d+', '', first_line).strip() + " " + lines[1].strip()
        return first_line


    def similar(self, a, b):
        '''
        Function to calculate similarity between two strings.

        :param a: String A.
        :type a: string
        :param b: String B.
        :type b: string.
        '''

        return SequenceMatcher(None, a, b).ratio()

    def filter_sections_by_keywords(self, sections_with_info, keyword_sets, threshold = 0.8):
        '''
        Function to filter the sections by keywords.

        :param sections_with_info: The list of sections with the metadata added.
        :type sections_with_info: dict
        :param keyword_sets: The keywords to use in the filters.
        :type keyword_sets: list[list]
        :param threshold: Similarity threshold to find matchs in the texts.
        :type threshold: float
        '''

        filtered_sections = []
        for sec in sections_with_info:
            title = sec['section_name']
            for keywords in keyword_sets:
                # Create regular expression based on the keywords
                pattern = r'(?=.*' + r')(?=.*'.join(re.escape(kw) for kw in keywords) + r')'
                if re.search(pattern, title, re.IGNORECASE):
                    filtered_sections.append(sec)
                    break
                # If the regex does not find any match, use similarity
                elif any(self.similar(title.lower(), kw.lower()) >= threshold for kw in keywords):
                    filtered_sections.append(sec)
                    break
                    
        return filtered_sections
    
    def monitoring_chunking(self, sections_with_info, filename, now):
        '''
        Function to create a txt file to monitor the chunks extracted.

        :param sections_with_info: The sections dict with the metadata.
        :type sections_with_info: dict
        :param filename: The filename is being analyzed currently.
        :type filename: string
        :param now: The current datetime.
        :type now: datetime
        '''
        
        # Create sep between sections
        sep = '\n' + '#' * 100 + '\n'

        # Write the txt with every section
        with open(f'{self.output_check_path}/monitoring_chunking_{now}.txt', 'a', encoding = 'utf-8') as f:
            f.write(f'FILENAME: {filename}\n\n')
            for s in sections_with_info:
                title = s.get('section_name', 'No title')
                content = s.get('content', '')

                f.write(f'SECTION: {title}\n')
                f.write(f'CONTENT: {content}\n')
                f.write(sep)


   