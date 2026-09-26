"""
Estilo das figuras e a função para salvar.

As figuras vão para um artigo impresso, então as cores usadas no
figuras.py são as que ainda dão para ler em preto e branco: "Blues" para
valores crescentes, "RdBu" para correlação e "C0"/"C1" para duas séries.
"""
from pathlib import Path

import matplotlib.pyplot as plt

FIGURAS_DIR = Path(__file__).resolve().parent.parent / "figuras"


def aplicar_estilo() -> None:
    """Chamar uma vez no começo do notebook."""
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({"savefig.dpi": 200, "savefig.bbox": "tight",
                         "font.size": 9, "axes.titlesize": 10})


def salvar(fig, nome: str) -> Path:
    """Salva a figura em figuras/<nome>.png."""
    FIGURAS_DIR.mkdir(parents=True, exist_ok=True)
    caminho = FIGURAS_DIR / f"{nome}.png"
    fig.savefig(caminho)
    return caminho
