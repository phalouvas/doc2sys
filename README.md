## Doc2Sys

A document automation software that extracts data from various files (images, PDFs etc), validates them, and integrates them into accounting systems, deployable both in the cloud and on-premises. Uses machine learning and NLP for intelligent document classification and data extraction.

#### License

gpl-3.0

## Installation
### System Dependencies

#### Install "poppler-utils" on OS
* Update apt with command: `sudo apt update`

* install pdftotext on Ubuntu, you can use the following command in the terminal:
`sudo apt install poppler-utils`
This will install the poppler-utils package which includes pdftotext

#### Installation of OCR input modules
A tesseract wrapper is included in auto language mode. It will test your input files against the languages installed on your system. To use it tesseract and imagemagick needs to be installed. tesseract supports multiple OCR engine modes. By default the available engine installed on the system will be used.

Languages: tesseract-ocr recognize more than 100 languages For Linux users, you can often find packages that provide language packs:

**Display a list of all Tesseract language packs**
`sudo apt-cache search tesseract-ocr`

**Debian/Ubuntu users**
`sudo apt-get install tesseract-ocr tesseract-ocr-eng tesseract-ocr-ell`  # Example: Install Greek and English language pack

**Arch Linux users**
`pacman -S tesseract-data-eng tesseract-data-deu` # Example: Install the English and German language packs

#### Installation of OCR Language Packs
For better OCR results with multiple languages, you need to install the appropriate language packs:

**Debian/Ubuntu users**
```bash
# List available language packs
sudo apt-cache search tesseract-ocr-

# Install specific language packs
sudo apt-get install tesseract-ocr-ell  # Greek
sudo apt-get install tesseract-ocr-deu  # German
sudo apt-get install tesseract-ocr-fra  # French
# etc.
```

**After installation**
Configure the languages in the Doc2Sys Settings page in ERPNext.

### Install "Doc2Sys" app on ErpNext
* `bench get-app --branch=master doc2sys https://github.com/phalouvas/doc2sys.git`
* `bench --site yoursite install-app doc2sys`

### Python Dependencies
The following Python dependencies will be installed automatically:
* python-docx - For processing Microsoft Word documents
* pdf2image - For converting PDF pages to images for OCR processing
