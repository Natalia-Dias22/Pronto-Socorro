"""Grafico de Gantt opcional; matplotlib e importado somente se solicitado."""

from modelos import Gravidade, TrechoGantt


def mostrar_gantt(trechos: list[TrechoGantt], titulo: str) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as erro:
        raise RuntimeError(
            "O Gantt requer matplotlib. Instale-o com: pip install matplotlib"
        ) from erro

    cores = {
        Gravidade.VERMELHO: "#d1495b",
        Gravidade.AMARELO: "#edae49",
        Gravidade.VERDE: "#2a9d8f",
    }
    figura, eixo = plt.subplots(figsize=(11, 3.5))
    for trecho in trechos:
        eixo.barh(
            trecho.medico,
            trecho.fim - trecho.inicio,
            left=trecho.inicio,
            color=cores[trecho.gravidade],
            edgecolor="white",
        )
        eixo.text(
            trecho.inicio + (trecho.fim - trecho.inicio) / 2,
            trecho.medico,
            f"P{trecho.paciente_id}",
            ha="center",
            va="center",
            fontsize=8,
        )
    eixo.set_yticks([1, 2], ["Medico 1", "Medico 2"])
    eixo.set_xlabel("Tempo simulado (s)")
    eixo.set_title(titulo)
    eixo.grid(axis="x", alpha=0.25)
    figura.tight_layout()
    plt.show()