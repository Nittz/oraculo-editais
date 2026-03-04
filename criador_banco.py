import pypdf
import chromadb

nome_arquivo = "documento_teste.pdf"
print(f"📚 Lendo todas as páginas do {nome_arquivo}...")

# 1. Extração do texto de TODAS as páginas
texto_completo = ""
with open(nome_arquivo, "rb") as arquivo:
    leitor = pypdf.PdfReader(arquivo)
    for pagina in leitor.pages:
        texto_completo += pagina.extract_text() + "\n"

print(f"✅ Texto extraído! Total de caracteres: {len(texto_completo)}")

# 2. Fatiamento (Chunking)
# Cortamos o edital a cada quebra de linha dupla (parágrafos)
pedacos = texto_completo.split("\n\n")
pedacos_limpos = [p.strip() for p in pedacos if len(p.strip()) > 50]

print(f"🔪 O edital foi perfeitamente fatiado em {len(pedacos_limpos)} pedaços.")

# 3. Criando o Banco de Dados Vetorial Local (ChromaDB)
print("🧠 Iniciando o motor do Banco Vetorial...")
# Isso cria uma pasta real no seu computador para guardar os dados
cliente_chroma = chromadb.PersistentClient(path="./banco_vetorial")

# Cria uma "gaveta" (coleção) específica chamada 'edital_concurso'
colecao = cliente_chroma.get_or_create_collection(name="edital_concurso")

# 4. Vetorização e Carga
print("⏳ Transformando texto em matemática e salvando (pode levar um minutinho)...")
ids_pedacos = [f"pedaco_{i}" for i in range(len(pedacos_limpos))]

# Chroma vai embutir os textos
colecao.add(
    documents=pedacos_limpos,
    ids=ids_pedacos
)

print("🎉 SUCESSO! Banco de Dados Vetorial criado e populado com o edital.")