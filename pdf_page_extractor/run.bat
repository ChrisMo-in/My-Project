@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt
py pdf_page_extractor.py
pause
