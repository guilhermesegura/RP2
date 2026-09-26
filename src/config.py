"""
Configurações usadas por todos os scripts.

Os valores ficam aqui para não espalhar números pelo código.
"""
from pathlib import Path

# --- Caminhos -----------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_RAW = BASE_DIR / "data" / "raw"
DATA_PROCESSED = BASE_DIR / "data" / "processed"

SSP_DIR = DATA_RAW / "ssp"
IEGM_DIR = DATA_RAW / "ieg-m"
IBGE_DIR = DATA_RAW / "ibge"

# Os arquivos da SSP vêm um por ano. O script lê todos que encontrar.
SSP_CRIMINAIS_GLOB = "SPDadosCriminais_*.xlsx"
SSP_VEICULOS_GLOB = "VeiculosSubtraidos_*.xlsx"
SSP_CELULARES_GLOB = "CelularesSubtraidos_*.xlsx"

# O IEGM tem uma planilha por exercício. O script lê todas. O nome do arquivo
# não diz o ano (ieg_m_2025.xls é o exercício 2022); o que vale é a coluna
# exercicio_ref dentro da planilha.
IEGM_GLOB = "*.xls"

# Gerados pelo ibge_sidra.py
POPULACAO_CSV = IBGE_DIR / "ibge_populacao.csv"
PIB_PERCAPITA_CSV = IBGE_DIR / "ibge_pib_percapita.csv"
URBANIZACAO_CSV = IBGE_DIR / "ibge_urbanizacao.csv"
CENSO2022_CSV = IBGE_DIR / "ibge_censo2022.csv"

# --- Saídas -------------------------------------------------------------
# Arquivos intermediários da SSP. Demoram para gerar, por isso ficam salvos.
SSP_PAINEL_CSV = DATA_PROCESSED / "ssp_painel.csv"
SSP_TEXTURA_CSV = DATA_PROCESSED / "ssp_textura.csv"
SSP_COMPLEMENTAR_CSV = DATA_PROCESSED / "ssp_complementar.csv"
SSP_COBERTURA_CSV = DATA_PROCESSED / "ssp_cobertura.csv"

# Base final (uma linha por município)
BASE_FINAL_CSV = DATA_PROCESSED / "base_final.csv"
DICIONARIO_CSV = DATA_PROCESSED / "dicionario_base.csv"
RELATORIO_TXT = DATA_PROCESSED / "relatorio_base.txt"

# --- Parâmetros ---------------------------------------------------------
UF_CODE_SP = "35"
TAXA_POR_HABITANTES = 100_000
CODIGO_CAPITAL = "3550308"   # São Paulo não tem IEGM (é fiscalizada pelo TCM-SP)

# --- Tabelas do SIDRA ---------------------------------------------------
TABELA_POPULACAO = "6579"    # estimativa de população (anual)
TABELA_PIB = "5938"          # PIB dos municípios (último ano: 2023)
# Urbanização vem da 9923 (Censo 2022). A tabela 202 parece a mesma coisa,
# mas é do Censo 2010: period="last" nela devolve 2010 sem dar erro.
TABELA_URBANIZACAO = "9923"
ANO_CENSO_URBANIZACAO = "2022"

# Indicadores do Censo 2022 por município. Os códigos de tabela, variável e
# categoria foram conferidos na API de metadados do IBGE em 10/09/2026.
# Entraram porque PIB per capita e urbanização sozinhos não representam bem
# a condição socioeconômica (o PIB per capita, por exemplo, fica muito alto
# em cidades com uma usina ou um polo industrial).
TABELA_ALFABETIZACAO = "9543"   # variável 2513: % alfabetizados, 15 anos ou mais
TABELA_RENDA = "10295"          # variável 13534: renda domiciliar per capita
                                #   mediana (R$). Mediana, não média, para
                                #   não sofrer com os valores extremos.
TABELA_ESGOTO = "6805"          # variável 381: domicílios por tipo de esgoto
TABELA_LIXO = "6892"            # variável 381: domicílios por destino do lixo
ANO_CENSO = "2022"

# Códigos das categorias na API. "Total" em sexo, cor/raça e idade quer dizer
# o município inteiro, sem recorte.
CENSO_TOTAL_SEXO = "6794"
CENSO_TOTAL_COR = "95251"
CENSO_TOTAL_IDADE_ALFAB = "100362"   # classificação 287 (tabela 9543)
CENSO_TOTAL_IDADE_RENDA = "95253"    # classificação 58 (tabela 10295)

# Esgoto adequado = rede geral (ou fossa ligada à rede) + fossa séptica.
CENSO_ESGOTO_TOTAL = "46292"
CENSO_ESGOTO_ADEQUADO = ["46290", "72112"]
CENSO_LIXO_TOTAL = "10972"
CENSO_LIXO_COLETADO = ["2520"]

# Anos usados na análise.
#   None  -> usa todos os anos que estiverem em data/raw/ssp/
#   lista -> ex.: [2023, 2024, 2025]
# Usamos 2023 a 2025: três anos completos, depois da troca de sistema da SSP
# (entre 2022 e 2023) e depois da pandemia. A janela foi testada no
# notebook 01.
ANOS_JANELA = [2023, 2024, 2025]

# Ano da população usada como denominador das taxas.
#   None -> usa o ano que estiver no CSV do IBGE
# A tabela 6579 não tem 2022 nem 2023 (anos de Censo). Usamos 2024, que é o
# meio da janela.
ANO_POPULACAO_REF = 2024

# Municípios com menos habitantes que isso recebem flag_pop_pequena. Neles,
# uma única ocorrência já vira uma taxa alta por 100 mil habitantes. Não são
# excluídos da base, só marcados.
POPULACAO_MINIMA = 5_000

# Se duas features têm correlação de Spearman acima disso, medem a mesma
# coisa e uma delas sai. Usado no notebook 02 e para decidir se o PIB per
# capita fica ao lado da renda mediana.
LIMIAR_REDUNDANCIA = 0.85

# --- IEGM ---------------------------------------------------------------
# As notas do IEGM vêm como letra. Esta é a conversão para número.
ESCALA_ORDINAL_IEGM = {"C": 1, "C+": 2, "B": 3, "B+": 4, "A": 5}

# nome na planilha -> nome na base final
COLUNAS_IEGM = {
    "iegm": "iegm",
    "iplanejamento": "i_planejamento",
    "ifiscal": "i_fiscal",
    "ieduc": "i_educ",
    "isaude": "i_saude",
    "iamb": "i_amb",
    "icidade": "i_cidade",
    "igov": "i_gov_ti",
}

# --- Naturezas criminais usadas ----------------------------------------
# Cada grupo vira uma taxa na base. A comparação com o arquivo da SSP é feita
# sem acento e em maiúsculas.
GRUPOS_NATUREZA = {
    # CVLI = crimes violentos letais intencionais. É o indicador padrão nos
    # estudos de segurança pública no Brasil, e juntar os três diminui a
    # quantidade de zeros.
    "cvli": ["HOMICÍDIO DOLOSO", "LATROCÍNIO", "LESÃO CORPORAL SEGUIDA DE MORTE"],
    "tentativa_homicidio": ["TENTATIVA DE HOMICÍDIO"],
    "lesao_dolosa": ["LESÃO CORPORAL DOLOSA"],
    "roubo_outros": ["ROUBO - OUTROS"],
    "roubo_veiculo": ["ROUBO DE VEÍCULO"],
    "roubo_carga": ["ROUBO DE CARGA"],
    "furto_outros": ["FURTO - OUTROS"],
    "furto_veiculo": ["FURTO DE VEÍCULO"],
    "estupro_total": ["ESTUPRO", "ESTUPRO DE VULNERÁVEL"],
    "trafico": ["TRÁFICO DE ENTORPECENTES"],
}

# Ficaram de fora (mas continuam no painel intermediário):
#   - crimes culposos de trânsito: são segurança viária, não criminalidade;
#   - porte/apreensão de drogas e porte de arma: dependem de quanto a polícia
#     atua, não de quanto crime acontece.
# O tráfico tem esse mesmo problema, mas ficou por indicar presença de
# organização criminosa. Vale citar essa limitação no artigo.

# Taxas de segunda linha (concentradas em poucos municípios). A modelagem
# decide se entram.
NATUREZAS_TIER2 = ["roubo_carga"]
