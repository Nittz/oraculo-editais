import requests
import pypdf
import chromadb
import os

# 1. O link do PDF que está na internet (Pode ser o edital que você está estudando!)
url_do_pdf = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf" # Exemplo de PDF público
nome_temporario = "edital_baixado.pdf"

print(f"🌐 Baixando o arquivo direto da internet...")

# 2. Fazendo o download invisível
resposta = requests.get(url_do_pdf)
with open(nome_temporario, 'wb') as f:
    f.write(resposta.content)

print(f"✅ Download concluído! Iniciando leitura...")

# 3. Extração
texto_completo = ""
with open(nome_temporario, "rb") as arquivo:
    leitor = pypdf.PdfReader(arquivo)
    for pagina in leitor.pages:
        texto_completo += pagina.extract_text() + "\n"

# 4. Fatiamento e Banco de Dados
pedacos = texto_completo.split("\n\n")
pedacos_limpos = [p.strip() for p in pedacos if len(p.strip()) > 50]

print("🧠 Injetando o novo documento no Banco Vetorial...")
cliente_chroma = chromadb.PersistentClient(path="./banco_vetorial")
colecao = cliente_chroma.get_or_create_collection(name="edital_concurso")

# Gerando IDs únicos (usando um prefixo 'web_' para sabermos que veio da internet)
quantidade_atual = colecao.count()
ids_pedacos = [f"web_{quantidade_atual + i}" for i in range(len(pedacos_limpos))]

colecao.add(documents=pedacos_limpos, ids=ids_pedacos)

# 5. Limpeza: Apaga o PDF temporário do seu computador para não ocupar espaço
os.remove(nome_temporario)

print("🎉 SUCESSO! Edital da internet foi lido, vetorizado e o arquivo foi apagado da sua máquina.")