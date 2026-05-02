"""Chunker recursivo simples, sem dependencias externas.

Estrategia (ordem dos separadores tentados):
  1. paragrafos (`\\n\\n`)
  2. quebras de linha (`\\n`)
  3. sentencas (heuristica via `. `, `! `, `? `)
  4. espacos
  5. caractere a caractere (janela fixa, ultimo recurso)

Cada chunk respeita `tamanho_max`. Entre chunks adjacentes aplica-se um
sufixo do anterior como prefixo do seguinte (`overlap`), preservando
contexto na fronteira.
"""
import re

_TAMANHO_MIN_CHUNK = 50  # chunks menores que isso sao descartados
_SEPARADORES = ["\n\n", "\n", ". ", " ", ""]


def criar_chunks_recursivos(
    texto: str,
    tamanho_max: int = 1200,
    overlap: int = 150,
) -> list[str]:
    """Quebra o texto em chunks ate `tamanho_max` aplicando separadores em ordem."""
    if not texto or not texto.strip():
        return []
    texto = texto.strip()

    pedacos = _split_recursivo(texto, _SEPARADORES, tamanho_max)
    pedacos = [p.strip() for p in pedacos if p and p.strip()]

    if overlap > 0 and len(pedacos) > 1:
        pedacos = _aplicar_overlap(pedacos, overlap)

    return [p for p in pedacos if len(p) >= _TAMANHO_MIN_CHUNK]


def _split_recursivo(texto: str, separadores: list, tamanho_max: int) -> list:
    if len(texto) <= tamanho_max:
        return [texto]

    sep = separadores[0]
    if sep == "":
        # Ultimo recurso: janela fixa
        return [texto[i : i + tamanho_max] for i in range(0, len(texto), tamanho_max)]

    if sep in (". ", "! ", "? "):
        # Quebra por sentenca preserva o delimitador
        partes = re.split(r"(?<=[.!?])\s+", texto)
    else:
        partes = texto.split(sep)

    chunks = []
    buffer = ""
    for parte in partes:
        if not parte:
            continue
        candidato = (buffer + sep + parte) if buffer else parte
        if len(candidato) <= tamanho_max:
            buffer = candidato
        else:
            if buffer:
                if len(buffer) > tamanho_max:
                    chunks.extend(_split_recursivo(buffer, separadores[1:], tamanho_max))
                else:
                    chunks.append(buffer)
            if len(parte) <= tamanho_max:
                buffer = parte
            else:
                chunks.extend(_split_recursivo(parte, separadores[1:], tamanho_max))
                buffer = ""
    if buffer:
        if len(buffer) > tamanho_max:
            chunks.extend(_split_recursivo(buffer, separadores[1:], tamanho_max))
        else:
            chunks.append(buffer)
    return chunks


def _aplicar_overlap(chunks: list, overlap: int) -> list:
    """Acrescenta o sufixo do chunk N como prefixo do chunk N+1."""
    resultado = [chunks[0]]
    for i in range(1, len(chunks)):
        anterior = chunks[i - 1]
        cauda = anterior[-overlap:] if len(anterior) > overlap else anterior
        # Quebra no espaco mais proximo para nao cortar palavra ao meio
        idx_espaco = cauda.find(" ")
        if 0 < idx_espaco < len(cauda) - 5:
            cauda = cauda[idx_espaco + 1 :]
        resultado.append(f"{cauda} {chunks[i]}".strip())
    return resultado
