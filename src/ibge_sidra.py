"""
Baixa os dados do IBGE pela API do SIDRA. É a única fonte com API, então
este script roda sozinho.

Tabelas usadas:
  6579  população estimada por município. Usamos 2024 como denominador
        das taxas, porque a tabela não tem 2022 nem 2023 (anos de Censo).
  5938  PIB dos municípios (último ano publicado: 2023). Não tem PIB per
        capita pronto, então dividimos o PIB total pela população.
  9923  população urbana e rural do Censo 2022, para a taxa de urbanização.
        Cuidado: a tabela 202 parece a mesma coisa, mas é do Censo 2010.
  9543, 10295, 6805, 6892  alfabetização, renda domiciliar mediana, esgoto
        e lixo, todos do Censo 2022.
"""
from __future__ import annotations

import sys
import pandas as pd
import requests
import sidrapy

from config import (
    UF_CODE_SP, POPULACAO_CSV, PIB_PERCAPITA_CSV, URBANIZACAO_CSV,
    CENSO2022_CSV,
    TABELA_POPULACAO, TABELA_PIB, TABELA_URBANIZACAO,
    ANO_CENSO_URBANIZACAO, ANO_POPULACAO_REF,
    TABELA_ALFABETIZACAO, TABELA_RENDA, TABELA_ESGOTO, TABELA_LIXO,
    ANO_CENSO, CENSO_TOTAL_SEXO, CENSO_TOTAL_COR,
    CENSO_TOTAL_IDADE_ALFAB, CENSO_TOTAL_IDADE_RENDA,
    CENSO_ESGOTO_TOTAL, CENSO_ESGOTO_ADEQUADO,
    CENSO_LIXO_TOTAL, CENSO_LIXO_COLETADO,
)


def _descobrir_variavel(tabela: str, precisa_conter: list[str], nao_pode_conter: list[str] | None = None) -> tuple[str, str]:
    """
    Procura o código de uma variável da tabela pelo nome, na API de
    metadados. `precisa_conter` são trechos que o nome tem que ter;
    `nao_pode_conter` são trechos que não pode ter.
    """
    url = f"https://servicodados.ibge.gov.br/api/v3/agregados/{tabela}/metadados"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    variaveis = resp.json().get("variaveis", [])

    nao_pode_conter = nao_pode_conter or []

    def bate(nome: str) -> bool:
        nome_lower = nome.lower()
        return (
            all(t.lower() in nome_lower for t in precisa_conter)
            and not any(t.lower() in nome_lower for t in nao_pode_conter)
        )

    candidatas = [v for v in variaveis if bate(v.get("nome", ""))]
    if not candidatas:
        disponiveis = [(v.get("id"), v.get("nome")) for v in variaveis]
        raise SystemExit(
            f"Não encontrei nenhuma variável com {precisa_conter!r} (excluindo "
            f"{nao_pode_conter!r}) nos metadados da tabela {tabela}. "
            f"Variáveis disponíveis: {disponiveis}\n"
            f"Ajuste manualmente o filtro em _descobrir_variavel()."
        )
    # Se mais de uma variável bater com o filtro, usamos a primeira.
    var_id, var_nome = candidatas[0]["id"], candidatas[0]["nome"]
    return str(var_id), var_nome


def _descobrir_classificacao(tabela: str, contem: str) -> tuple[str, str]:
    """Procura o código de uma classificação da tabela pelo nome."""
    url = f"https://servicodados.ibge.gov.br/api/v3/agregados/{tabela}/metadados"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    classificacoes = resp.json().get("classificacoes", [])

    contem_lower = contem.lower()
    candidatas = [c for c in classificacoes if contem_lower in c.get("nome", "").lower()]
    if not candidatas:
        disponiveis = [(c.get("id"), c.get("nome")) for c in classificacoes]
        raise SystemExit(
            f"Não encontrei nenhuma classificação com {contem!r} nos metadados "
            f"da tabela {tabela}. Classificações disponíveis: {disponiveis}"
        )
    # Se mais de uma classificação bater, usamos a primeira.
    class_id, class_nome = candidatas[0]["id"], candidatas[0]["nome"]
    return str(class_id), class_nome


def _periodos_disponiveis(tabela: str) -> list[str]:
    """Lista os anos que a tabela tem publicados."""
    url = f"https://servicodados.ibge.gov.br/api/v3/agregados/{tabela}/periodos"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return [str(p["id"]) for p in resp.json()]


def _filtrar_sp(df: pd.DataFrame, col_codigo: str = "D1C") -> pd.DataFrame:
    """Mantém só os municípios de SP (código começa com 35)."""
    return df[df[col_codigo].astype(str).str.startswith(UF_CODE_SP)].copy()


def get_populacao(periodo: str = "last") -> pd.DataFrame:
    """
    População estimada por município de SP.

    Para o denominador das taxas o main() passa o ano de ANO_POPULACAO_REF
    (2024). Com period="last" viria 2026.
    """
    df = sidrapy.get_table(
        table_code=TABELA_POPULACAO,
        territorial_level="6",
        ibge_territorial_code="all",
        period=periodo,
    )
    # O sidrapy devolve um DataFrame com colunas D1C, D1N, V etc.
    df = _filtrar_sp(df)
    df = df.rename(columns={
        "D1C": "codigo_ibge",
        "D1N": "municipio",
        "V": "populacao",
        "D2N": "ano_populacao",
    })
    cols = [c for c in ["codigo_ibge", "municipio", "populacao", "ano_populacao"] if c in df.columns]
    df = df[cols]
    df["populacao"] = pd.to_numeric(df["populacao"], errors="coerce")
    return df.reset_index(drop=True)


def get_pib_total(periodo: str = "last") -> pd.DataFrame:
    """PIB total (R$ 1.000, preços correntes) por município de SP."""
    # A tabela 5938 tem muitas variáveis. Pegamos só o PIB total, sem as
    # variantes de "participação".
    variavel, _ = _descobrir_variavel(
        TABELA_PIB,
        precisa_conter=["produto interno bruto", "preços correntes"],
        nao_pode_conter=["participação"],
    )

    df = sidrapy.get_table(
        table_code=TABELA_PIB,
        territorial_level="6",
        ibge_territorial_code="all",
        variable=variavel,
        period=periodo,
    )
    df = _filtrar_sp(df)
    df = df.rename(columns={
        "D1C": "codigo_ibge",
        "D1N": "municipio",
        "V": "pib_total_mil_reais",
        "D2N": "ano_pib",
    })
    cols = [c for c in ["codigo_ibge", "municipio", "pib_total_mil_reais", "ano_pib"] if c in df.columns]
    df = df[cols]
    df["pib_total_mil_reais"] = pd.to_numeric(df["pib_total_mil_reais"], errors="coerce")
    return df.reset_index(drop=True)


def get_pib_percapita() -> pd.DataFrame:
    """
    PIB per capita por município de SP.

    O SIDRA não tem PIB per capita por município, então calculamos: PIB
    total (tabela 5938) dividido pela população (tabela 6579) do mesmo ano
    do PIB, ou do ano mais próximo se aquele não existir.
    """
    pib_total = get_pib_total()

    anos_pib = pib_total["ano_pib"].dropna().unique() if "ano_pib" in pib_total.columns else []
    if len(anos_pib) != 1:
        raise SystemExit(
            f"Esperava um único ano de referência no PIB total, mas veio "
            f"{list(anos_pib)}. Ajuste get_pib_percapita() para tratar múltiplos anos."
        )
    ano_pib = str(anos_pib[0])

    # Se o ano do PIB não existir na tabela de população, usamos o ano mais
    # recente antes dele.
    periodos_pop = _periodos_disponiveis(TABELA_POPULACAO)
    if ano_pib in periodos_pop:
        periodo_pop = ano_pib
    else:
        anteriores = [p for p in periodos_pop if p.isdigit() and int(p) <= int(ano_pib)]
        if not anteriores:
            raise SystemExit(
                f"Ano do PIB ({ano_pib}) não está nos períodos da tabela 6579 "
                f"({periodos_pop}) e não achei nenhum período anterior pra usar "
                f"como aproximação. Ajuste manualmente get_pib_percapita()."
            )
        periodo_pop = max(anteriores, key=int)

    populacao_ano_pib = get_populacao(periodo=periodo_pop)

    df = pib_total.merge(
        populacao_ano_pib[["codigo_ibge", "populacao"]],
        on="codigo_ibge",
        how="left",
    )
    df["pib_percapita"] = (df["pib_total_mil_reais"] * 1000) / df["populacao"]
    cols = ["codigo_ibge", "municipio", "pib_percapita", "pib_total_mil_reais", "populacao", "ano_pib"]
    return df[[c for c in cols if c in df.columns]].reset_index(drop=True)


def get_urbanizacao(periodo: str = ANO_CENSO_URBANIZACAO) -> pd.DataFrame:
    """
    Taxa de urbanização (%) por município, do Censo 2022 (tabela 9923).

    Não usar a tabela 202: ela é do Censo 2010 e period="last" devolveria
    2010 sem avisar.
    """
    disponiveis = _periodos_disponiveis(TABELA_URBANIZACAO)
    if periodo not in disponiveis:
        raise SystemExit(
            f"A tabela {TABELA_URBANIZACAO} não publica o período {periodo}. "
            f"Períodos disponíveis: {disponiveis}. Ajuste "
            "ANO_CENSO_URBANIZACAO em config.py."
        )

    # Sem pedir a classificação, o SIDRA devolve só o total. Precisamos da
    # quebra urbana/rural.
    class_id, _ = _descobrir_classificacao(TABELA_URBANIZACAO,
                                           "situação do domicílio")
    # Pegamos a variável de contagem (pessoas) e calculamos a % nós mesmos.
    variavel, _ = _descobrir_variavel(
        TABELA_URBANIZACAO,
        precisa_conter=["população residente"],
        nao_pode_conter=["percentual"],
    )

    df = sidrapy.get_table(
        table_code=TABELA_URBANIZACAO,
        territorial_level="6",
        ibge_territorial_code="all",
        variable=variavel,
        classification=f"{class_id}/all",
        period=periodo,
    )
    # Filtrar por SP também remove a linha de cabeçalho que o sidrapy às
    # vezes deixa no começo.
    df = _filtrar_sp(df)
    df["V"] = pd.to_numeric(df["V"], errors="coerce")

    # Descobre qual coluna tem "Urbana"/"Rural"/"Total" olhando o conteúdo,
    # porque a posição muda de tabela para tabela.
    col_categoria = None
    candidatas_cat = [c for c in df.columns if c.startswith("D") and c.endswith("N") and c != "D1N"]
    for candidate in candidatas_cat:
        valores = set(str(v).strip().lower() for v in df[candidate].dropna().unique())
        if "urbana" in valores and "total" in valores:
            col_categoria = candidate
            break
    if col_categoria is None:
        detalhes = {c: sorted(df[c].dropna().unique().tolist())[:10] for c in candidatas_cat}
        raise SystemExit(
            "Não identifiquei a coluna de situação do domicílio (nenhuma "
            f"coluna com valores 'Urbana'/'Total'). Colunas e valores: {detalhes}"
        )

    pivot = df.pivot_table(
        index=["D1C", "D1N"], columns=col_categoria, values="V", aggfunc="sum"
    ).reset_index()
    pivot = pivot.rename(columns={"D1C": "codigo_ibge", "D1N": "municipio"})

    col_urbana = next((c for c in pivot.columns if "urbana" in str(c).lower()), None)
    col_total = next((c for c in pivot.columns if "total" in str(c).lower()), None)
    if col_urbana is None or col_total is None:
        raise SystemExit(
            "Não encontrei colunas 'Urbana' e/ou 'Total' após o pivot. "
            f"Colunas: {list(pivot.columns)}."
        )

    pivot["taxa_urbanizacao"] = (pivot[col_urbana] / pivot[col_total]) * 100
    return pivot[["codigo_ibge", "municipio", "taxa_urbanizacao"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Censo 2022: outros indicadores socioeconômicos
# ---------------------------------------------------------------------------

def _censo(tabela: str, variavel: str, classificacoes: dict[str, str],
           periodo: str = ANO_CENSO) -> pd.DataFrame:
    """
    Consulta uma tabela do Censo, já filtrada para SP e com o valor
    convertido em número. O SIDRA usa "-", "..." e "X" para dado ausente;
    isso vira NaN.
    """
    df = sidrapy.get_table(
        table_code=tabela,
        territorial_level="6",
        ibge_territorial_code="all",
        variable=variavel,
        classifications=classificacoes,
        period=periodo,
    )
    df = _filtrar_sp(df)
    df["V"] = pd.to_numeric(df["V"], errors="coerce")
    return df


def _coluna_da_classificacao(df: pd.DataFrame, ids: list[str]) -> str:
    """
    Descobre qual coluna D*C tem a classificação pedida: é a que só contém
    os códigos das categorias que pedimos. A posição muda de tabela para
    tabela, por isso olhamos o conteúdo.
    """
    alvo = set(ids)
    for col in df.columns:
        if col.startswith("D") and col.endswith("C") and col != "D1C":
            if set(df[col].astype(str).unique()) <= alvo:
                return col
    raise SystemExit(f"Nenhuma coluna com as categorias {ids}. "
                     f"Colunas: {list(df.columns)}")


def _percentual(tabela: str, variavel: str, classificacao: str,
                total: str, numerador: list[str], nome: str) -> pd.DataFrame:
    """% de domicílios nas categorias `numerador` sobre o `total`."""
    pedidas = [total] + numerador
    df = _censo(tabela, variavel, {classificacao: ",".join(pedidas)})
    col = _coluna_da_classificacao(df, pedidas)
    largo = df.pivot_table(index="D1C", columns=col, values="V",
                           aggfunc="sum")
    largo.columns = largo.columns.astype(str)
    pct = largo[numerador].sum(axis=1) / largo[total] * 100
    return (pct.rename(nome).reset_index()
               .rename(columns={"D1C": "codigo_ibge"}))


def get_censo_2022() -> pd.DataFrame:
    """
    Quatro indicadores do Censo 2022 por município de SP:

      taxa_alfabetizacao        % de pessoas de 15 anos ou mais alfabetizadas
      renda_domiciliar_mediana  renda domiciliar per capita mediana (R$)
      prop_esgoto_adequado      % de domicílios com rede geral ou fossa séptica
      prop_lixo_coletado        % de domicílios com lixo coletado

    Os dois primeiros já vêm prontos (pedimos "Total" em sexo, cor e idade).
    Os dois últimos são calculados a partir das contagens de domicílios.
    """
    alf = _censo(TABELA_ALFABETIZACAO, "2513", {
        "2": CENSO_TOTAL_SEXO, "86": CENSO_TOTAL_COR,
        "287": CENSO_TOTAL_IDADE_ALFAB,
    })
    alf = alf[["D1C", "V"]].rename(columns={"D1C": "codigo_ibge",
                                            "V": "taxa_alfabetizacao"})

    ren = _censo(TABELA_RENDA, "13534", {
        "2": CENSO_TOTAL_SEXO, "86": CENSO_TOTAL_COR,
        "58": CENSO_TOTAL_IDADE_RENDA,
    })
    ren = ren[["D1C", "V"]].rename(columns={"D1C": "codigo_ibge",
                                            "V": "renda_domiciliar_mediana"})

    esg = _percentual(TABELA_ESGOTO, "381", "11558", CENSO_ESGOTO_TOTAL,
                      CENSO_ESGOTO_ADEQUADO, "prop_esgoto_adequado")

    lixo = _percentual(TABELA_LIXO, "381", "67", CENSO_LIXO_TOTAL,
                       CENSO_LIXO_COLETADO, "prop_lixo_coletado")

    df = (alf.merge(ren, on="codigo_ibge", how="outer")
             .merge(esg, on="codigo_ibge", how="outer")
             .merge(lixo, on="codigo_ibge", how="outer"))
    df["ano_censo"] = int(ANO_CENSO)
    return df.reset_index(drop=True)


def main() -> None:
    # Denominador das taxas: população de ANO_POPULACAO_REF (2024).
    periodo_pop = ("last" if ANO_POPULACAO_REF is None
                   else str(ANO_POPULACAO_REF))
    populacao = get_populacao(periodo=periodo_pop)
    populacao.to_csv(POPULACAO_CSV, index=False)
    print(f"-> salvo em {POPULACAO_CSV} ({len(populacao)} municípios)")

    pib = get_pib_percapita()
    pib.to_csv(PIB_PERCAPITA_CSV, index=False)
    print(f"-> salvo em {PIB_PERCAPITA_CSV} ({len(pib)} municípios)")

    urban = get_urbanizacao()
    urban.to_csv(URBANIZACAO_CSV, index=False)
    print(f"-> salvo em {URBANIZACAO_CSV} ({len(urban)} municípios)")

    censo = get_censo_2022()
    censo.to_csv(CENSO2022_CSV, index=False)
    print(f"-> salvo em {CENSO2022_CSV} ({len(censo)} municípios)")


if __name__ == "__main__":
    sys.path.insert(0, str(__file__).replace("ibge_sidra.py", ""))
    main()
