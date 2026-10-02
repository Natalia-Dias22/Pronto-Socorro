"""Fila por prioridade com preempcao entre fatias de CPU."""

import threading
import time
from collections.abc import Callable

from controle import ControleSimulacao
from modelos import Paciente


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
    ) -> None:
        self.instante_zero = instante_zero
        self.controle = controle
        self.publicar_evento = publicar_evento
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

    @staticmethod
    def _chave(paciente: Paciente) -> tuple[int, float, int]:
        return paciente.prioridade, paciente.chegada, paciente.id

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
        """Troca o processo se alguem mais grave ja estiver elegivel."""
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
            if melhor.prioridade >= atual.prioridade:
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