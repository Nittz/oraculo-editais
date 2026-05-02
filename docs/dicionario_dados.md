# Dicionário de dados

Este documento descreve os campos persistidos no pipeline atual e as fontes de origem.

> Para o panorama geral do projeto, ver [README.md](../README.md). Para a metodologia de chunking e prompting, ver `docs/metodologia.md` (a ser criado em fase posterior).

---

## 1. Estrutura no ChromaDB

A coleção `editais_brasil_mg_v2` armazena, para cada chunk:

### 1.1 Campos sempre presentes (gerados pelo crawler)

| Atributo | Tipo no Chroma | Tipo lógico | Origem | Descrição |
|---|---|---|---|---|
| `id` | `str` | identificador | gerado em runtime (`aranha_<n>`) | Chave única do chunk dentro da coleção |
| `document` | `str` | texto | chunk recursivo (paragrafo → sentença → janela) com overlap de 150 chars | Conteúdo textual do chunk indexado |
| `metadata.titulo` | `str` | dimensão | parser HTML + normalização (`.title()`, split em `-`) | Nome do edital, derivado da âncora do portal |
| `metadata.abrangencia` | `str` enum | dimensão | URL de origem do scraping | `Nacional` ou `Minas Gerais` |
| `metadata.salario` | `float` | métrica (BRL) | regex sobre o cartão do anúncio | Maior valor monetário detectado no resumo HTML |
| `metadata.status` | `str` enum | dimensão | crawler (ciclo de vida) | `aberto` enquanto o edital aparece no portal; `fechado` quando some entre rodadas. Default em registros legados sem o campo: `aberto` |
| `metadata.data_ultima_visualizacao` | `str` (ISO date) | timestamp | crawler | Data (`YYYY-MM-DD`) da última rodada em que o edital foi observado no portal. Atualizada para hoje sempre que o título reaparece |
| `metadata.fonte_extracao` | `str` enum | dimensão | crawler | `gemini` quando a extração estruturada rodou; `indisponivel` quando não havia chave ou houve falha |
| `metadata.confianca_extracao` | `str` enum | dimensão | LLM (auto-avaliação) | `alta` \| `media` \| `baixa` — declarada pelo próprio Gemini ao final da extração |

### 1.2 Campos extraídos via Gemini (presentes só quando a extração teve sucesso)

| Atributo | Tipo no Chroma | Tipo lógico | Exemplo | Observação de qualidade |
|---|---|---|---|---|
| `metadata.orgao` | `str` ou ausente | dimensão | `"Prefeitura Municipal de Belo Horizonte"` | Texto livre extraído pelo LLM. Pode variar em formatação entre edições |
| `metadata.uf` | `str` ou ausente | dimensão | `"MG"` | Validado contra lista oficial de UFs brasileiras. Valores fora da lista viram ausente |
| `metadata.cidade` | `str` ou ausente | dimensão | `"Belo Horizonte"` | Texto livre. Pode estar em maiúsculas/minúsculas variadas; sem normalização canônica ainda |
| `metadata.data_inscricao_fim` | `str` (ISO date) ou ausente | timestamp | `"2026-06-30"` | ISO 8601 estrito (`YYYY-MM-DD`). Datas absurdas (< 2020 ou > hoje+5 anos) viram ausente |
| `metadata.vagas` | `int` ou ausente | métrica | `12` | Total de vagas declarado. Apenas inteiros positivos. Editais que não declaram total ficam ausentes |
| `metadata.escolaridade` | `str` (CSV) ou ausente | dimensão | `"Médio, Superior"` | Lista canonicizada serializada como CSV. Valores possíveis: `Fundamental`, `Médio`, `Técnico`, `Superior`, `Pós-graduação` |
| `metadata.taxa_inscricao` | `float` ou ausente | métrica (BRL) | `80.00` | Valor da taxa em reais. Editais gratuitos podem cair em `0.00` ou ausente, dependendo do que o LLM identificou |

---

## 2. Detalhes por campo

### `titulo`
- **Pipeline de derivação**:
  1. Texto da âncora do link `/noticias/` no portal `pciconcursos.com.br`
  2. Se cair em rótulo genérico (*"Vários Cargos"*, *"Superior"*, *"Médio"*, *"Fundamental"*, *"Ver Edital"*), o crawler usa a primeira linha não-trivial do cartão
  3. Aplicado `.title()` e split em `-` para limpar sufixos
- **Cardinalidade esperada**: alta — um edital, um título
- **Risco**: títulos parecidos podem causar falsa duplicação (ex.: *"Prefeitura De X — 2024"* vs *"Prefeitura De X — Retificação"*). A deduplicação atual é por igualdade exata após normalização

### `abrangencia`
- **Valores possíveis**: `Nacional` | `Minas Gerais`
- **Como é decidido**: derivado da URL alvo do scraping (a página *Sudeste* contém Minas; outros estados são filtrados via lista de prefixos no texto do cartão)
- **Limitação**: o recorte regional atual é binário; expandir para outros estados exige re-tunar a lista de prefixos do filtro

### `salario`
- **Unidade**: reais brasileiros (BRL), `float`
- **Extração**: regex `r'r\$\s*([\d\.]+,\d{2})'` aplicado ao texto do cartão de listagem
- **Semântica**: maior valor monetário detectado **no cartão de listagem**, não necessariamente o maior salário do edital completo
- **Valor padrão**: `0.0` quando nenhum valor é encontrado pelo regex — é importante distinguir *"sem salário declarado"* (`0.0`) de *"salário desconhecido"*. Hoje os dois casos colidem
- **Limitações**: salários expressos por extenso (*"vencimento de cinco mil reais"*) ou em texto livre fora do cartão **não** são capturados

### `document` (chunk textual)
- **Tamanho típico**: parágrafos do PDF, com o filtro `len(strip()) > 50`
- **Limitação**: o split por `\n\n` quebra mal em editais com tabelas, listas numeradas e multi-coluna. A migração para `RecursiveCharacterTextSplitter` está prevista nos próximos passos do README

### `status` (ciclo de vida)
- **Valores possíveis**: `aberto` | `fechado`
- **Como é decidido**:
  - `aberto`: o crawler viu o título do edital no portal nesta rodada
  - `fechado`: o título existia na base mas **não foi visto** na rodada atual (ou seja, sumiu da listagem)
- **Decisão de design**: editais fechados **não são apagados** da base — mantemos histórico para análise. O dashboard filtra por `aberto` por padrão; um toggle expõe os fechados quando interessar
- **Compatibilidade legada**: chunks anteriores ao Bloco 5 não têm o campo. Em todo lugar que lê o status, aplicamos `meta.get('status', 'aberto')` como fallback. Após uma execução completa do crawler novo, todos os chunks passam a ter o campo populado

### `data_ultima_visualizacao`
- **Formato**: data ISO 8601 (`YYYY-MM-DD`), gravada como string
- **Quando é atualizada**: a cada rodada do crawler em que o título reaparece. Editais marcados como `fechado` mantêm o último valor gravado (auditoria de quando foi visto pela última vez)
- **Uso analítico futuro**: possibilita métricas como "tempo médio que um edital permanece aberto" e detecção de retificações silenciosas

### `fonte_extracao` e `confianca_extracao`
- **`fonte_extracao`**: `gemini` indica que o pipeline conseguiu extração estruturada via LLM; `indisponivel` quando não havia `GEMINI_API_KEY` no ambiente ou quando o JSON retornado não passou na validação. Permite separar análises confiáveis de baseline puro.
- **`confianca_extracao`**: declarada pelo próprio modelo durante a extração. `alta` quando os campos principais foram identificados com clareza; `media` quando 2-3 ficaram null/ambíguos; `baixa` quando a maior parte não pôde ser determinada. Útil como filtro defensivo para BI ("considerar só extrações de confiança alta+média").

### Campos opcionais extraídos (`orgao`, `uf`, `cidade`, `data_inscricao_fim`, `vagas`, `escolaridade`, `taxa_inscricao`)
- **Política de ausência**: campos não preenchidos pelo LLM **não** são gravados no metadata (em vez de `null`). Reduz lixo de filtragem (`meta.get(campo)` devolve `None` naturalmente).
- **`escolaridade` como CSV**: ChromaDB só aceita escalares em metadata. A lista canonicizada (`["Médio", "Superior"]`) vira a string `"Médio, Superior"` no momento de gravar; o dashboard separa via `split(',')` ao filtrar.
- **Regravação em rodadas futuras**: o ciclo de vida atual (`atualizar_status_edital`) **preserva** os campos extraídos quando atualiza apenas `status` e `data_ultima_visualizacao`. Para reprocessar a extração, é preciso forçar re-ingestão (TODO: flag no crawler).

---

## 3. Campos desejáveis ainda **não** persistidos

A maior parte do schema desejado já entrou em produção no Bloco 6 (extração via Gemini). Os campos abaixo continuam como evolução prevista:

| Campo | Tipo previsto | Fonte provável | Comentário |
|---|---|---|---|
| `data_publicacao` | `date` | corpo do PDF | Marco temporal do edital (não confundir com inscrição) |
| `data_inscricao_inicio` | `date` | corpo do PDF | Habilita alerta proativo de abertura |
| `data_prova` | `date` | corpo do PDF | Apoia planejamento do candidato |
| `link_pdf` | `url` | crawler | Hoje vive apenas em runtime, não é persistido |
| `link_pagina_oficial` | `url` | crawler | Idem |
| `data_coleta` | `datetime` | crawler | Rastreabilidade do scraping (a `data_ultima_visualizacao` cobre parte disso) |
| `hash_pdf` | `sha256` | crawler | Detectar retificação/prorrogação automaticamente |
| `cargos` | `list[str]` | corpo do PDF | Granularidade abaixo de `escolaridade`; alimenta busca por cargo específico |

Quando estes forem incorporados, será natural promover o schema para `pydantic` e introduzir `argparse` no crawler (`--reextract`, `--limit`, `--regiao`).

---

## 4. Convenções

- **Idioma**: nomes de campos em português, sem acento. Valores de enums em formato humano (`"Nacional"`, `"Minas Gerais"`).
- **Tipos numéricos**: `float` para valores monetários, `int` para contagens.
- **Datas**: ISO 8601 (`YYYY-MM-DD`) quando forem introduzidas.
- **Identificadores gerados**: prefixo `aranha_` denota origem no crawler. Outros prefixos podem surgir em ingestões manuais futuras.
