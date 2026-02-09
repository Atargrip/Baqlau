import os
from pypdf import PdfReader


def pdf_file_table_extractor():
    reader = PdfReader("C:/Users/Aset/Desktop/gold_statement.pdf")
    for i in range(len(reader.pages)):
        page = reader.pages[i]
        extracted_text = page.extract_text().split("\n")
        for j in range(len(extracted_text)):
            print(extracted_text[j])


pdf_file_table_extractor()
