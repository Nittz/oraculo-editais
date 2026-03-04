import streamlit as st
import chromadb
import google.generativeai as genai

# 1. CONFIGURAÇÃO DA CHAVE DO GOOGLE GEMINI
CHAVE_GEMINI = "AIzaSyAsLlVdzYit8jwlDPcROKQnya0mV7cU7B0"
genai.configure(api_key=CHAVE_GEMINI)

# 2. SELEÇÃO DINÂMICA DE MODELO (À Prova de Falhas 404)
@st.cache_resource
def carregar_motor_ia():
    # Pede ao Google a lista de modelos que sua chave tem permissão para usar
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            # Pega o primeiro modelo válido (ex: gemini-1.0-pro ou gemini-1.5-flash)
            nome_limpo = m.name.replace("models/", "")
            return genai.GenerativeModel(nome_limpo)
    # Fallback de segurança
    return genai.GenerativeModel('gemini-1.5-flash')

modelo = carregar_motor_ia()

# 3. CONFIGURAÇÃO DA INTERFACE VISUAL
st.set_page_config(page_title="Oráculo de Editais", page_icon="🏛️", layout="centered")
st.title("🏛️ Oráculo de Editais (Gemini Version)")
st.markdown(f"Assistente conectado à inteligência do Google na nuvem.")

# 4. CONEXÃO COM O BANCO DE DADOS VETORIAL LOCAL
@st.cache_resource 
def carregar_banco():
    cliente = chromadb.PersistentClient(path="./banco_vetorial")
    return cliente.get_collection(name="edital_concurso")

colecao = carregar_banco()

# 5. LÓGICA DE CHAT E BUSCA (RAG)
pergunta = st.chat_input("Digite sua dúvida sobre o edital...")

if pergunta:
    # Mostra a pergunta do usuário na tela
    st.chat_message("user").write(pergunta)
    
    with st.spinner("Consultando o banco e processando com o Gemini..."):
        
        # Busca os 3 trechos mais relevantes no ChromaDB
        resultados = colecao.query(
            query_texts=[pergunta],
            n_results=3
        )
        contexto_encontrado = "\n\n".join(resultados['documents'][0])
        
        # Trava de segurança (Prompt System)
        prompt_sistema = f"""
        Você é um assistente focado em concursos públicos.
        Responda à pergunta do usuário usando APENAS as informações abaixo.
        Se a resposta não estiver no texto abaixo, diga 'Não encontrei essa informação no documento'.
        Não invente dados.
        
        TEXTO DE REFERÊNCIA:
        {contexto_encontrado}
        
        PERGUNTA DO USUÁRIO:
        {pergunta}
        """
        
        try:
            # Envia a requisição para a nuvem
            resposta_ia = modelo.generate_content(prompt_sistema)
            # Exibe a resposta final na tela
            st.chat_message("assistant").write(resposta_ia.text)
        except Exception as e:
            st.error(f"Erro ao conectar com a nuvem: {e}")