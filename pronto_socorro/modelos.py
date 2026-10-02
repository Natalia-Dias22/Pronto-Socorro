"""Modelos simples usados na simulacao do pronto-socorro."""

from dataclasses import dataclass
from enum import IntEnum


class Gravidade(IntEnum):
    VERMELHO = 0
    AMARELO = 1
    VERDE = 2


@dataclass
class Paciente:
    """Um paciente representa um processo que disputa os medicos (CPUs)."""

    id: int
    gravidade: Gravidade
    duracao: float
    chegada: float
    restante: float
    inicio: float | None = None
    fim: float | None = None
    usa_raio_x: bool = False
    usa_leito: bool = False
    usa_prontuario: bool = False
    recursos_atendidos: bool = False

    @property
    def prioridade(self) -> int:
        return int(self.gravidade)


@dataclass(frozen=True)
class TrechoGantt:
    medico: int
    paciente_id: int
    gravidade: Gravidade
    inicio: float
    fim: float