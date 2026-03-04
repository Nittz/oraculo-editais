import requests
from bs4 import BeautifulSoup
import pypdf
import chromadb
import os
from urllib.parse import urljoin
import time
import re

# Configuração de diretório absoluto para o banco vetorial
DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
CAMINHO_BANCO = os.path.join(DIRETORIO_ATUAL, "banco_vetorial")

# Mapeamento de URLs alvo (a secção de MG encontra-se na página do Sudeste)
urls_alvo = {
    "Nacional": "https://www.pciconcursos.com.br/concursos/nacional/",
    "Minas Gerais": "https://www.pciconcursos.com.br/concursos/sudeste/" 
}

alvos_pdf = ["edital", "abertura", "normativo", "completo"]

# Lista de estados a ignorar durante a extração da região Sudeste
estados_proibidos = [
    "- sp", "- rj", "- es", "- pr", "- sc", "- rs", "- go", "- df", 
    "- ba", "- ce", "- pe", "- pb", "- rn", "- al", "- se", "- ma", 
    "- pi", "- pa", "- am", "- ro", "- ac", "- rr", "- ap", "- mt", 
    "- ms"
]

cabecalhos = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

print("A iniciar varredura incremental (Nacional e MG)...\n")

try:
    concursos_encontrados = []

    for abrangencia, url_portal in urls_alvo.items():
        print(f"A aceder ao portal [{abrangencia}]: {url_portal}")
        resposta_n1 = requests.get(url_portal, headers=cabecalhos)
        sopa_n1 = BeautifulSoup(resposta_n1.text, 'html.parser')
        
        area_principal = sopa_n1.find('div', id='concursos')
        if not area_principal:
            area_principal = sopa_n1
            
        links = area_principal.find_all('a')
        
        for link in links:
            href = link.get('href')
            if not href:
                continue
                
            href_lower = href.lower()
            
            # Filtragem de links não relacionados com anúncios de concursos
            if "/noticias/" not in href_lower:
                continue
            if "apostila" in href_lower or "provas" in href_lower or "simulados" in href_lower:
                continue
            if any(c['link'] == urljoin(url_portal, href) for c in concursos_encontrados):
                continue

            titulo_link = link.text.strip()
            if len(titulo_link) < 4: 
                continue

            # Extração da secção principal que contém as informações da vaga
            cartao = link.parent
            if cartao and cartao.parent:
                cartao = cartao.parent
                
            texto_cartao = cartao.text.lower() if cartao else titulo_link.lower()
            
            if len(texto_cartao) > 800:
                texto_cartao = titulo_link.lower()

            # Verificação de estado do concurso
            if "encerrad" in texto_cartao or "cancelad" in texto_cartao or "suspenso" in texto_cartao:
                continue

            # Aplicação de filtro geográfico restritivo para MG
            if abrangencia == "Minas Gerais" and any(estado in texto_cartao for estado in estados_proibidos):
                continue
                
            # Extração do salário máximo através de expressões regulares
            salario_maximo = 0.0
            match_salario = re.search(r'r\$\s*([\d\.]+,\d{2})', texto_cartao)
            if match_salario:
                try:
                    str_valor = match_salario.group(1).replace('.', '').replace(',', '.')
                    salario_maximo = float(str_valor)
                except ValueError:
                    pass
            
            # Normalização de títulos
            if titulo_link.lower() in ["vários cargos", "superior", "médio", "fundamental", "ver edital"]:
                linhas_texto = [l.strip() for l in cartao.text.split('\n') if len(l.strip()) > 3]
                titulo_limpo = linhas_texto[0].title() if linhas_texto else "Concurso Identificado"
            else:
                titulo_limpo = titulo_link.title()
                
            titulo_limpo = titulo_limpo.split('-')[0].strip()
            
            concursos_encontrados.append({
                'titulo': titulo_limpo, 
                'link': urljoin(url_portal, href),
                'abrangencia': abrangencia,
                'salario': salario_maximo
            })
                    
    print(f"Encontrados {len(concursos_encontrados)} concursos abertos compatíveis.\n")

    print("A ligar ao banco de dados vetorial...")
    cliente_chroma = chromadb.PersistentClient(path=CAMINHO_BANCO)
    colecao = cliente_chroma.get_or_create_collection(name="editais_brasil_mg_v2")

    # Lógica de atualização incremental
    # Recolha dos metadados existentes para evitar duplicação
    dados_existentes = colecao.get(include=['metadatas'])
    titulos_existentes = set()
    if dados_existentes and dados_existentes['metadatas']:
        for meta in dados_existentes['metadatas']:
            if meta and 'titulo' in meta:
                titulos_existentes.add(meta['titulo'].title())

    editais_processados = {"Nacional": 0, "Minas Gerais": 0}
    limite_por_regiao = 10 
    novos_adicionados = 0
    
    for concurso in concursos_encontrados:
        regiao = concurso['abrangencia']
        titulo_atual = concurso['titulo']
        
        # Ignorar o processamento se o documento já constar no banco de dados
        if titulo_atual in titulos_existentes:
            print(f"[{regiao}] Edital já existente na base: {titulo_atual} (A ignorar)")
            continue

        if editais_processados[regiao] >= limite_por_regiao:
            continue
            
        print(f"[{regiao}] Novo edital detectado (R$ {concurso['salario']}). A descarregar: {titulo_atual}")
        time.sleep(2)
        
        try:
            resposta_n2 = requests.get(concurso['link'], headers=cabecalhos, timeout=10)
            sopa_n2 = BeautifulSoup(resposta_n2.text, 'html.parser')
            links_n2 = sopa_n2.find_all('a')
            
            pdf_encontrado = False
            
            for link_doc in links_n2:
                href_doc = link_doc.get('href')
                texto_doc = link_doc.text.lower()
                
                if not href_doc:
                    continue
                    
                href_lower = href_doc.lower()
                
                is_pdf_link = False
                if href_lower.endswith('.pdf'): is_pdf_link = True
                elif 'arquivo.pciconcursos' in href_lower: is_pdf_link = True
                elif any(alvo in texto_doc for alvo in alvos_pdf): is_pdf_link = True
                
                if is_pdf_link and "apostila" not in href_lower and "apostila" not in texto_doc:
                        
                    link_completo_pdf = urljoin(concurso['link'], href_doc)
                    nome_temporario = "edital_aranha.pdf"
                    
                    headers_download = cabecalhos.copy()
                    headers_download['Accept'] = 'application/pdf,application/octet-stream,*/*'
                    
                    try:
                        resposta_pdf = requests.get(link_completo_pdf, headers=headers_download, timeout=15)
                        
                        # Verificação da assinatura do ficheiro (Magic Number) para confirmar o formato PDF
                        if not resposta_pdf.content.startswith(b'%PDF'):
                            continue 
                        
                        with open(nome_temporario, 'wb') as f:
                            f.write(resposta_pdf.content)
                        
                        texto_completo = ""
                        with open(nome_temporario, "rb") as arquivo:
                            leitor = pypdf.PdfReader(arquivo)
                            for pagina in leitor.pages:
                                texto_completo += pagina.extract_text() + "\n"
                        
                        pedacos = texto_completo.split("\n\n")
                        pedacos_limpos = [p.strip() for p in pedacos if len(p.strip()) > 50]
                        
                        if len(pedacos_limpos) > 0:
                            qtd_atual = colecao.count()
                            ids_pedacos = [f"aranha_{qtd_atual + i}" for i in range(len(pedacos_limpos))]
                            
                            metadados_pedacos = [{
                                "titulo": titulo_atual, 
                                "abrangencia": regiao,
                                "salario": concurso['salario']
                            } for _ in range(len(pedacos_limpos))]
                            
                            colecao.add(
                                documents=pedacos_limpos, 
                                metadatas=metadados_pedacos, 
                                ids=ids_pedacos
                            )
                            
                            pdf_encontrado = True
                            editais_processados[regiao] += 1
                            novos_adicionados += 1
                            print("-> Sucesso: Inserido no banco de dados.")
                            break
                            
                    except Exception:
                        continue 
                            
            if not pdf_encontrado:
                print("-> Erro: PDF não encontrado ou acesso bloqueado.")
        except Exception as ex:
             print(f"-> Erro ao aceder à página do concurso: {ex}")
        finally:
            if os.path.exists("edital_aranha.pdf"):
                os.remove("edital_aranha.pdf")

    print(f"\nVarredura finalizada. {novos_adicionados} novos editais adicionados ao banco.")

except Exception as e:
    print(f"Erro na execução do pipeline: {e}")