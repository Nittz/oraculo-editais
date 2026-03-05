import streamlit as st
import chromadb
import google.generativeai as genai
import pandas as pd
import os

# Definicao de caminhos absolutos para persistencia de dados
DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
CAMINHO_BANCO = os.path.join(DIRETORIO_ATUAL, "banco_vetorial")

st.set_page_config(page_title="Oráculo Editais PRO", page_icon="📊", layout="wide")

# CARREGAMENTO SEGURO DA API KEY (Evita vazamentos no GitHub)
try:
    CHAVE_GEMINI = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=CHAVE_GEMINI)
except KeyError:
    st.error("⚠️ Chave da API não configurada. Por favor, adicione 'GEMINI_API_KEY' nos Secrets do Streamlit Cloud.")
    st.stop()

@st.cache_resource
def carregar_motor_ia():
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            nome_limpo = m.name.replace("models/", "")
            return genai.GenerativeModel(nome_limpo)
    return genai.GenerativeModel('gemini-1.5-flash')

modelo = carregar_motor_ia()

@st.cache_resource 
def carregar_banco():
    cliente = chromadb.PersistentClient(path=CAMINHO_BANCO)
    return cliente.get_or_create_collection(name="editais_brasil_mg_v2")

colecao = carregar_banco()

dados_banco = colecao.get()
total_chunks = len(dados_banco['ids']) if dados_banco['ids'] else 0

# Processamento e separacao de dados brutos
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

# Inicializacao da Interface Visual (Sidebar)
with st.sidebar:
    st.title("⚙️ Painel de Controle")
    st.markdown("Monitoramento do Banco Vetorial e Status da IA.")
    
    st.divider()
    
    # 1. FILTRO DE ELITE E PALAVRA-CHAVE
    st.markdown("### 🎯 Filtros de Elite")
    st.caption("Filtre as oportunidades pelo seu nível de interesse:")
    
    busca_texto = st.text_input("🔍 Buscar Órgão/Cargo (ex: Câmara, UFMG):", "").strip().lower()
    filtro_salario = st.slider("💰 Salário Mínimo Exigido:", min_value=0, max_value=30000, value=0, step=1000, format="R$ %d")
    
    # Aplicar os filtros combinados (Salário + Busca)
    editais_mg = {k: v for k, v in editais_mg_brutos.items() if v >= filtro_salario and (busca_texto in k.lower() if busca_texto else True)}
    editais_nacional = {k: v for k, v in editais_nacional_brutos.items() if v >= filtro_salario and (busca_texto in k.lower() if busca_texto else True)}
    
    st.divider()
    
    st.markdown(f"### 📚 Editais em Aberto ({len(editais_nacional) + len(editais_mg)})")
    
    st.markdown("**Concursos Nacionais / Federais:**")
    if editais_nacional:
        for titulo, sal in editais_nacional.items():
            if sal > 0:
                st.info(f"🇧🇷 {titulo}\n\n*(Até R$ {sal:,.2f})*")
            else:
                st.info(f"🇧🇷 {titulo}")
    else:
        st.caption("Nenhum edital nacional atende aos filtros.")
        
    st.write("") 
    
    st.markdown("**Concursos em Minas Gerais:**")
    if editais_mg:
        for titulo, sal in editais_mg.items():
            if sal > 0:
                st.success(f"🔺 {titulo}\n\n*(Até R$ {sal:,.2f})*")
            else:
                st.success(f"🔺 {titulo}")
    else:
        st.caption("Nenhum edital de MG atende aos filtros.")

# Renderizacao do Dashboard Principal
st.title("📊 Centro de Inteligência RAG (Visão de Mercado)")
st.markdown("Dashboard analítico unificando Editais **Nacionais** e de **Minas Gerais**, com extração inteligente de salários em tempo real.")

# Inicializacao das 3 abas da aplicacao
aba_raiox, aba_analytics, aba_chat = st.tabs(["🔍 Raio-X do Edital", "📈 Business Intelligence (BI)", "💬 Oráculo (Chat Livre)"])

with aba_raiox:
    st.markdown("### 🤖 Extração Proativa de Dados")
    st.write("Selecione um edital da base de dados. A IA irá ler o documento isoladamente e gerar um resumo estruturado e focado no que interessa.")
    
    # Consolida os titulos FILTRADOS para o menu suspenso
    todos_titulos = sorted(list(editais_nacional.keys()) + list(editais_mg.keys()))
    
    if todos_titulos:
        col_selecao, col_botao = st.columns([3, 1])
        
        with col_selecao:
            edital_alvo = st.selectbox("Selecione o Concurso:", todos_titulos)
            
        with col_botao:
            st.write("") 
            st.write("")
            gerar = st.button("Gerar Raio-X Completo", type="primary", use_container_width=True)
            
        if gerar:
            with st.spinner(f"A analisar o edital: {edital_alvo}..."):
                dados_isolados = colecao.get(where={"titulo": edital_alvo})
                
                if dados_isolados and dados_isolados['documents']:
                    texto_completo_edital = "\n\n".join(dados_isolados['documents'])
                    
                    # --- PREVENÇÃO DO ERRO 429 (QUOTA EXCEEDED) ---
                    # Limitar o tamanho do payload enviado para a API da Google.
                    # 60.000 caracteres garante que capturamos as regras principais
                    # sem sobrecarregar a cota gratuita com PDFs de 200 páginas.
                    LIMITE_CARACTERES = 60000
                    if len(texto_completo_edital) > LIMITE_CARACTERES:
                        texto_completo_edital = texto_completo_edital[:LIMITE_CARACTERES] + "\n\n[AVISO TÉCNICO: O documento original é demasiado extenso. O texto foi truncado para respeitar os limites da API. As regras principais foram preservadas.]"
                    
                    prompt_raiox = f"""
                    Aja como um Analista de Concursos Público Sênior, objetivo e proativo.
                    Faça um "Raio-X" do edital fornecido, extraindo as informações vitais de forma direta.
                    
                    Regra: Se não encontrar a informação, escreva explicitamente "Não especificado no documento". Não invente dados.
                    
                    Estrutura de saída obrigatória (use Markdown):
                    ### 🎯 Resumo da Oportunidade
                    [Breve descrição do órgão e objetivo do concurso]
                    
                    ### 💼 Cargos e Vagas Principais
                    [Lista com bullet points dos principais cargos e quantidade de vagas]
                    
                    ### 💰 Remuneração e Benefícios
                    [Detalhes de salários e benefícios encontrados]
                    
                    ### 📅 Datas Importantes
                    [Período de inscrição, data da prova, etc.]
                    
                    ### 🎓 Requisitos de Escolaridade
                    [Níveis exigidos: Médio, Técnico, Superior, etc.]
                    
                    ---
                    TEXTO DO EDITAL:
                    {texto_completo_edital}
                    """
                    
                    try:
                        resposta = modelo.generate_content(prompt_raiox)
                        st.success("Análise concluída com sucesso!")
                        
                        url_busca_inteligente = f"https://www.google.com/search?q=Concurso+{edital_alvo.replace(' ', '+')}+Inscrição"
                        st.link_button("🔗 Abrir Página de Inscrição (Pesquisa Web)", url_busca_inteligente, type="secondary")
                        
                        with st.container(border=True):
                            st.markdown(resposta.text)
                            
                    except Exception as e:
                        st.error(f"Erro na comunicação com a API de Inteligência Artificial: {e}")
                else:
                    st.warning("Não foi possível carregar o texto deste edital. O PDF pode ter sido corrompido durante o download.")
    else:
        st.info("Nenhum edital atende aos critérios atuais do filtro.")

with aba_analytics:
    sals_mg = [s for s in editais_mg.values() if s > 0]
    sals_nac = [s for s in editais_nacional.values() if s > 0]
    
    media_mg = sum(sals_mg) / len(sals_mg) if sals_mg else 0
    media_nac = sum(sals_nac) / len(sals_nac) if sals_nac else 0
    diferenca = media_nac - media_mg
    
    st.markdown("### 💰 Análise Financeira (Média Salarial Oferecida)")
    col_s1, col_s2, col_s3 = st.columns(3)
    
    txt_nac = f"R$ {media_nac:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    txt_mg = f"R$ {media_mg:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    col_s1.metric("Média Nacional", txt_nac)
    col_s2.metric("Média Minas Gerais", txt_mg)
    
    if diferenca > 0:
        texto_dif = f"+ R$ {diferenca:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        col_s3.metric("Diferença", texto_dif, "Nacional paga mais")
    elif diferenca < 0:
        texto_dif = f"- R$ {abs(diferenca):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        col_s3.metric("Diferença", texto_dif, "MG paga mais", delta_color="inverse")
    else:
        col_s3.metric("Diferença", "R$ 0,00", "Equivalente")
        
    st.divider()
    
    col_graf1, col_graf2 = st.columns(2)
    
    with col_graf1:
        st.markdown("### 🗺️ Volume por Região (Filtrado)")
        dados_grafico_regiao = pd.DataFrame({
            'Região': ['Nacionais (BR)', 'Minas Gerais (MG)'],
            'Quantidade': [len(editais_nacional), len(editais_mg)]
        })
        st.bar_chart(dados_grafico_regiao.set_index('Região'), color="#3b82f6")
        
    with col_graf2:
        st.markdown("### 🏆 Top Maiores Salários")
        todos_filtrados = {**editais_nacional, **editais_mg}
        ranking_real = {k: v for k, v in todos_filtrados.items() if v > 0}
        
        if ranking_real:
            df_ranking_completo = pd.DataFrame(list(ranking_real.items()), columns=['Concurso', 'Salário Máx.'])
            df_ranking_completo = df_ranking_completo.sort_values(by='Salário Máx.', ascending=False)
            
            df_visual = df_ranking_completo.head(5).copy()
            df_visual['Salário Máx.'] = df_visual['Salário Máx.'].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            st.dataframe(df_visual, use_container_width=True, hide_index=True)
            
            csv_data = df_ranking_completo.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Baixar Ranking Completo (CSV)",
                data=csv_data,
                file_name="ranking_concursos.csv",
                mime="text/csv",
                help="Faça o download da tabela completa baseada nos filtros aplicados."
            )
        else:
            st.info("Nenhum salário capturado nos editais que passaram pelo filtro.")

with aba_chat:
    st.markdown("### 💬 Consulta Livre à Base de Dados Inteira")
    st.write("Faça perguntas gerais e a IA procurará respostas em **todos** os editais disponíveis em simultâneo.")
    
    pergunta = st.chat_input("Ex: Existe alguma vaga para Engenheiro Civil em Minas Gerais?")
    if pergunta:
        st.chat_message("user").write(pergunta)
        with st.spinner("A analisar os vetores na base de dados..."):
            if colecao.count() > 0:
                resultados = colecao.query(query_texts=[pergunta], n_results=5) 
                if resultados and resultados['documents'] and len(resultados['documents'][0]) > 0:
                    contexto_encontrado = "\n\n".join(resultados['documents'][0])
                    prompt_sistema = f"""
                    Você é um assistente focado em concursos públicos.
                    Responda à pergunta do usuário usando APENAS as informações abaixo.
                    Se a resposta não estiver no texto abaixo, diga 'Não encontrei essa informação no documento'.
                    
                    TEXTO DE REFERÊNCIA (Trechos extraídos do banco de dados):
                    {contexto_encontrado}
                    
                    PERGUNTA DO USUÁRIO:
                    {pergunta}
                    """
                    try:
                        resposta_ia = modelo.generate_content(prompt_sistema)
                        st.chat_message("assistant").write(resposta_ia.text)
                        with st.expander("🔍 Ver trechos da base de dados utilizados"):
                            st.info(contexto_encontrado)
                    except Exception as e:
                        st.error(f"Erro ao conectar com a nuvem: {e}")
            else:
                st.warning("O banco de dados ainda está vazio.")