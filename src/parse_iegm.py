"""
Lê as planilhas do IEGM (TCE-SP) e monta uma linha por município.

OBS: As colunas *_ord são a média dos exercícios disponíveis.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import xlrd

from config import IEGM_DIR, IEGM_GLOB, ESCALA_ORDINAL_IEGM, COLUNAS_IEGM


def _ler_planilha(caminho: Path) -> pd.DataFrame:
    livro = xlrd.open_workbook(str(caminho))
    aba = livro.sheet_by_index(0)
    cabecalho = [str(c).strip().lower() for c in aba.row_values(0)]
    linhas = [aba.row_values(i) for i in range(1, aba.nrows)]
    df = pd.DataFrame(linhas, columns=cabecalho)

    saida = pd.DataFrame({
        "codigo_ibge": df["codigo_municipio"].astype(float).astype(int)
                                             .astype(str),
        "municipio_iegm": df["nome"].astype(str).str.strip(),
        "exercicio_ref": df["exercicio_ref"].astype(float).astype(int),
    })
    if "ano_apuracao" in df.columns:
        saida["ano_apuracao"] = df["ano_apuracao"].astype(float).astype(int)

    for origem, destino in COLUNAS_IEGM.items():
        conceito = df[origem].astype(str).str.strip().str.upper()
        saida[f"{destino}_conceito"] = conceito
        saida[f"{destino}_ord"] = conceito.map(ESCALA_ORDINAL_IEGM)

    return saida


def carregar_iegm(diretorio: Path = IEGM_DIR) -> pd.DataFrame:
    """
    Junta todos os exercícios do IEGM em uma linha por município.
    """
    arquivos = sorted(Path(diretorio).glob(IEGM_GLOB))
    exercicios = [_ler_planilha(a) for a in arquivos]
    longo = pd.concat(exercicios, ignore_index=True)
    anos = sorted(longo["exercicio_ref"].unique())

    cols_ord = [f"{d}_ord" for d in COLUNAS_IEGM.values()]
    cols_conc = [f"{d}_conceito" for d in COLUNAS_IEGM.values()]

    medias = (longo.groupby("codigo_ibge", as_index=False)[cols_ord]
              .mean().round(4))

    # As letras vêm só do exercício mais recente (para as colunas) e as médias, de todos eles.
    recente = longo["exercicio_ref"] == max(anos)
    rotulos = longo.loc[recente, ["codigo_ibge", "municipio_iegm"] + cols_conc]

    saida = rotulos.merge(medias, on="codigo_ibge", how="outer") # outer: mantém município que não apareceu no exercício mais recente


    # Guarda o intervalo de anos como texto (No caso do estudo, "2022-2024").
    def intervalo(serie: pd.Series) -> str:
        v = sorted(serie.dropna().astype(int).unique())
        return str(v[0]) if len(v) == 1 else f"{v[0]}-{v[-1]}"

    saida["iegm_exercicio_ref"] = intervalo(longo["exercicio_ref"])
    if "ano_apuracao" in longo.columns:
        saida["iegm_ano_apuracao"] = intervalo(longo["ano_apuracao"])

    return saida.reset_index(drop=True)


if __name__ == "__main__":
    df = carregar_iegm()
    print(f"{len(df)} municípios | exercícios {df['iegm_exercicio_ref'].iloc[0]}")
