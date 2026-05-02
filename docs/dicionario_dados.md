# Dicionário de dados

Este documento descreve os campos persistidos no pipeline atual e as fontes de origem.

> Para o panorama geral do projeto, ver [README.md](../README.md). Para a metodologia de chunking e prompting, ver `docs/metodologia.md` (a ser criado em fase posterior).

---

## 1. Estrutura no ChromaDB

A coleção `editais_brasil_mg_v2` armazena, para cada chunk:

| Atributo | Tipo no Chroma | Tipo lógico | Origem | Descrição |
|---|---|---|---|---|
| `id` | `str` | identificador | gerado em runtime (`aranha_<n>`) | Chave única do chunk dentro da coleção |
| `document` | `str` | texto | trecho do PDF após `split("\n\n")` | Conteúdo textual do chunk indexado |
| `metadata.titulo` | `str` | dimensão | parser HTML + normalização (`.title()`, split em `-`) | Nome do edital, derivado da âncora do portal |
| `metadata.abrangencia` | `str` enum | dimensão | URL de origem do scraping | `Nacional` ou `Minas Gerais` |
| `metadata.salario` | `float` | métrica (BRL) | regex sobre o cartão do anúncio | Maior valor monetário detectado no resumo HTML |
| `metadata.status` | `str` enum | dimensão | crawler (ciclo de vida) | `aberto` enquanto o edital aparece no portal; `fechado` quando some entre rodadas. Default em registros legados sem o campo: `aberto` |
| `metadata.data_ultima_visualizacao` | `str` (ISO date) | timestamp | crawler | Data (`YYYY-MM-DD`) da última rodada em que o edital foi observado no portal. Atualizada para hoje sempre que o título reaparece |

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

---

## 3. Campos desejáveis ainda **não** persistidos

Os campos abaixo são úteis para BI, busca e priorização, mas o crawler atual ainda **não** os extrai/persiste. Estão listados em *Próximos passos* no README:

| Campo | Tipo previsto | Fonte provável | Comentário |
|---|---|---|---|
| `orgao` | `str` | corpo do PDF / título | Hoje vive embutido no `titulo` |
| `data_publicacao` | `date` | corpo do PDF | Marco temporal do edital |
| `data_inscricao_inicio` | `date` | corpo do PDF | Habilita alerta proativo |
| `data_inscricao_fim` | `date` | corpo do PDF | Habilita alerta D-3 |
| `data_prova` | `date` | corpo do PDF | Apoia planejamento do candidato |
| `quantidade_vagas` | `int` | corpo do PDF | Métrica essencial para BI |
| `nivel_escolaridade` | `enum` | corpo do PDF | Filtro de aderência |
| `taxa_inscricao` | `float` | corpo do PDF | Custo de oportunidade |
| `cidade` | `str` | corpo do PDF | Recorte geográfico fino |
| `link_pdf` | `url` | crawler | Hoje vive apenas em runtime, não é persistido |
| `link_pagina_oficial` | `url` | crawler | Idem |
| `data_coleta` | `datetime` | crawler | Rastreabilidade do scraping |
| `hash_pdf` | `sha256` | crawler | Detectar retificação/prorrogação |

A intenção é que, ao introduzir `pydantic`, esses campos passem a fazer parte do schema canônico do edital, com extração estruturada via LLM antes do chunking.

---

## 4. Convenções

- **Idioma**: nomes de campos em português, sem acento. Valores de enums em formato humano (`"Nacional"`, `"Minas Gerais"`).
- **Tipos numéricos**: `float` para valores monetários, `int` para contagens.
- **Datas**: ISO 8601 (`YYYY-MM-DD`) quando forem introduzidas.
- **Identificadores gerados**: prefixo `aranha_` denota origem no crawler. Outros prefixos podem surgir em ingestões manuais futuras.
