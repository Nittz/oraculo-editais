import streamlit as st
import chromadb
import google.generativeai as genai
import pandas as pd
import os

# Definição de caminhos absolutos para persistência de dados
DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
CAMINHO_BANCO = os.path.join(DIRETORIO_ATUAL, "banco_vetorial")

st.set_page_config(page_title="Oráculo Editais PRO", page_icon="📊", layout="wide")

# CARREGAMENTO SEGURO E LIMPO DA API KEY
def configurar_ia():
    try:
        # O .strip() remove espaços ou quebras de linha acidentais
        chave = st.secrets["GEMINI_API_KEY"].strip()
        if not chave or chave == "cole-aqui":
            st.error("⚠️ A chave configurada nos Secrets parece estar vazia ou é o texto de exemplo.")
            st.stop()
        genai.configure(api_key=chave)
        return True
    except KeyError:
        st.error("⚠️ Chave 'GEMINI_API_KEY' não encontrada nos Secrets do Streamlit.")
        st.info("Aceda a 'Settings' -> 'Secrets' e adicione: GEMINI_API_KEY = 'sua-chave'")
        st.stop()
    except Exception as e:
        st.error(f"⚠️ Erro ao configurar API: {e}")
        st.stop()

configurar_ia()

@st.cache_resource
def carregar_motor_ia():
    try:
        # Tenta encontrar um modelo disponível (preferência pelo flash)
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'gemini-1.5-flash' in m.name:
                    return genai.GenerativeModel('gemini-1.5-flash')
        return genai.GenerativeModel('gemini-pro')
    except Exception as e:
        st.error(f"Erro ao listar modelos: {e}. Verifique se a sua chave é válida.")
        st.stop()

modelo = carregar_motor_ia()

@st.cache_resource 
def carregar_banco():
    cliente = chromadb.PersistentClient(path=CAMINHO_BANCO)
    return cliente.get_or_create_collection(name="editais_brasil_mg_v2")

colecao = carregar_banco()

# --- Recuperação de Dados ---
dados_banco = colecao.get()
total_chunks = len(dados_banco['ids']) if dados_banco['ids'] else 0

editais_mg_brutos = {}
editais_nacional_brutos = {}

if dados_banco['metadatas']:
    for meta in dados_banco['metadatas']:
        if meta and 'titulo' in meta and 'abrangencia' in meta:
            titulo_limpo = meta['titulo'].title()
            salario = meta.get('salario', 0.0)
            
            if meta['abrangencia'] == 'Minas Gerais':
                editais_mg_brutos[titulo_limpo] = salario
            else:
                editais_nacional_brutos[titulo_limpo] = salario

# --- Interface Visual (Sidebar) ---
with st.sidebar:
    st.title("⚙️ Painel de Controle")
    st.markdown("Status da Base de Dados e IA.")
    
    st.divider()
    
    st.markdown("### 🎯 Filtros de Elite")
    busca_texto = st.text_input("🔍 Buscar Órgão/Cargo:", "").strip().lower()
    filtro_salario = st.slider("💰 Salário Mínimo:", 0, 30000, 0, 1000, "R$ %d")
    
    editais_mg = {k: v for k, v in editais_mg_brutos.items() if v >= filtro_salario and (busca_texto in k.lower() if busca_texto else True)}
    editais_nacional = {k: v for k, v in editais_nacional_brutos.items() if v >= filtro_salario and (busca_texto in k.lower() if busca_texto else True)}
    
    st.divider()
    st.markdown(f"### 📚 Editais Filtrados ({len(editais_nacional) + len(editais_mg)})")
    
    if editais_nacional:
        for t, s in editais_nacional.items():
            st.info(f"🇧🇷 {t}" + (f"\n*(R$ {s:,.2f})*" if s > 0 else ""))
    
    if editais_mg:
        for t, s in editais_mg.items():
            st.success(f"🔺 {t}" + (f"\n*(R$ {s:,.2f})*" if s > 0 else ""))

# --- Dashboard Principal ---
st.title("📊 Centro de Inteligência RAG")
aba_raiox, aba_analytics, aba_chat = st.tabs(["🔍 Raio-X do Edital", "📈 Analytics", "💬 Oráculo Chat"])

with aba_raiox:
    st.markdown("### 🤖 Extração Proativa")
    todos_titulos = sorted(list(editais_nacional.keys()) + list(editais_mg.keys()))
    
    if todos_titulos:
        col_sel, col_btn = st.columns([3, 1])
        with col_sel:
            edital_alvo = st.selectbox("Selecione o Concurso:", todos_titulos)
        with col_btn:
            st.write("")
            st.write("")
            gerar = st.button("Gerar Raio-X Completo", type="primary", use_container_width=True)
            
        if gerar:
            with st.spinner(f"A analisar: {edital_alvo}..."):
                dados = colecao.get(where={"titulo": edital_alvo})
                if dados and dados['documents']:
                    texto = "\n\n".join(dados['documents'])
                    if len(texto) > 60000:
                        texto = texto[:60000] + "\n\n[Texto truncado para limites da API]"
                    
                    prompt = f"Faça um Raio-X objetivo deste edital, focando em Cargos, Vagas, Salários, Datas e Requisitos:\n\n{texto}"
                    
                    try:
                        res = modelo.generate_content(prompt)
                        st.success("Análise concluída!")
                        url = f"https://www.google.com/search?q=Concurso+{edital_alvo.replace(' ', '+')}+Inscrição"
                        st.link_button("🔗 Ver Página Oficial", url)
                        st.markdown(res.text)
                    except Exception as e:
                        st.error(f"Erro na IA: {e}")
                else:
                    st.warning("Conteúdo do edital não encontrado no banco.")
    else:
        st.info("Nenhum edital na base de dados.")

with aba_analytics:
    st.write("Estatísticas financeiras e de volume de dados.")
    # Implementação simplificada para foco no debug da IA
    st.metric("Total de Chunks no Banco", total_chunks)

with aba_chat:
    st.write("Chat interativo com a base de dados.")
    pergunta = st.chat_input("Faça uma pergunta...")
    if pergunta:
        st.chat_message("user").write(pergunta)
        if colecao.count() > 0:
            res_vetor = colecao.query(query_texts=[pergunta], n_results=3)
            contexto = "\n".join(res_vetor['documents'][0])
            try:
                res_ia = modelo.generate_content(f"Contexto: {contexto}\n\nPergunta: {pergunta}")
                st.chat_message("assistant").write(res_ia.text)
            except Exception as e:
                st.error(f"Erro no Chat: {e}")