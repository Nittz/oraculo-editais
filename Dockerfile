# Imagem para deploy do dashboard (Hugging Face Spaces, Render, Fly.io, etc.)
FROM python:3.10-slim

# Instala dependencias primeiro para aproveitar cache
WORKDIR /code
COPY requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# HF Spaces exige usuario nao-root
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app
COPY --chown=user . $HOME/app

# HF Spaces espera porta 7860 por padrao
EXPOSE 7860

CMD ["streamlit", "run", "app/dashboard.py", \
     "--server.port=7860", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
