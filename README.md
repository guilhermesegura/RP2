# RP2 — Construção da base de dados

Pipeline que integra SSP-SP, IEGM/TCE-SP e SIDRA/IBGE em uma base com **uma
linha por município** do estado de São Paulo, seguida dos notebooks de
análise.

> Este README trata apenas da execução do projeto, da obtenção das bases e
> das saídas geradas. As decisões metodológicas e a sua justificativa estão
> no artigo principal.

## 1. Instalação

```bash
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

## 2. Obtenção das bases

Das três fontes, apenas o IBGE dispõe de acesso via API. As demais são
disponibilizadas por painéis interativos, de modo que o download precisa ser
feito manualmente antes da primeira execução.

| Fonte | Acesso | Ação necessária |
|---|---|---|
| SIDRA/IBGE | API REST pública (`apisidra.ibge.gov.br`) | nenhuma, o `main.py` consulta e salva em `data/raw/ibge/` |
| SSP-SP | painel interativo, export sob demanda | download manual (seção 2.1) |
| IEGM/TCE-SP | painel interativo, export sob demanda | download manual (seção 2.2) |

### 2.1 SSP-SP

Em <https://www.ssp.sp.gov.br/estatistica/consultas>, baixe os exports
**anuais** e salve em `data/raw/ssp/`, mantendo os nomes originais:

```
data/raw/ssp/SPDadosCriminais_<ano>.xlsx 
data/raw/ssp/VeiculosSubtraidos_<ano>.xlsx   
data/raw/ssp/CelularesSubtraidos_<ano>.xlsx 
```

São necessários os anos **2023, 2024 e 2025**, que compõem a janela de
análise definida em `ANOS_JANELA` (`src/config.py`). O ano de **2022 é
opcional** e serve apenas de série de controle no notebook 01: ele entra na
camada intermediária e é descartado antes da base final. O pipeline descobre
sozinho quais anos existem na pasta.

> **Os nomes das colunas mudam de ano para ano.** A SSP renomeou campos
> entre os exports e a aba de dicionário de dados por vezes documenta o nome
> antigo. Por isso toda coluna é resolvida por uma **lista de apelidos**, nas
> constantes `APELIDOS_*` no topo de `src/parse_ssp.py`: caso um ano novo
> quebre a leitura, é o único ponto a ajustar. Atenção ao aviso `nenhuma aba
> de dados reconhecida`, pois um nome de coluna não reconhecido não interrompe
> a execução, e sim produz **painel vazio**.

### 2.2 IEGM/TCE-SP

Em <https://www.tce.sp.gov.br/iegm>, baixe as planilhas de resultados e
salve todas em `data/raw/ieg-m/`. **O nome do arquivo é irrelevante**: o
pipeline lê todos os `.xls` da pasta e se orienta pela coluna `exercicio_ref`
interna de cada planilha, já que o nome em disco não corresponde ao exercício
apurado (`ieg_m_2025.xls` contém o exercício 2022).

Estão em uso os exercícios **2022, 2023 e 2024**, cuja média forma as colunas
`*_ord` da base. Quanto mais exercícios disponíveis, melhor.

### 2.3 IBGE/SIDRA

Nenhuma ação é necessária. Na primeira execução o `main.py` consulta a API e
grava em `data/raw/ibge/` os arquivos `ibge_populacao.csv`,
`ibge_pib_percapita.csv`, `ibge_urbanizacao.csv` e `ibge_censo2022.csv`. As
consultas são puladas nas execuções seguintes; para forçar uma atualização,
basta apagar esses arquivos.

## 3. Execução

### 3.1 Pipeline

```bash
python main.py            # roda o que faltar
python main.py --forcar   # reprocessa os .xlsx da SSP do zero
```

A execução ocorre em quatro etapas: consulta ao SIDRA, verificação dos
arquivos baixados manualmente, agregação dos microdados da SSP e integração
das três fontes na base final. A agregação da SSP é a etapa demorada, pois
percorre milhões de linhas, de modo que o seu resultado fica salvo em
`data/processed/` e só é refeito com `--forcar`. Caso falte algum arquivo
manual, o pipeline interrompe na etapa 2 e informa qual portal consultar.

### 3.2 Notebooks

```
notebooks/01_validacao_temporal.ipynb        Fase 1 — Figura 1
notebooks/02_exploratoria.ipynb              Fase 2 — Tabela 2 e Figura 2
notebooks/03_preprocessamento.ipynb          Fase 3 — Figura 3 e matriz_modelagem.csv
notebooks/03b_apendice_escalonadores.ipynb   Apêndice — StandardScaler e RobustScaler
```

Todos operam sobre `data/processed/` e nenhum reprocessa microdado, razão
pela qual devem ser executados após o `main.py`. As figuras são desenhadas
por funções de `src/figuras.py`, uma por figura, e salvas em `figuras/` em
formato pronto para o Overleaf.

> **Verifique o kernel.** Se há mais de um Python instalado na máquina e nem
> todos têm as dependências. Se o notebook retornar `ModuleNotFoundError` no
> primeiro import, use *Select Kernel* e selecione o interpretador em que o
> `pip install -r requirements.txt` foi executado. A primeira célula imprime
> `sys.executable` justamente para essa conferência.

## 4. Saídas geradas

### 4.1 `data/processed/`

| Arquivo | Conteúdo | Gerado por |
|---|---|---|
| `ssp_painel.csv` | município × ano × **mês** × natureza → contagem de ocorrências | `main.py` |
| `ssp_textura.csv` | município × ano → local e período das ocorrências | `main.py` |
| `ssp_complementar.csv` | município × ano → veículos e celulares subtraídos | `main.py` |
| `ssp_cobertura.csv` | ano → nº de meses observados, origem de `exposicao_anos` | `main.py` |
| **`base_final.csv`** | **645 municípios × 54 colunas — uma linha por município** | `main.py` |
| `dicionario_base.csv` | coluna → bloco, tipo e papel na modelagem | `main.py` |
| `relatorio_base.txt` | ausentes, zero-inflação, balanço de features e pesos por bloco | `main.py` |
| `tabela2_descritivas.csv` | descritivas e percentual de zeros das 9 taxas (Tabela 2 do artigo) | notebook 02 |
| `matriz_modelagem.csv` | 644 municípios × 22 features transformadas e ponderadas, mais 2 colunas de identificação | notebook 03 |

Duas observações sobre a leitura desses arquivos. Primeiro, **o painel é
mensal e a base é anual**: o `merge_bases.py` soma sobre o mês, e as
ocorrências sem mês informado recebem `mes = 0`, de modo que continuam no
total anual; análises de série mensal devem filtrar `mes > 0`. Segundo, **o
painel cobre 2022 e a base não**, pois o filtro `ANOS_JANELA` descarta o ano
de controle antes da integração.

A diferença entre as 645 linhas da `base_final.csv` e os 644 municípios da
`matriz_modelagem.csv` é a capital, fiscalizada pelo TCM-SP e, por isso, sem
nota do IEGM. Ela permanece na base, marcada por `flag_sem_iegm`, e é
filtrada na modelagem.

### 4.2 `figuras/`

| Arquivo | Conteúdo | Gerado por |
|---|---|---|
| `figura1_serie_mensal.png` | **Figura 1** — total mensal de ocorrências, 2022 a 2025 | notebook 01 |
| `figura1b_serie_por_natureza.png` | mesma série desagregada por natureza criminal | notebook 01 |
| `figura_eda_populacao.png` | distribuição populacional dos municípios | notebook 02 |
| `figura_eda_boxplot_taxas.png` | boxplots das taxas criminais | notebook 02 |
| `figura_distribuicoes_log1p.png` | distribuições antes e depois do `log1p` | notebook 02 |
| `figura2_spearman.png` | **Figura 2** — matriz de correlação de Spearman | notebook 02 |
| `figura_orcamento_blocos.png` | contribuição de cada bloco na distância, com e sem ponderação | notebook 03 |
| `figura3_variancia_pca.png` | **Figura 3** — variância explicada acumulada do PCA | notebook 03 |
| `figura_pc1_pc2.png` | dispersão dos municípios nas duas primeiras componentes | notebook 03 |

## 5. Estrutura de diretórios

```
database-rp2/
├── main.py                    # orquestra as 4 etapas
├── requirements.txt
├── src/
│   ├── config.py              # caminhos, janela temporal, agrupamento de naturezas
│   ├── ibge_sidra.py          # SIDRA — automático
│   ├── parse_ssp.py           # microdados da SSP -> painel mensal (streaming)
│   ├── parse_iegm.py          # .xls legado do IEGM -> conceitos + ordinais
│   ├── merge_bases.py         # une tudo por codigo_ibge -> base final
│   ├── figuras.py             # uma função por figura do artigo
│   └── estilo.py              # estilo do matplotlib + salvar()
├── notebooks/                 # análise (Fases 1 a 3) + apêndice 03b
├── figuras/                   # saída das figuras do artigo
└── data/
    ├── raw/{ssp,ieg-m,ibge}/
    └── processed/
```
