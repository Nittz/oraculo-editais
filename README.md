# Oráculo de Editais PRO: IA, RAG & Automação de Dados

Este projeto é uma aplicação de Inteligência Artificial e Engenharia de Dados *End-to-End* (de ponta a ponta). Ele automatiza a captação, vetorização e a consulta de editais de concursos públicos, com foco no cenário **Nacional** e no estado de **Minas Gerais**.
O sistema elimina o trabalho manual de leitura de PDFs extensos, transformando documentos complexos num banco de dados inteligente, que pode ser consultado através de linguagem natural.

## Arquitetura "Poor Man's Data Pipeline"

Este projeto utiliza uma arquitetura criativa e de custo zero para operar 100% na nuvem de forma autónoma:

1. **Web Crawler Dinâmico (`cacador_editais.py`):** Um script em Python navega periodicamente pelos portais de concursos, filtra oportunidades e faz o download de PDFs inéditos.
2. **ETL & Vetorização:** O texto dos PDFs é extraído, limpo, dividido em *chunks* e convertido em *Embeddings*, sendo armazenado num **ChromaDB** local (`/banco_vetorial`).
3. **Orquestração via GitHub Actions:** A cada 2 dias, o GitHub acorda o robô, executa o Crawler e guarda as atualizações do banco de dados diretamente no repositório através de *auto-commits*.
4. **Interface Streamlit Cloud (`dashboard_pro.py`):** Um painel analítico hospedado gratuitamente lê a base de dados em tempo real e utiliza a API do **Google Gemini 1.5 Flash** para aplicar a técnica de RAG (*Retrieval-Augmented Generation*).

## Funcionalidades Principais

* **Filtros de Elite:** Procure por palavras-chave (ex: "Câmara", "UFMG", "Engenheiro") e defina pisos salariais para ver apenas oportunidades do seu interesse.
* **Raio-X Proativo (Resumo IA):** O sistema isola um edital de centenas de páginas e extrai automaticamente: Resumo, Vagas, Remuneração, Datas e Requisitos. Possui uma **Trava de Carga** de 60.000 caracteres para evitar o esgotamento de *tokens* em editais massivos.
* **Business Intelligence (BI):** Painel financeiro que compara médias salariais entre vagas Nacionais e de Minas Gerais, gera gráficos de volume e cria um *ranking* exportável em CSV.
* **Oráculo Chat:** Converse com a base de dados inteira em simultâneo. Pergunte *"Quais os concursos abertos com salário acima de 10 mil?"* e a IA irá responder com base nos dados exatos dos PDFs.

## Como executar localmente

Siga os passos abaixo para correr o projeto na sua máquina:

**1. Clone o repositório e aceda à pasta:**
```bash
git clone [https://github.com/SeuUsuario/oraculo-editais.git](https://github.com/SeuUsuario/oraculo-editais.git)
cd oraculo-editais
2. Crie e ative o ambiente virtual:

Bash

python -m venv venv

# Se estiver no Windows:
venv\Scripts\activate

# Se estiver no Linux ou Mac:
source venv/bin/activate
3. Instale as dependências:

Bash

pip install -r requirements.txt
4. Configuração da API Key (Gemini):
Crie uma pasta oculta chamada .streamlit e um ficheiro secrets.toml no seu interior:

Bash

mkdir .streamlit
echo 'GEMINI_API_KEY = "SUA_CHAVE_AQUI"' > .streamlit/secrets.toml
(Nota: Substitua "SUA_CHAVE_AQUI" pela sua chave real gerada no Google AI Studio).

5. Inicie o sistema:

Bash

# Opcional: Execute o robô para popular o banco de dados inicial
python cacador_editais.py

# Inicie o Dashboard Analítico
streamlit run dashboard_pro.py
Implantação e Automação na Nuvem
Este projeto está configurado para o Streamlit Community Cloud.

Segurança de API: A chave do Google Gemini é protegida através da funcionalidade Secrets do Streamlit, impedindo fugas no código público.

Atualização Autónoma: O ficheiro .github/workflows/robo_cacador.yml garante que o projeto procura novos concursos dia sim, dia não (à meia-noite UTC), mantendo a aplicação viva sem necessidade de manutenção diária.

Desenvolvido como projeto de portfólio comprovando o domínio em Python, Automação, Bancos Vetoriais e IAs Generativas.
