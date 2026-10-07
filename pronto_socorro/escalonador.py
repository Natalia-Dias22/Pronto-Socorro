"""Fila por prioridade com preempcao entre fatias de CPU."""

import threading
import time
from collections.abc import Callable
from enum import Enum

from controle import ControleSimulacao
from modelos import Paciente


class PoliticaEscalonamento(str, Enum):
    PRIORIDADE = "Prioridade"
    SJF = "SJF"


def chave_prioridade(paciente: Paciente) -> tuple[int, float, int]:
    """Prioridade atende casos graves primeiro, com risco de starvation."""
    return paciente.prioridade, paciente.chegada, paciente.id


def chave_sjf(paciente: Paciente) -> tuple[float, float, int]:
    """SJF otimiza a espera media, mas ignora a gravidade do paciente."""
    return paciente.restante, paciente.chegada, paciente.id


# Margem usada so para evitar que ruido de ponto flutuante (ex.: 0.5 - 0.1 -
# 0.1 - 0.1 - 0.1 - 0.1 != 0.0 exato) dispare uma preempcao quando os dois
# restantes sao, na pratica, iguais.
_EPSILON = 1e-9


def deve_preemptar_prioridade(atual: Paciente, candidato: Paciente) -> bool:
    return candidato.prioridade < atual.prioridade


def deve_preemptar_sjf(atual: Paciente, candidato: Paciente) -> bool:
    # SRTF: compara SEMPRE o tempo RESTANTE (nunca a duracao total nem a
    # gravidade). O candidato so assume se for estritamente mais rapido do
    # que o que falta para o paciente atual terminar.
    return candidato.restante < atual.restante - _EPSILON


def _normalizar_politica(
    politica: PoliticaEscalonamento | str,
) -> PoliticaEscalonamento:
    if isinstance(politica, PoliticaEscalonamento):
        return politica
    return PoliticaEscalonamento(politica)


def chave_ordenacao(
    paciente: Paciente,
    politica: PoliticaEscalonamento | str = PoliticaEscalonamento.PRIORIDADE,
) -> tuple[int | float, float, int]:
    estrategias = {
        PoliticaEscalonamento.PRIORIDADE: chave_prioridade,
        PoliticaEscalonamento.SJF: chave_sjf,
    }
    return estrategias[_normalizar_politica(politica)](paciente)


def deve_preemptar(
    atual: Paciente,
    candidato: Paciente,
    politica: PoliticaEscalonamento | str = PoliticaEscalonamento.PRIORIDADE,
) -> bool:
    estrategias = {
        PoliticaEscalonamento.PRIORIDADE: deve_preemptar_prioridade,
        PoliticaEscalonamento.SJF: deve_preemptar_sjf,
    }
    return estrategias[_normalizar_politica(politica)](atual, candidato)


class Escalonador:
    """Coordena dois medicos sem polling ativo, usando Condition."""

    def __init__(
        self,
        pacientes: list[Paciente],
        instante_zero: float,
        controle: ControleSimulacao | None = None,
        publicar_evento: Callable[
            [str, int | None, int | None, dict[str, object]], None
        ] | None = None,
        politica: PoliticaEscalonamento | str = PoliticaEscalonamento.PRIORIDADE,
    ) -> None:
        self.instante_zero = instante_zero
        self.controle = controle
        self.publicar_evento = publicar_evento
        self.politica = _normalizar_politica(politica)
        self._condicao = threading.Condition()
        self._fila = list(pacientes)
        self._chegadas_publicadas: set[int] = set()
        self._total = len(pacientes)
        self._concluidos = 0
        self.preempcoes = 0
        if controle is not None:
            controle.registrar_ouvinte(self._acordar)

    def _acordar(self) -> None:
        with self._condicao:
            self._condicao.notify_all()

    def _tempo_simulado(self) -> float:
        if self.controle is not None:
            return self.controle.tempo
        return time.monotonic() - self.instante_zero

    def _anunciar_chegadas(self, agora: float) -> None:
        if self.publicar_evento is None:
            return
        for paciente in self._fila:
            if paciente.chegada <= agora and paciente.id not in self._chegadas_publicadas:
                self._chegadas_publicadas.add(paciente.id)
                self.publicar_evento(
                    "paciente_chegou",
                    None,
                    paciente.id,
                    {
                        "gravidade": paciente.gravidade.name,
                        "prioridade": paciente.prioridade,
                        "chegada": paciente.chegada,
                        "duracao": paciente.duracao,
                        "restante": paciente.restante,
                    },
                )

    def publicar_chegadas(self) -> None:
        """Anuncia admissões em uma thread leve, sem interferir na fila de CPU."""
        with self._condicao:
            while True:
                if self.controle is not None and self.controle.parada:
                    return
                agora = self._tempo_simulado()
                self._anunciar_chegadas(agora)
                pendentes = [
                    paciente.chegada
                    for paciente in self._fila
                    if paciente.id not in self._chegadas_publicadas
                ]
                if not pendentes:
                    return
                if self.controle is not None and self.controle.pausada:
                    timeout = None
                else:
                    velocidade = self.controle.velocidade if self.controle else 1.0
                    timeout = max(0.001, (min(pendentes) - agora) / velocidade)
                self._condicao.wait(timeout=timeout)

    def _chave(self, paciente: Paciente) -> tuple[int | float, float, int]:
        return chave_ordenacao(paciente, self.politica)

    def proximo_paciente(self) -> Paciente | None:
        """Aguarda a chegada de um paciente elegivel sem consumir CPU."""
        with self._condicao:
            while self._concluidos < self._total:
                if self.controle is not None and self.controle.parada:
                    return None
                agora_simulado = self._tempo_simulado()
                self._anunciar_chegadas(agora_simulado)
                elegiveis = [
                    paciente
                    for paciente in self._fila
                    if paciente.chegada <= agora_simulado
                ]
                if elegiveis:
                    escolhido = min(elegiveis, key=self._chave)
                    self._fila.remove(escolhido)
                    return escolhido

                proximas = [
                    paciente.chegada - agora_simulado for paciente in self._fila
                ]
                if self.controle is not None and self.controle.pausada:
                    timeout = None
                elif proximas:
                    velocidade = self.controle.velocidade if self.controle else 1.0
                    timeout = max(0.001, min(proximas) / velocidade)
                else:
                    timeout = None
                # A Condition libera o lock enquanto espera: ha progresso sem busy waiting.
                self._condicao.wait(timeout=timeout)
            return None

    def apos_fatia(self, atual: Paciente) -> Paciente:
        """Reavalia a preempcao segundo a politica ativa ao fim da fatia."""
        with self._condicao:
            agora_simulado = self._tempo_simulado()
            self._anunciar_chegadas(agora_simulado)
            elegiveis = [
                paciente
                for paciente in self._fila
                if paciente.chegada <= agora_simulado
            ]
            if not elegiveis:
                return atual

            melhor = min(elegiveis, key=self._chave)
            if not deve_preemptar(atual, melhor, self.politica):
                return atual

            self._fila.append(atual)
            self._fila.remove(melhor)
            self.preempcoes += 1
            self._condicao.notify_all()
            return melhor

    def concluir(self) -> None:
        with self._condicao:
            self._concluidos += 1
            self._condicao.notify_all()