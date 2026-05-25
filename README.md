# Cap-parser
## Project Overview
The Cap-parser project is designed to extract transactions from bank statement PDFs, supporting multiple banks and providing a flexible parsing mechanism.
## Key Features
* Supports parsing of PDFs from tymebank, capitec, and other banks
* Extracts transactions and returns them as a list of dictionaries
* Uses pdfplumber and PyPDF2 libraries for PDF text extraction
* Handles password-protected PDFs
## Tech Stack
* Python 3.x
* pdfplumber
* PyPDF2
* logging
## Installation
To install the required libraries, run the following command:
```bash
pip install pdfplumber PyPDF2
```
## Usage
To use the Cap-parser, create an instance of the `PDFParser` class and call the `parse_pdf` method, passing in the PDF data, bank name, and optional password:
```python
from parsers import PDFParser

pdf_data = b'...'  # binary PDF data
bank_name = 'tymebank'
password = 'optional_password'

parser = PDFParser()
transactions = parser.parse_pdf(pdf_data, bank_name, password)
```
## Environment Variables
No specific environment variables are required for this project. However, you may want to set the `LOG_LEVEL` environment variable to control the logging level:
```bash
export LOG_LEVEL=DEBUG
```
This will set the logging level to DEBUG, allowing you to see more detailed log messages.