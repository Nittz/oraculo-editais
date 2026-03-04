import chromadb
import ollama

# 1. Conectando ao banco de dados que criamos no passo anterior
cliente_chroma = chromadb.PersistentClient(path="./banco_vetorial")
colecao = cliente_chroma.get_collection(name="edital_concurso")

# 2. A sua pergunta (Pode mudar para o que quiser saber do edital!)
# 2. A sua pergunta agora é digitada direto no terminal!
pergunta = input("💬 Digite sua pergunta sobre o edital: ")

print(f"👤 Pergunta: {pergunta}")
print("🔍 Vasculhando as páginas do edital no Banco Vetorial...\n")

# 3. Busca Semântica
# O banco vai trazer os 3 parágrafos do edital que mais combinam com a pergunta
resultados = colecao.query(
    query_texts=[pergunta],
    n_results=3
)

# Juntamos os 3 parágrafos encontrados em um texto só
contexto_encontrado = "\n".join(resultados['documents'][0])

# 4. A Regra de Ouro da IA (Prompt de Sistema)
# É aqui que "travamos" a IA para ela não alucinar e não inventar regras falsas
prompt_sistema = f"""
Você é um assistente jurídico especialista em editais de concursos públicos.
Responda à pergunta do usuário usando APENAS as informações contidas no contexto abaixo.
Se a resposta não estiver no contexto, diga cordialmente que não encontrou a informação no trecho lido.
Seja claro, direto e profissional.

CONTEXTO EXTRAÍDO DO EDITAL:
{contexto_encontrado}
"""

print("🧠 Llama 3 está lendo as regras e formulando a resposta...\n")

# 5. Enviamos tudo para o modelo local rodando na sua máquina
resposta = ollama.chat(model='llama3', messages=[
  {'role': 'system', 'content': prompt_sistema},
  {'role': 'user', 'content': pergunta}
])

print("🤖 Resposta do Oráculo:")
print("-" * 60)
print(resposta['message']['content'])
print("-" * 60)