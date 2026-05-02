"""Extracao estruturada de metadados de edital via LLM (Gemini).

Funcao principal:
    extrair_metadata_edital(texto_pdf, model) -> dict

Devolve um dicionario com chaves padronizadas (orgao, uf, cidade,
data_inscricao_fim, vagas, escolaridade, taxa_inscricao, fonte_extracao,
confianca_extracao). Em qualquer falha (modelo ausente, erro de API, JSON
invalido, campos malformados) o resultado degrada graciosamente para o
shape padrao com `fonte_extracao = "indisponivel"` e campos None/vazios.
"""
import json
import re
from datetime import date, datetime

# UFs brasileiras validas
UFS_BR = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}

# Niveis canonicos de escolaridade (ordem aplicada na saida)
ESCOLARIDADE_CANONICAS = ["Fundamental", "Médio", "Técnico", "Superior", "Pós-graduação"]

# Mapeamento de variantes -> canonico. Ordem importa: marcadores especificos
# (pos-graduacao, ensino medio) sao verificados antes dos genericos (graduacao,
# medio) para evitar match incorreto via substring.
_ESCOLARIDADE_MAP = [
    (("pos-graduacao", "pós-graduação", "pos graduacao", "mestrado", "doutorado", "especializacao", "especialização"), "Pós-graduação"),
    (("ensino medio", "ensino médio"), "Médio"),
    (("ensino superior", "bacharelado", "licenciatura", "graduacao", "graduação"), "Superior"),
    (("fundamental",), "Fundamental"),
    (("tecnico", "técnico"), "Técnico"),
    (("medio", "médio"), "Médio"),
    (("superior",), "Superior"),
]

# Limite de tokens enviados ao Gemini (evita custo/latencia em PDFs gigantes)
_LIMITE_CARACTERES_PROMPT = 60000

# Prompt-template (manter como string formatada em runtime, nao f-string,
# para nao escapar chaves do JSON-schema)
_PROMPT = """Voce e um analista de editais de concurso publico brasileiro.

Tarefa: extrair metadados estruturados do edital fornecido.
Responda APENAS com JSON valido, sem markdown, sem comentarios, sem texto adicional.

Schema esperado (use null quando nao tiver certeza; nao invente):
{
  "orgao": string ou null,
  "uf": string ou null,
  "cidade": string ou null,
  "data_inscricao_fim": string ou null,
  "vagas": int ou null,
  "escolaridade": [string],
  "taxa_inscricao": float ou null,
  "confianca_extracao": "alta" ou "media" ou "baixa"
}

Regras:
- "orgao": nome formal do orgao publico (ex.: "Prefeitura Municipal de Belo Horizonte").
- "uf": sigla em 2 letras maiusculas (ex.: "MG"). Null se nao explicito.
- "cidade": cidade principal do certame.
- "data_inscricao_fim": ULTIMO dia de inscricao em ISO 8601 (YYYY-MM-DD). Null se nao declarado.
- "vagas": total de vagas (somatorio dos cargos). Null se nao declarado.
- "escolaridade": niveis exigidos no certame, dentre: "Fundamental", "Medio", "Tecnico", "Superior", "Pos-graduacao". Lista pode ter mais de um.
- "taxa_inscricao": valor em reais (float). Null se nao houver ou nao for declarado.
- "confianca_extracao":
  - "alta": campos principais identificados com clareza
  - "media": 2-3 campos importantes ficaram null/ambiguos
  - "baixa": maior parte dos campos nao pode ser determinada

TEXTO DO EDITAL:
"""


def extrair_metadata_edital(texto_pdf: str, model) -> dict:
    """Extrai metadados estruturados via Gemini.

    Parametros
    ----------
    texto_pdf : str
        Texto bruto extraido do PDF do edital.
    model : objeto Gemini ja configurado (`genai.GenerativeModel(...)`) ou None.
        Se None ou vazio, devolve estrutura com fonte_extracao='indisponivel'.

    Returns
    -------
    dict com chaves: orgao, uf, cidade, data_inscricao_fim, vagas,
    escolaridade (lista), taxa_inscricao, fonte_extracao, confianca_extracao.
    """
    base = _metadata_vazia()
    if not model or not texto_pdf or not texto_pdf.strip():
        return base

    texto_truncado = texto_pdf[:_LIMITE_CARACTERES_PROMPT]
    prompt = _PROMPT + texto_truncado

    try:
        resposta = model.generate_content(prompt)
        bruto = _extrair_json_da_resposta(getattr(resposta, "text", "") or "")
    except Exception as exc:
        nome_modelo = getattr(model, "nome_modelo", "?")
        msg = str(exc).splitlines()[0][:200] if str(exc) else "?"
        print(
            f"  -> aviso: extracao Gemini falhou com modelo {nome_modelo} "
            f"({type(exc).__name__}: {msg}); seguindo sem metadados estruturados"
        )
        return base

    if not isinstance(bruto, dict):
        return base

    return _validar_e_normalizar(bruto)


def _metadata_vazia() -> dict:
    return {
        "orgao": None,
        "uf": None,
        "cidade": None,
        "data_inscricao_fim": None,
        "vagas": None,
        "escolaridade": [],
        "taxa_inscricao": None,
        "fonte_extracao": "indisponivel",
        "confianca_extracao": "baixa",
    }


def _extrair_json_da_resposta(texto: str):
    """Tenta parsear JSON da resposta. Tolera fences markdown e prefixos."""
    if not texto:
        return None
    limpo = texto.strip()
    # Remove fences markdown comuns: ```json ... ``` ou ``` ... ```
    limpo = re.sub(r"^```(?:json)?\s*", "", limpo)
    limpo = re.sub(r"\s*```\s*$", "", limpo)
    try:
        return json.loads(limpo)
    except json.JSONDecodeError:
        # Procura primeiro objeto JSON aparente
        match = re.search(r"\{[\s\S]*\}", limpo)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _validar_e_normalizar(bruto: dict) -> dict:
    base = _metadata_vazia()
    base["fonte_extracao"] = "gemini"

    # orgao
    valor = bruto.get("orgao")
    if isinstance(valor, str) and valor.strip():
        base["orgao"] = valor.strip()

    # uf
    valor = bruto.get("uf")
    if isinstance(valor, str):
        candidato = valor.strip().upper()
        if candidato in UFS_BR:
            base["uf"] = candidato

    # cidade
    valor = bruto.get("cidade")
    if isinstance(valor, str) and valor.strip():
        base["cidade"] = valor.strip()

    # data_inscricao_fim
    base["data_inscricao_fim"] = _validar_iso_date(bruto.get("data_inscricao_fim"))

    # vagas
    valor = bruto.get("vagas")
    if isinstance(valor, bool):
        pass  # bool e subtipo de int em Python; rejeita explicitamente
    elif isinstance(valor, int) and valor > 0:
        base["vagas"] = valor
    elif isinstance(valor, float) and valor > 0:
        base["vagas"] = int(valor)

    # escolaridade
    base["escolaridade"] = _normalizar_escolaridade(bruto.get("escolaridade"))

    # taxa_inscricao
    valor = bruto.get("taxa_inscricao")
    if isinstance(valor, bool):
        pass
    elif isinstance(valor, (int, float)) and valor >= 0:
        base["taxa_inscricao"] = float(valor)

    # confianca_extracao
    valor = bruto.get("confianca_extracao")
    if isinstance(valor, str) and valor.strip().lower() in ("alta", "media", "baixa"):
        base["confianca_extracao"] = valor.strip().lower()

    return base


def _validar_iso_date(valor) -> str:
    if not isinstance(valor, str):
        return None
    try:
        dt = datetime.strptime(valor.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None
    # Sanity: rejeita datas absurdas
    hoje = date.today()
    if dt.year < 2020 or dt.year > hoje.year + 5:
        return None
    return dt.isoformat()


def _normalizar_escolaridade(valor) -> list:
    if not isinstance(valor, list):
        return []
    encontradas = set()
    for item in valor:
        if not isinstance(item, str):
            continue
        chave = item.strip().lower()
        if not chave:
            continue
        for variantes, canonico in _ESCOLARIDADE_MAP:
            if any(v in chave for v in variantes):
                encontradas.add(canonico)
                break
    # Ordena conforme ordem canonica
    return [n for n in ESCOLARIDADE_CANONICAS if n in encontradas]
