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
    # Tempo acumulado na fila de prontos, somando cada volta apos uma preempcao.
    espera: float = 0.0
    # Instante da ultima entrada na fila de prontos (chegada ou preempcao).
    entrou_na_fila: float = 0.0
    # Quantas vezes o escalonador entregou o paciente a um medico.
    despachos: int = 0
    # Tempo bloqueado em raio-X, leito e prontuario: nao e fila de prontos nem consulta.
    tempo_recursos: float = 0.0

    @property
    def prioridade(self) -> int:
        return int(self.gravidade)


@dataclass(frozen=True)
class RegistroAtendimento:
    """Retrato imutavel de um paciente concluido; base de todas as metricas."""

    paciente_id: int
    gravidade: Gravidade
    chegada: float
    inicio: float
    fim: float
    espera: float
    duracao: float = 0.0
    tempo_recursos: float = 0.0

    @property
    def retorno(self) -> float:
        return self.fim - self.chegada

    @property
    def resposta(self) -> float:
        return self.inicio - self.chegada

    @classmethod
    def de_paciente(cls, paciente: Paciente) -> "RegistroAtendimento":
        if paciente.inicio is None or paciente.fim is None:
            raise ValueError(f"Paciente {paciente.id} ainda nao foi concluido.")
        return cls(
            paciente_id=paciente.id,
            gravidade=paciente.gravidade,
            chegada=paciente.chegada,
            inicio=paciente.inicio,
            fim=paciente.fim,
            espera=paciente.espera,
            duracao=paciente.duracao,
            tempo_recursos=paciente.tempo_recursos,
        )


@dataclass(frozen=True)
class TrechoGantt:
    medico: int
    paciente_id: int
    gravidade: Gravidade
    inicio: float
    fim: float
