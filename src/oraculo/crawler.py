"""Crawler de editais de concursos publicos do pciconcursos.com.br.

Cobre o ciclo de vida basico:
  - editais novos sao baixados, fatiados e indexados no ChromaDB
  - editais ja indexados que ainda aparecem no portal sao marcados como `aberto`
    e tem `data_ultima_visualizacao` atualizada
  - editais ja indexados que NAO aparecem mais no portal sao marcados como `fechado`
    (a base preserva o historico em vez de apagar)
"""
import os
import re
import time
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import pypdf
import chromadb


# ----------------------------------------------------------------------------
# Configuracao
# ----------------------------------------------------------------------------
RAIZ_PROJETO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CAMINHO_BANCO = os.path.join(RAIZ_PROJETO, "banco_vetorial")
NOME_COLECAO = "editais_brasil_mg_v2"

DATA_VISUALIZACAO_HOJE = date.today().isoformat()

URLS_ALVO = {
    "Nacional": "https://www.pciconcursos.com.br/concursos/nacional/",
    "Minas Gerais": "https://www.pciconcursos.com.br/concursos/sudeste/",
}

ALVOS_PDF = ["edital", "abertura", "normativo", "completo"]

# Filtro positivo: na aba Sudeste so aceita editais que mencionam MG no cartao.
# Inversao da logica anterior (lista de UFs proibidas), que falhava quando o
# portal mudava o formato (ex.: "(SP)" no lugar de "- sp").
MG_MARKERS = re.compile(r"\b(minas gerais|mg|belo horizonte|bh)\b", re.IGNORECASE)

LIMITE_POR_REGIAO = 10  # quantos editais NOVOS processar por rodada e por regiao

CABECALHOS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


# ----------------------------------------------------------------------------
# Helpers de ChromaDB
# ----------------------------------------------------------------------------
def coletar_titulos_da_base(colecao):
    """Mapeia titulo -> lista de ids de chunks ja na base."""
    dados = colecao.get(include=["metadatas"])
    titulo_para_ids = {}
    if dados and dados.get("metadatas") and dados.get("ids"):
        for chunk_id, meta in zip(dados["ids"], dados["metadatas"]):
            if meta and "titulo" in meta:
                titulo_para_ids.setdefault(meta["titulo"], []).append(chunk_id)
    return titulo_para_ids


def atualizar_status_edital(colecao, ids_chunks, status):
    """Atualiza status e data_ultima_visualizacao de todos os chunks de um edital.

    Preserva os demais campos de metadata. Quando status='aberto', refresca
    `data_ultima_visualizacao` para a data de hoje. Quando status='fechado',
    mantem o ultimo `data_ultima_visualizacao` ja gravado (util para auditoria).
    """
    if not ids_chunks:
        return 0
    atual = colecao.get(ids=ids_chunks, include=["metadatas"])
    novos_metas = []
    for meta_atual in atual.get("metadatas", []):
        novo = dict(meta_atual or {})
        novo["status"] = status
        if status == "aberto":
            novo["data_ultima_visualizacao"] = DATA_VISUALIZACAO_HOJE
        novos_metas.append(novo)
    colecao.update(ids=ids_chunks, metadatas=novos_metas)
    return len(ids_chunks)


# ----------------------------------------------------------------------------
# Coleta no portal
# ----------------------------------------------------------------------------
def extrair_listagem_de_editais():
    """Varre as URLs alvo e devolve lista de editais candidatos (sem download)."""
    encontrados = []

    for abrangencia, url_portal in URLS_ALVO.items():
        print(f"A aceder ao portal [{abrangencia}]: {url_portal}")
        resposta = requests.get(url_portal, headers=CABECALHOS, timeout=15)
        sopa = BeautifulSoup(resposta.text, "html.parser")

        area_principal = sopa.find("div", id="concursos") or sopa
        links = area_principal.find_all("a")

        for link in links:
            href = link.get("href")
            if not href:
                continue

            href_lower = href.lower()
            if "/noticias/" not in href_lower:
                continue
            if any(marker in href_lower for marker in ("apostila", "provas", "simulados")):
                continue

            link_completo = urljoin(url_portal, href)
            if any(c["link"] == link_completo for c in encontrados):
                continue

            titulo_link = link.text.strip()
            if len(titulo_link) < 4:
                continue

            cartao = link.parent
            if cartao and cartao.parent:
                cartao = cartao.parent
            texto_cartao = (cartao.text if cartao else titulo_link).lower()
            if len(texto_cartao) > 800:
                texto_cartao = titulo_link.lower()

            if any(s in texto_cartao for s in ("encerrad", "cancelad", "suspenso")):
                continue

            # Filtro positivo: para aba Sudeste, exigir evidencia de MG.
            if abrangencia == "Minas Gerais" and not MG_MARKERS.search(texto_cartao):
                continue

            salario_maximo = 0.0
            match_salario = re.search(r"r\$\s*([\d\.]+,\d{2})", texto_cartao)
            if match_salario:
                try:
                    str_valor = match_salario.group(1).replace(".", "").replace(",", ".")
                    salario_maximo = float(str_valor)
                except ValueError:
                    pass

            # Normalizacao de titulo
            if titulo_link.lower() in ("vários cargos", "superior", "médio", "fundamental", "ver edital"):
                linhas_texto = [l.strip() for l in cartao.text.split("\n") if len(l.strip()) > 3]
                titulo_limpo = linhas_texto[0].title() if linhas_texto else "Concurso Identificado"
            else:
                titulo_limpo = titulo_link.title()
            titulo_limpo = titulo_limpo.split("-")[0].strip()

            encontrados.append({
                "titulo": titulo_limpo,
                "link": link_completo,
                "abrangencia": abrangencia,
                "salario": salario_maximo,
            })

    return encontrados


def baixar_e_indexar_edital(concurso, colecao):
    """Baixa o PDF principal, fationa em chunks e adiciona ao ChromaDB.

    Retorna True se conseguiu indexar pelo menos um chunk, False caso contrario.
    """
    nome_temporario = os.path.join(RAIZ_PROJETO, "edital_aranha.pdf")
    headers_download = CABECALHOS.copy()
    headers_download["Accept"] = "application/pdf,application/octet-stream,*/*"

    try:
        resposta = requests.get(concurso["link"], headers=CABECALHOS, timeout=10)
        sopa = BeautifulSoup(resposta.text, "html.parser")

        for link_doc in sopa.find_all("a"):
            href_doc = link_doc.get("href")
            if not href_doc:
                continue
            texto_doc = link_doc.text.lower()
            href_lower = href_doc.lower()

            eh_pdf = (
                href_lower.endswith(".pdf")
                or "arquivo.pciconcursos" in href_lower
                or any(alvo in texto_doc for alvo in ALVOS_PDF)
            )
            if not eh_pdf:
                continue
            if "apostila" in href_lower or "apostila" in texto_doc:
                continue

            link_pdf = urljoin(concurso["link"], href_doc)
            try:
                resp_pdf = requests.get(link_pdf, headers=headers_download, timeout=15)
                if not resp_pdf.content.startswith(b"%PDF"):
                    continue

                with open(nome_temporario, "wb") as f:
                    f.write(resp_pdf.content)

                texto_completo = ""
                with open(nome_temporario, "rb") as arquivo:
                    leitor = pypdf.PdfReader(arquivo)
                    for pagina in leitor.pages:
                        texto_completo += pagina.extract_text() + "\n"

                pedacos = [p.strip() for p in texto_completo.split("\n\n") if len(p.strip()) > 50]
                if not pedacos:
                    continue

                qtd_atual = colecao.count()
                ids_pedacos = [f"aranha_{qtd_atual + i}" for i in range(len(pedacos))]
                metadados = [
                    {
                        "titulo": concurso["titulo"],
                        "abrangencia": concurso["abrangencia"],
                        "salario": concurso["salario"],
                        "status": "aberto",
                        "data_ultima_visualizacao": DATA_VISUALIZACAO_HOJE,
                    }
                    for _ in range(len(pedacos))
                ]
                colecao.add(documents=pedacos, metadatas=metadados, ids=ids_pedacos)
                return True
            except Exception:
                continue

        return False
    except Exception as ex:
        print(f"  -> erro ao aceder pagina do concurso: {ex}")
        return False
    finally:
        if os.path.exists(nome_temporario):
            os.remove(nome_temporario)


# ----------------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------------
def main():
    print("A iniciar varredura incremental (Nacional e MG)...\n")

    encontrados = extrair_listagem_de_editais()
    print(f"\nEncontrados {len(encontrados)} concursos abertos compativeis.\n")

    print("A ligar ao banco de dados vetorial...")
    cliente = chromadb.PersistentClient(path=CAMINHO_BANCO)
    colecao = cliente.get_or_create_collection(name=NOME_COLECAO)

    titulo_para_ids = coletar_titulos_da_base(colecao)
    titulos_existentes = set(titulo_para_ids.keys())
    seen_titles = {c["titulo"] for c in encontrados}

    novos = seen_titles - titulos_existentes
    revisitados = seen_titles & titulos_existentes
    sumidos = titulos_existentes - seen_titles

    print(
        f"\nEstado da base: {len(novos)} novos | "
        f"{len(revisitados)} revisitados | "
        f"{len(sumidos)} sumidos (serao marcados como fechados)\n"
    )

    # 1) Indexa novos editais (com limite por regiao)
    processados = {"Nacional": 0, "Minas Gerais": 0}
    novos_adicionados = 0
    for concurso in encontrados:
        titulo = concurso["titulo"]
        regiao = concurso["abrangencia"]
        if titulo not in novos:
            continue
        if processados[regiao] >= LIMITE_POR_REGIAO:
            continue

        print(f"[{regiao}] Novo edital (R$ {concurso['salario']}). A descarregar: {titulo}")
        time.sleep(2)

        if baixar_e_indexar_edital(concurso, colecao):
            processados[regiao] += 1
            novos_adicionados += 1
            print("  -> sucesso: inserido no banco de dados")
        else:
            print("  -> falha: PDF nao encontrado ou bloqueado")

    # 2) Atualiza revisitados (status=aberto, refresh de data_ultima_visualizacao)
    chunks_aberto = 0
    for titulo in revisitados:
        chunks_aberto += atualizar_status_edital(
            colecao, titulo_para_ids[titulo], status="aberto"
        )

    # 3) Marca sumidos como fechados
    chunks_fechado = 0
    for titulo in sumidos:
        chunks_fechado += atualizar_status_edital(
            colecao, titulo_para_ids[titulo], status="fechado"
        )

    print("\nVarredura finalizada.")
    print(f"  Novos editais adicionados: {novos_adicionados}")
    print(f"  Revisitados (status=aberto): {len(revisitados)} editais ({chunks_aberto} chunks)")
    print(f"  Sumidos (status=fechado):    {len(sumidos)} editais ({chunks_fechado} chunks)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Erro na execucao do pipeline: {e}")
        raise
