# Deploy no Hugging Face Spaces

Este guia descreve o procedimento para publicar o dashboard no [Hugging Face Spaces](https://huggingface.co/spaces) usando o SDK Docker.

A estratégia atual é **snapshot embutido**: o `banco_vetorial/` é gerado localmente e versionado via Git LFS na branch `hf-deploy`. A `main` permanece limpa para o GitHub. Atualizações de dado são feitas re-rodando o crawler localmente e fazendo push da `hf-deploy`.

---

## Pré-requisitos

### Ferramentas locais

```bash
# Git LFS (necessário para versionar banco_vetorial)
# Windows: baixe o instalador em https://git-lfs.com/
# Linux/Mac: brew install git-lfs ou apt install git-lfs

git lfs install
```

### No Hugging Face

1. Conta criada em https://huggingface.co
2. Space criado em https://huggingface.co/new-space com:
   - **SDK**: Docker
   - **Docker template**: Blank
   - **Hardware**: CPU basic (free)
   - **Visibility**: Public
3. Secret `GEMINI_API_KEY` configurado em **Settings → Variables and secrets**
4. Token de acesso com permissão `Write` em https://huggingface.co/settings/tokens

---

## Setup inicial (uma vez só)

### 1. Popular o banco vetorial localmente

```bash
python src/oraculo/crawler.py
```

Cria `banco_vetorial/` com os editais atuais (~5-10 min).

### 2. Criar a branch de deploy

```bash
git checkout -b hf-deploy
```

### 3. Configurar Git LFS para o banco vetorial

```bash
git lfs track "banco_vetorial/**"
git add .gitattributes
```

### 4. Permitir versionamento do banco vetorial nesta branch

Edite `.gitignore` e remova (ou comente) a linha `banco_vetorial/`. Esta mudança fica **apenas** na branch `hf-deploy`.

### 5. Adicionar frontmatter HF no topo do README

Insira o bloco abaixo no início do `README.md` desta branch (a `main` no GitHub não recebe esse bloco):

```yaml
---
title: Oraculo de Editais
emoji: 🏛️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
---
```

### 6. Adicionar HF Space como remote

```bash
git remote add hf https://huggingface.co/spaces/<seu-usuario>/<nome-do-space>
```

### 7. Commitar tudo

```bash
git add .gitignore README.md banco_vetorial/
git commit -m "chore: prepara branch hf-deploy com snapshot do banco vetorial"
```

### 8. Push inicial

```bash
git push hf hf-deploy:main
```

Quando solicitado:
- **Username**: seu usuário HF
- **Password**: seu token HF (não a senha da conta)

O Space vai detectar o push, builda o container (~3-5 min) e o dashboard fica acessível em
`https://huggingface.co/spaces/<seu-usuario>/<nome-do-space>`.

---

## Atualizações periódicas

Sempre que quiser atualizar o snapshot do banco vetorial e/ou trazer mudanças de código da `main`:

```bash
# 1. Atualiza o banco vetorial
python src/oraculo/crawler.py

# 2. Vai para a branch de deploy
git checkout hf-deploy

# 3. Traz mudanças da main
git merge main

# 4. Stage do novo snapshot (LFS cuida dos arquivos grandes)
git add banco_vetorial/

# 5. Commit e push
git commit -m "deploy: snapshot $(date +%Y-%m-%d)"
git push hf hf-deploy:main
```

---

## Troubleshooting

### O Space builda mas o dashboard mostra "Chave da API não configurada"

O secret `GEMINI_API_KEY` não foi exposto ao container, ou o nome diverge.

- Confira em **Settings → Variables and secrets** se o nome é exatamente `GEMINI_API_KEY` (caixa alta).
- Reinicie o Space em **Settings → Restart Space**.

### Build falha com "Permission denied" em `banco_vetorial/`

O `Dockerfile` copia tudo como usuário `user` (UID 1000). Se houver permissão estranha local, force:

```bash
git rm -r --cached banco_vetorial/
git add banco_vetorial/
git commit -m "fix: re-stage banco_vetorial com permissoes consistentes"
git push hf hf-deploy:main
```

### LFS quota estourou

A free tier do HF Spaces oferece 1 GB de Git LFS. Como o `banco_vetorial/` cresce com o número de editais, eventualmente vai bater no limite. Quando isso acontecer, é hora de migrar para a estratégia C (storage externo): Chroma Cloud, Qdrant Cloud ou similar. Ver seção *Próximos passos* no [README](../README.md).

### Logs do container

`https://huggingface.co/spaces/<seu-usuario>/<nome-do-space>/logs` mostra stdout/stderr do build e do runtime.

---

## Estratégias alternativas (futuro)

| Estratégia | Quando faz sentido |
|---|---|
| **Snapshot embutido** (atual) | Baixo volume, atualizações manuais aceitáveis |
| **Lazy load via crawler na primeira execução** | Sem dependência de LFS, mas com cold start lento |
| **Storage externo (Chroma Cloud, Qdrant Cloud, HF Datasets)** | Volume crescente, atualização automatizada, múltiplos consumidores |

A migração para *storage externo* está em *Próximos passos* no README e fica natural quando houver volume justificando.
