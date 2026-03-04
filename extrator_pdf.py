import pypdf

# O nome do arquivo PDF que irá ser colocado na pasta
nome_arquivo = "documento_teste.pdf"

print(f"📄 Tentando abrir o arquivo: {nome_arquivo}...\n")

try:
    # Abrindo o arquivo em modo de leitura binária ('rb')
    with open(nome_arquivo, "rb") as arquivo:
        leitor = pypdf.PdfReader(arquivo)
        numero_paginas = len(leitor.pages)
        
        print(f"✅ Sucesso! O documento tem {numero_paginas} páginas.\n")
        
        # Vamos extrair o texto apenas da primeira página para testar
        primeira_pagina = leitor.pages[0]
        texto_bruto = primeira_pagina.extract_text()
        
        print("🔍 Primeiros 500 caracteres encontrados na página 1:")
        print("-" * 50)
        print(texto_bruto[:500])
        print("-" * 50)

except FileNotFoundError:
    print(f"❌ Erro: O arquivo '{nome_arquivo}' não foi encontrado na pasta.")
    print("Dica: Arraste um PDF para cá e renomeie para bater com o código!")