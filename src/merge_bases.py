"""
Junta SSP, IEGM e IBGE numa base com uma linha por município.

- A chave é codigo_ibge em todas as fontes. Não juntamos por nome, porque
  o município onde o BO foi registrado nem sempre é o do local do fato.
- As ocorrências viram taxa por 100 mil habitantes por ano:

      taxa = ocorrencias_na_janela / (populacao * exposicao_anos) * 100.000

  exposicao_anos vem de ssp_cobertura.csv (meses observados / 12, somados).
  Assim um ano incompleto não derruba a taxa.
- A base mantém os 645 municípios. Tirar a capital ou os municípios pequenos
  é decisão da análise; aqui eles só recebem uma flag.
"""
from __future__ import annotations

import pandas as pd

from config import (
    POPULACAO_CSV, PIB_PERCAPITA_CSV, URBANIZACAO_CSV, CENSO2022_CSV,
    LIMIAR_REDUNDANCIA,
    SSP_PAINEL_CSV, SSP_TEXTURA_CSV, SSP_COMPLEMENTAR_CSV, SSP_COBERTURA_CSV,
    BASE_FINAL_CSV, DICIONARIO_CSV, RELATORIO_TXT,
    ANOS_JANELA, POPULACAO_MINIMA, CODIGO_CAPITAL,
    TAXA_POR_HABITANTES, GRUPOS_NATUREZA, NATUREZAS_TIER2, COLUNAS_IEGM,
)
from parse_iegm import carregar_iegm
from parse_ssp import normaliza


def _limpa_nome(serie: pd.Series) -> pd.Series:
    """Tira o '- SP' do fim do nome: 'Adamantina - SP' vira 'Adamantina'."""
    return serie.astype(str).str.replace(r"\s*-\s*SP$", "", regex=True).str.strip()


def _codigo(serie: pd.Series) -> pd.Series:
    return serie.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)


# ---------------------------------------------------------------------------

def carregar_ibge() -> pd.DataFrame:
    """Monta a lista dos 645 municípios com os dados do IBGE."""
    pop = pd.read_csv(POPULACAO_CSV)
    pop["codigo_ibge"] = _codigo(pop["codigo_ibge"])
    base = pd.DataFrame({
        "codigo_ibge": pop["codigo_ibge"],
        "municipio": _limpa_nome(pop["municipio"]),
        "populacao": pd.to_numeric(pop["populacao"], errors="coerce"),
        "ano_populacao": pop.get("ano_populacao"),
    }).drop_duplicates(subset="codigo_ibge").reset_index(drop=True)

    # O PIB per capita é recalculado aqui com a população de 2024. O CSV do
    # ibge_sidra.py usa a população de 2021 (a tabela do IBGE não tem 2022
    # nem 2023), e isso deixaria o valor alto demais nas cidades que cresceram.
    pib = pd.read_csv(PIB_PERCAPITA_CSV)
    pib["codigo_ibge"] = _codigo(pib["codigo_ibge"])
    base = base.merge(
        pib[["codigo_ibge", "pib_total_mil_reais", "ano_pib"]],
        on="codigo_ibge", how="left",
    )
    base["pib_percapita"] = (
        pd.to_numeric(base["pib_total_mil_reais"], errors="coerce") * 1000
    ) / base["populacao"]

    urb = pd.read_csv(URBANIZACAO_CSV)
    urb["codigo_ibge"] = _codigo(urb["codigo_ibge"])
    base = base.merge(urb[["codigo_ibge", "taxa_urbanizacao"]],
                      on="codigo_ibge", how="left")

    # Censo 2022: alfabetização, renda mediana, esgoto e lixo.
    censo = pd.read_csv(CENSO2022_CSV)
    censo["codigo_ibge"] = _codigo(censo["codigo_ibge"])
    base = base.merge(censo, on="codigo_ibge", how="left")
    return base


def definir_janela(cobertura: pd.DataFrame) -> tuple[list[int], float]:
    """Devolve os anos da janela e a exposição (anos completos observados)."""
    disponiveis = sorted(cobertura["ano"].astype(int).tolist())
    anos = sorted(ANOS_JANELA) if ANOS_JANELA else disponiveis

    ausentes = [a for a in anos if a not in disponiveis]
    if ausentes:
        raise SystemExit(
            f"ANOS_JANELA pede {ausentes}, mas só há dados da SSP para "
            f"{disponiveis}.\nBaixe os arquivos SPDadosCriminais_<ano>.xlsx "
            "faltantes em data/raw/ssp/ e rode parse_ssp.py de novo."
        )

    meses = cobertura.set_index(cobertura["ano"].astype(int))["n_meses"]
    exposicao = sum(meses[a] / 12.0 for a in anos)
    return anos, exposicao


def agregar_janela(painel: pd.DataFrame, anos: list[int]) -> pd.DataFrame:
    """Soma as ocorrências dos anos da janela por município e grupo."""
    dados = painel[painel["ano"].astype(int).isin(anos)]

    # GRUPOS_NATUREZA tem acento e o painel não. Normalizamos os dois lados.
    mapa = {}
    for grupo, naturezas in GRUPOS_NATUREZA.items():
        for nat in naturezas:
            mapa[normaliza(nat)] = grupo

    dados = dados.assign(grupo=dados["natureza"].map(mapa)).dropna(subset=["grupo"])
    largo = (
        dados.groupby(["codigo_ibge", "grupo"])["ocorrencias"].sum()
        .unstack(fill_value=0).reset_index()
    )
    largo.columns.name = None
    # Se um grupo não tiver nenhuma ocorrência no estado, cria a coluna zerada.
    for grupo in GRUPOS_NATUREZA:
        if grupo not in largo.columns:
            largo[grupo] = 0
    return largo


def montar_base_final() -> tuple[pd.DataFrame, pd.DataFrame, list[int], float]:
    base = carregar_ibge()

    painel = pd.read_csv(SSP_PAINEL_CSV, dtype={"codigo_ibge": str})
    textura = pd.read_csv(SSP_TEXTURA_CSV, dtype={"codigo_ibge": str})
    comp = pd.read_csv(SSP_COMPLEMENTAR_CSV, dtype={"codigo_ibge": str})
    cobertura = pd.read_csv(SSP_COBERTURA_CSV)

    anos, exposicao = definir_janela(cobertura)

    # --- população usada como denominador ---
    ano_pop = base["ano_populacao"].iloc[0]

    # --- taxas de criminalidade ---
    contagens = agregar_janela(painel, anos)
    base = base.merge(contagens, on="codigo_ibge", how="left")
    pessoas_ano = base["populacao"] * exposicao
    for grupo in GRUPOS_NATUREZA:
        base[grupo] = base[grupo].fillna(0)
        base[f"taxa_{grupo}"] = base[grupo] / pessoas_ano * TAXA_POR_HABITANTES
    base["total_ocorrencias_janela"] = base[list(GRUPOS_NATUREZA)].sum(axis=1)
    base = base.drop(columns=list(GRUPOS_NATUREZA))

    # --- proporções sobre local e período ---
    tex = (textura[textura["ano"].astype(int).isin(anos)]
           .groupby("codigo_ibge")[["n_ocorrencias", "n_via_publica",
                                    "n_periodo_conhecido", "n_noturno"]].sum()
           .reset_index())
    base = base.merge(tex, on="codigo_ibge", how="left")
    base["prop_via_publica"] = base["n_via_publica"] / base["n_ocorrencias"]
    base["prop_noturno"] = base["n_noturno"] / base["n_periodo_conhecido"]
    base["cobertura_periodo"] = base["n_periodo_conhecido"] / base["n_ocorrencias"]

    campos_comp = ["veic_furtado", "veic_roubado", "veic_localizado",
                   "veic_subtraido", "veic_moto", "cel_furto", "cel_roubo"]
    cmp_janela = (comp[comp["ano"].astype(int).isin(anos)]
                  .groupby("codigo_ibge")[campos_comp].sum().reset_index())
    base = base.merge(cmp_janela, on="codigo_ibge", how="left")
    for c in campos_comp:
        base[c] = base[c].fillna(0)
    # Se o denominador for zero, a proporção fica NaN (não existe). Usamos
    # where() em vez de replace(0, NA) para a coluna continuar numérica.
    veic_subtraido = base["veic_subtraido"].where(base["veic_subtraido"] > 0)
    n_ocorr = base["n_ocorrencias"].where(base["n_ocorrencias"] > 0)

    base["taxa_recuperacao_veiculo"] = base["veic_localizado"] / veic_subtraido
    base["prop_veiculo_motocicleta"] = base["veic_moto"] / veic_subtraido
    base["prop_celular_em_furto_roubo"] = (
        (base["cel_furto"] + base["cel_roubo"]) / n_ocorr
    )
    base = base.drop(columns=campos_comp + ["n_via_publica", "n_noturno",
                                            "n_periodo_conhecido"])

    # --- IEGM ---
    iegm = carregar_iegm()
    base = base.merge(iegm.drop(columns=["municipio_iegm"]),
                      on="codigo_ibge", how="left")

    # --- flags ---
    base["flag_sem_iegm"] = base["iegm_ord"].isna()
    base["flag_pop_pequena"] = base["populacao"] < POPULACAO_MINIMA
    base["flag_capital"] = base["codigo_ibge"] == CODIGO_CAPITAL
    base["janela_anos"] = "-".join(str(a) for a in (anos[0], anos[-1]))
    base["exposicao_anos"] = round(exposicao, 4)
    base["ano_populacao_ref"] = ano_pop

    base = base.drop(columns=["pib_total_mil_reais"])
    return base, montar_dicionario(base), anos, exposicao


# ---------------------------------------------------------------------------

def montar_dicionario(base: pd.DataFrame) -> pd.DataFrame:
    """
    Monta o dicionário da base: para cada coluna, o bloco, o tipo e o papel
    na modelagem (feature, contexto, flag...).

    Os notebooks leem este arquivo para saber quais colunas são features.
    Assim ninguém precisa listar coluna na mão.
    """
    linhas = []

    def add(col, bloco, tipo, papel, desc):
        if col in base.columns:
            linhas.append({"coluna": col, "bloco": bloco, "tipo": tipo,
                           "papel": papel, "descricao": desc})

    add("codigo_ibge", "identificacao", "str", "chave", "Código IBGE de 7 dígitos")
    add("municipio", "identificacao", "str", "rotulo", "Nome oficial IBGE")
    add("populacao", "identificacao", "int", "contexto", "População residente (denominador)")
    add("ano_populacao", "identificacao", "int", "metadado", "Ano da estimativa populacional")

    rotulos = {
        "cvli": "Crimes violentos letais intencionais (homicídio doloso + latrocínio + lesão seguida de morte)",
        "tentativa_homicidio": "Tentativa de homicídio",
        "lesao_dolosa": "Lesão corporal dolosa",
        "roubo_outros": "Roubo (exceto veículo e carga)",
        "roubo_veiculo": "Roubo de veículo",
        "roubo_carga": "Roubo de carga",
        "furto_outros": "Furto (exceto veículo e carga)",
        "furto_veiculo": "Furto de veículo",
        "estupro_total": "Estupro + estupro de vulnerável",
        "trafico": "Tráfico de entorpecentes (mede também intensidade de policiamento)",
    }
    for grupo, desc in rotulos.items():
        papel = "feature_tier2" if grupo in NATUREZAS_TIER2 else "feature"
        add(f"taxa_{grupo}", "criminalidade", "float", papel,
            f"{desc} -- por 100 mil hab./ano")

    add("prop_via_publica", "textura", "float", "validacao_externa",
        "Proporção de ocorrências com DESCR_SUBTIPOLOCAL='Via Pública' "
        "(sugerida como validação externa). DESCR_SUBTIPOLOCAL e não "
        "DESCR_TIPOLOCAL: este último só existe no export de 2025")
    # Os números das descrições são calculados aqui, para não ficarem
    # desatualizados.
    cobertura_med = base["cobertura_periodo"].median()
    add("prop_noturno", "textura", "float", "feature_tier2",
        "Proporção de ocorrências noturnas entre as de período conhecido. "
        f"Cobertura baixa (mediana {cobertura_med:.0%}); não promover a "
        "feature")
    add("cobertura_periodo", "textura", "float", "qualidade",
        "Fração de ocorrências com período preenchido. Mediana na janela: "
        f"{cobertura_med:.2f}")

    # A razão localizados/subtraídos passa de 1 em muitos municípios, porque
    # um carro roubado numa cidade pode ser localizado em outra. Então ela
    # não mede a efetividade da polícia local.
    recup = base["taxa_recuperacao_veiculo"].dropna()
    acima_de_um = int((recup > 1).sum())
    add("taxa_recuperacao_veiculo", "textura", "float", "contexto",
        "Veículos localizados no município / veículos subtraídos no "
        f"município. Excede 1 em {acima_de_um} de {len(recup)} municípios "
        f"({acima_de_um / len(recup):.0%}), pois inclui veículos subtraídos "
        "em outros municípios. NÃO mede efetividade institucional")
    add("prop_veiculo_motocicleta", "textura", "float", "feature_tier2",
        "Participação de motos entre os veículos subtraídos")
    add("prop_celular_em_furto_roubo", "textura", "float", "feature_tier2",
        "Ocorrências com celular subtraído / total de ocorrências")

    # O PIB per capita fica muito alto em cidades com uma usina ou um polo
    # industrial, então não representa bem a renda das famílias. Ele só fica
    # como feature se não for redundante com a renda domiciliar mediana.
    rho_pib_renda = base["pib_percapita"].corr(
        base["renda_domiciliar_mediana"], method="spearman")
    papel_pib = ("contexto" if abs(rho_pib_renda) > LIMIAR_REDUNDANCIA
                 else "feature")
    add("pib_percapita", "socioeconomico", "float", papel_pib,
        "PIB per capita em R$ (recalculado com a população de referência). "
        "Distorcido por enclaves industriais; Spearman com "
        f"renda_domiciliar_mediana = {rho_pib_renda:.2f}")
    add("taxa_urbanizacao", "socioeconomico", "float", "feature",
        "% da população em domicílio urbano (Censo 2022, tabela SIDRA 9923)")
    # A população fica fora das features de propósito: todo o resto já é por
    # habitante, e ela faria os grupos virarem "cidade grande x pequena".
    add("ano_pib", "socioeconomico", "int", "metadado", "Ano de referência do PIB")

    add("taxa_alfabetizacao", "socioeconomico", "float", "feature",
        "% de pessoas de 15 anos ou mais alfabetizadas "
        "(Censo 2022, SIDRA 9543)")
    add("renda_domiciliar_mediana", "socioeconomico", "float", "feature",
        "Rendimento domiciliar per capita mediano, em R$ "
        "(Censo 2022, SIDRA 10295)")
    add("prop_esgoto_adequado", "socioeconomico", "float", "feature",
        "% de domicílios com rede geral de esgoto ou fossa séptica "
        "(Censo 2022, SIDRA 6805)")
    add("prop_lixo_coletado", "socioeconomico", "float", "feature",
        "% de domicílios com lixo coletado (Censo 2022, SIDRA 6892)")
    add("ano_censo", "socioeconomico", "int", "metadado",
        "Ano do Censo dos quatro indicadores acima")

    # O índice geral do IEGM é calculado a partir das 7 dimensões. Usar os
    # dois como feature contaria a mesma coisa duas vezes. Ficam as
    # dimensões; o índice geral fica como contexto.
    for destino in COLUNAS_IEGM.values():
        papel_ord = "contexto" if destino == "iegm" else "feature"
        add(f"{destino}_ord", "gestao", "ordinal_1_5", papel_ord,
            f"IEGM {destino}: conceito em ordinal (C=1 ... A=5), MÉDIA dos "
            "exercícios disponíveis (ver iegm_exercicio_ref)"
            + (". Fora das features: é composto pelas 7 dimensões, que já "
               "entram" if destino == "iegm" else ""))
        add(f"{destino}_conceito", "gestao", "str", "rotulo",
            f"IEGM {destino}: conceito em letra do exercício MAIS RECENTE -- "
            "rótulo legível; não corresponde a _ord, que é a média")
    add("iegm_exercicio_ref", "gestao", "str", "metadado",
        "Exercício(s) avaliado(s) pelo IEGM, como intervalo")
    add("iegm_ano_apuracao", "gestao", "str", "metadado",
        "Ano(s) de apuração do IEGM, como intervalo")

    add("total_ocorrencias_janela", "qualidade", "int", "qualidade",
        "Soma bruta das ocorrências do Bloco B -- detecta subnotificação")
    add("n_ocorrencias", "qualidade", "int", "qualidade",
        "Total de ocorrências de qualquer natureza no município/janela")
    add("flag_sem_iegm", "qualidade", "bool", "flag",
        "Sem nota IEGM (apenas a capital: fiscalizada pelo TCM-SP)")
    add("flag_pop_pequena", "qualidade", "bool", "flag",
        f"População < {POPULACAO_MINIMA} -- sujeito ao problema dos números pequenos")
    add("flag_capital", "qualidade", "bool", "flag", "É o município de São Paulo")
    add("janela_anos", "qualidade", "str", "metadado", "Janela temporal da SSP")
    add("exposicao_anos", "qualidade", "float", "metadado",
        "Anos-equivalentes de exposição (meses observados / 12, somados)")
    add("ano_populacao_ref", "qualidade", "int", "metadado",
        "Ano da população usada como denominador")

    return pd.DataFrame(linhas)


def relatorio(base: pd.DataFrame, dic: pd.DataFrame, anos, exposicao) -> str:
    L = []
    L.append("=" * 68)
    L.append("BASE FINAL -- perfis de municípios paulistas")
    L.append("=" * 68)
    L.append(f"Municípios: {len(base)}   Colunas: {len(base.columns)}")

    # Cada fonte tem um ano de referência diferente. Isso vai como limitação
    # no artigo.
    L.append("\n--- Anos de referência por fonte ---")
    L.append(f"  Criminalidade (SSP)   {anos[0]}-{anos[-1]}  "
             f"({exposicao:.3f} ano(s)-equivalente(s) de exposição)")
    L.append(f"  Gestão (IEGM/TCE-SP)  exercícios "
             f"{base['iegm_exercicio_ref'].dropna().iloc[0]} "
             f"(apurados em {base['iegm_ano_apuracao'].dropna().iloc[0]})")
    L.append(f"  População (denominador das taxas)  "
             f"{base['ano_populacao'].iloc[0]}")
    L.append(f"  PIB (SIDRA 5938)      {base['ano_pib'].dropna().iloc[0]:.0f}")
    L.append("  Urbanização (SIDRA 9923)  Censo 2022")
    L.append("  Alfabetização, renda mediana, esgoto e lixo  Censo 2022")
    if exposicao < 0.999 * len(anos):
        L.append("\n  *** ATENÇÃO: a janela contém ano(s) INCOMPLETO(S). As taxas já")
        L.append("      estão anualizadas pela exposição, mas herdam viés sazonal.")
        L.append("      Trate esta base como PROVISÓRIA até baixar anos completos.")

    L.append("\n--- Municípios aptos à modelagem ---")
    aptos = base[~base["flag_sem_iegm"]]
    L.append(f"Com todos os blocos (crime + socioeconômico + gestão): {len(aptos)}")
    L.append(f"Sem IEGM (fora da modelagem): {int(base['flag_sem_iegm'].sum())} "
             f"-> {', '.join(base.loc[base['flag_sem_iegm'], 'municipio'])}")
    L.append(f"Com população < {POPULACAO_MINIMA:,}: "
             f"{int(base['flag_pop_pequena'].sum())} "
             f"({base['flag_pop_pequena'].mean():.1%}) -- mantidos na base, "
             "usar em análise de sensibilidade")

    L.append("\n--- Valores ausentes ---")
    ausentes = base.isna().sum()
    ausentes = ausentes[ausentes > 0]
    if len(ausentes):
        for col, n in ausentes.items():
            L.append(f"  {col:34s} {n:4d} ({n / len(base):.1%})")
    else:
        L.append("  nenhum")

    L.append("\n--- Bloco B: taxas por 100 mil hab./ano ---")
    L.append(f"  {'variável':30s} {'média':>9s} {'mediana':>9s} {'máx':>10s} {'zeros':>7s}")
    taxas_crime = [c for c in dic.loc[dic["bloco"] == "criminalidade", "coluna"]
                   if c in base.columns]
    for col in taxas_crime:
        s = base[col]
        zeros = int((s == 0).sum())
        L.append(f"  {col:30s} {s.mean():9.1f} {s.median():9.1f} "
                 f"{s.max():10.1f} {zeros:5d} ({zeros / len(base):.0%})")
    L.append("\n  Zeros elevados = zero-inflação. Ela cai ao ampliar a janela:")
    L.append("  estimativa Poisson para CVLI -- 1 ano: 46% | 2 anos: 31% | "
             "3 anos: 23% | 5 anos: 14%.")

    L.append("\n--- pib_percapita x renda_domiciliar_mediana ---")
    rho = base["pib_percapita"].corr(base["renda_domiciliar_mediana"],
                                     method="spearman")
    papel_pib = dic.loc[dic["coluna"] == "pib_percapita", "papel"].iloc[0]
    L.append(f"  Spearman = {rho:.3f}  (limiar de redundância "
             f"{LIMIAR_REDUNDANCIA}) -> pib_percapita como '{papel_pib}'")

    L.append("\n--- Espaço de features (etapa única) ---")
    feats = dic[dic["papel"] == "feature"]
    for bloco, grupo in feats.groupby("bloco"):
        L.append(f"  {bloco:18s} {len(grupo):2d} features -> peso sugerido "
                 f"1/sqrt({len(grupo)}) = {1 / len(grupo) ** 0.5:.3f}")
    L.append("  Sem peso por bloco, cada bloco influencia a distância na")
    L.append("  proporção do nº de colunas que a fonte por acaso tem.")
    L.append("\n  Transformações aplicadas NO NOTEBOOK DE MODELAGEM (não aqui):")
    L.append("    log1p nas taxas criminais e nas duas variáveis em R$ (PIB per")
    L.append("    capita e renda domiciliar mediana), depois StandardScaler")
    L.append("    ajustado só no subconjunto clusterizado, e peso 1/sqrt(n) por")
    L.append("    bloco.")
    return "\n".join(L)


def main() -> None:
    base, dic, anos, exposicao = montar_base_final()
    base.to_csv(BASE_FINAL_CSV, index=False, encoding="utf-8")
    dic.to_csv(DICIONARIO_CSV, index=False, encoding="utf-8")
    texto = relatorio(base, dic, anos, exposicao)
    RELATORIO_TXT.write_text(texto, encoding="utf-8")
    print(f"\n-> {BASE_FINAL_CSV}")
    print(f"-> {DICIONARIO_CSV}")
    print(f"-> {RELATORIO_TXT}\n")
    print(texto)


if __name__ == "__main__":
    main()
