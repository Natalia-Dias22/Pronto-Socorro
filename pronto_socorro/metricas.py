"""Calculo e exibicao das metricas dos escalonamentos."""

from dataclasses import dataclass

from modelos import Gravidade, Paciente


@dataclass(frozen=True)
class Metricas:
    espera_media: float
    retorno_medio: float
    resposta_media: float
    por_gravidade: dict[Gravidade, tuple[float, float, float]]


def calcular_metricas(pacientes: list[Paciente]) -> Metricas:
    esperas = [max(0.0, (p.inicio or 0.0) - p.chegada) for p in pacientes]
    retornos = [max(0.0, (p.fim or 0.0) - p.chegada) for p in pacientes]
    respostas = list(esperas)
    por_gravidade: dict[Gravidade, tuple[float, float, float]] = {}
    for gravidade in Gravidade:
        grupo = [p for p in pacientes if p.gravidade == gravidade]
        if not grupo:
            por_gravidade[gravidade] = (0.0, 0.0, 0.0)
            continue
        grupo_espera = [max(0.0, (p.inicio or 0.0) - p.chegada) for p in grupo]
        grupo_retorno = [max(0.0, (p.fim or 0.0) - p.chegada) for p in grupo]
        por_gravidade[gravidade] = (
            sum(grupo_espera) / len(grupo),
            sum(grupo_retorno) / len(grupo),
            sum(grupo_espera) / len(grupo),
        )
    return Metricas(
        espera_media=sum(esperas) / len(pacientes) if pacientes else 0.0,
        retorno_medio=sum(retornos) / len(pacientes) if pacientes else 0.0,
        resposta_media=sum(respostas) / len(pacientes) if pacientes else 0.0,
        por_gravidade=por_gravidade,
    )


def imprimir_metricas(metricas: Metricas, titulo: str) -> None:
    print(f"\n{titulo}")
    print(
        f"Geral        espera={metricas.espera_media:.3f}s"
        f" retorno={metricas.retorno_medio:.3f}s"
        f" resposta={metricas.resposta_media:.3f}s"
    )
    for gravidade in Gravidade:
        espera, retorno, resposta = metricas.por_gravidade[gravidade]
        print(
            f"{gravidade.name:<12} espera={espera:.3f}s"
            f" retorno={retorno:.3f}s resposta={resposta:.3f}s"
        )