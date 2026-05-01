.PHONY: install crawl app clean help

help:
	@echo "Comandos disponiveis:"
	@echo "  make install   - Instala dependencias do requirements.txt"
	@echo "  make crawl     - Executa o crawler e popula o banco vetorial"
	@echo "  make app       - Sobe o dashboard Streamlit em localhost:8501"
	@echo "  make clean     - Remove caches Python (__pycache__, *.pyc)"

install:
	pip install -r requirements.txt

crawl:
	python src/oraculo/crawler.py

app:
	streamlit run app/dashboard.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
