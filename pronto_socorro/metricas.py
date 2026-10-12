"""Calculo e exibicao das metricas dos escalonamentos.

Definicoes do Cap. 5 (Criterios de Scheduling), calculadas sobre os pacientes
concluidos:
- espera: tempo total na fila de prontos, somando cada volta apos preempcao;
- retorno (turnaround): fim - chegada;
- resposta: inicio do primeiro atendimento - chegada.

Terminal e interface usam estas mesmas funcoes, para que o mesmo valor apareca
igual em qualquer lugar.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from modelos import Gravidade, RegistroAtendimento


@dataclass(frozen=True)
class Medias:
    quantidade: int
    espera: float
    retorno: float
    resposta: float


@dataclass(frozen=True)
class Metricas:
    geral: Medias
    por_gravidade: dict[Gravidade, Medias]


def _medias(registros: list[RegistroAtendimento]) -> Medias:
    if not registros:
        return Medias(0, 0.0, 0.0, 0.0)
    quantidade = len(registros)
    return Medias(
        quantidade=quantidade,
        espera=sum(registro.espera for registro in registros) / quantidade,
        retorno=sum(registro.retorno for registro in registros) / quantidade,
        resposta=sum(registro.resposta for registro in registros) / quantidade,
    )


def calcular_metricas(registros: Iterable[RegistroAtendimento]) -> Metricas:
    # Ordem fixa: somas de float dependem da ordem, e o painel (ordem de conclusao)
    # precisa chegar exatamente ao mesmo valor do resultado final (ordem de id).
    lista = sorted(registros, key=lambda registro: registro.paciente_id)
    return Metricas(
        geral=_medias(lista),
        por_gravidade={
            gravidade: _medias([r for r in lista if r.gravidade == gravidade])
            for gravidade in Gravidade
        },
    )


def formatar_segundos(valor: float) -> str:
    return f"{valor:.2f}s"


def formatar_tempos(medias: Medias, vazio: str = "-") -> tuple[str, str, str]:
    """Espera, retorno e resposta formatados; grupo sem concluidos nao vira 0.00s."""
    if medias.quantidade == 0:
        return vazio, vazio, vazio
    return (
        formatar_segundos(medias.espera),
        formatar_segundos(medias.retorno),
        formatar_segundos(medias.resposta),
    )


def formatar_medias(medias: Medias) -> str:
    if medias.quantidade == 0:
        return "—"
    return (
        f"E {formatar_segundos(medias.espera)} · "
        f"R {formatar_segundos(medias.retorno)} · "
        f"Resp {formatar_segundos(medias.resposta)}"
    )


CRITERIOS = (
    ("espera", "Menor espera média na fila"),
    ("retorno", "Menor retorno médio"),
    ("resposta", "Menor resposta média"),
)


def destaques_comparacao(resultados: list[tuple[str, Metricas]]) -> list[str]:
    """Aponta, em frases curtas, quem foi melhor (menor) em cada criterio.

    A decisao usa o valor ja formatado: se dois valores aparecem iguais na tela,
    o resultado e empate.
    """
    if len(resultados) < 2 or any(m.geral.quantidade == 0 for _, m in resultados):
        return []
    frases = []
    for atributo, titulo in CRITERIOS:
        valores = [(nome, getattr(m.geral, atributo)) for nome, m in resultados]
        textos = [formatar_segundos(valor) for _, valor in valores]
        if len(set(textos)) == 1:
            frases.append(f"{titulo}: empate ({textos[0]})")
            continue
        vencedor, menor = min(valores, key=lambda item: item[1])
        outros = ", ".join(
            f"{nome}: {formatar_segundos(valor)}"
            for nome, valor in valores
            if nome != vencedor
        )
        frases.append(f"{titulo}: {vencedor} com {formatar_segundos(menor)} ({outros})")
    vermelhos = [
        (nome, m.por_gravidade[Gravidade.VERMELHO])
        for nome, m in resultados
        if m.por_gravidade[Gravidade.VERMELHO].quantidade
    ]
    if len(vermelhos) == len(resultados):
        frases.append(
            "Espera dos pacientes vermelhos: "
            + " · ".join(f"{nome} {formatar_segundos(m.espera)}" for nome, m in vermelhos)
        )
    return frases


def imprimir_metricas(metricas: Metricas, titulo: str) -> None:
    print(f"\n{titulo}")
    print("Espera = tempo na fila de prontos | Retorno = fim - chegada | Resposta = inicio - chegada")
    print(f"{'Grupo':<10} {'Concl.':>6} {'Espera':>9} {'Retorno':>9} {'Resposta':>9}")
    linhas = [("Geral", metricas.geral)] + [
        (gravidade.name.capitalize(), metricas.por_gravidade[gravidade])
        for gravidade in Gravidade
    ]
    for nome, medias in linhas:
        espera, retorno, resposta = formatar_tempos(medias)
        print(f"{nome:<10} {medias.quantidade:>6} {espera:>9} {retorno:>9} {resposta:>9}")
