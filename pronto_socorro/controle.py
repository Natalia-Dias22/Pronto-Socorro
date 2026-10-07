"""Controle de tempo, pausa e cancelamento da simulacao concorrente."""

import threading
import time
from collections.abc import Callable

Evento = tuple[str, int | None, int | None, dict[str, object], float]
CallbackEvento = Callable[[Evento], None]


class ControleSimulacao:
    def __init__(self, velocidade: float = 1.0) -> None:
        self._condicao = threading.Condition()
        self._velocidade = velocidade
        self._pausada = False
        self._parada = False
        self._tempo_simulado = 0.0
        self._ultima_atualizacao = time.monotonic()
        self._ouvintes: list[Callable[[], None]] = []

    def _avancar_tempo(self) -> None:
        agora = time.monotonic()
        if not self._pausada and not self._parada:
            self._tempo_simulado += (agora - self._ultima_atualizacao) * self._velocidade
        self._ultima_atualizacao = agora

    def reiniciar_relogio(self) -> None:
        """Zera o tempo simulado e resincroniza a referencia de parede com
        o instante atual.

        Precisa ser chamado logo antes de uma politica comecar a rodar de
        fato quando o ControleSimulacao foi CRIADO com antecedencia mas so
        passa a ser usado depois de um atraso real (ex.: na comparacao de
        politicas, os dois ControleSimulacao sao criados juntos, mas a
        segunda politica so comeca a rodar depois que a primeira termina
        por completo, o que pode levar varios segundos reais). Sem este
        reinicio, a primeira leitura de 'tempo' da segunda politica
        contabilizaria todo esse atraso ocioso como se fosse tempo
        simulado ja decorrido: isso inflaria o 'inicio' de todos os
        pacientes (e, portanto, a espera media) e, pior, faria parecer que
        TODAS as chegadas ja tinham acontecido antes mesmo do primeiro
        atendimento comecar -- eliminando qualquer chance de uma chegada
        ocorrer DURANTE uma consulta e disparar uma preempcao por tempo.
        """
        with self._condicao:
            self._tempo_simulado = 0.0
            self._ultima_atualizacao = time.monotonic()
            self._condicao.notify_all()

    @property
    def tempo(self) -> float:
        with self._condicao:
            self._avancar_tempo()
            return self._tempo_simulado

    @property
    def velocidade(self) -> float:
        with self._condicao:
            return self._velocidade

    @property
    def pausada(self) -> bool:
        with self._condicao:
            return self._pausada

    @property
    def parada(self) -> bool:
        with self._condicao:
            return self._parada

    def registrar_ouvinte(self, callback: Callable[[], None]) -> None:
        with self._condicao:
            self._ouvintes.append(callback)

    def _notificar_ouvintes(self) -> None:
        for callback in tuple(self._ouvintes):
            callback()

    def definir_velocidade(self, velocidade: float) -> None:
        with self._condicao:
            self._avancar_tempo()
            self._velocidade = max(0.25, min(4.0, velocidade))
            self._condicao.notify_all()
        self._notificar_ouvintes()

    def definir_pausa(self, pausada: bool) -> None:
        with self._condicao:
            self._avancar_tempo()
            self._pausada = pausada
            self._condicao.notify_all()
        self._notificar_ouvintes()

    def parar(self) -> None:
        with self._condicao:
            self._avancar_tempo()
            self._parada = True
            self._pausada = False
            self._condicao.notify_all()
        self._notificar_ouvintes()

    def aguardar(self, duracao_simulada: float) -> bool:
        """Espera tempo simulado; retorna False se a simulacao foi cancelada."""
        with self._condicao:
            self._avancar_tempo()
            alvo = self._tempo_simulado + max(0.0, duracao_simulada)
            while self._tempo_simulado < alvo:
                if self._parada:
                    return False
                if self._pausada:
                    self._condicao.wait()
                    self._avancar_tempo()
                    continue
                restante = alvo - self._tempo_simulado
                self._condicao.wait(timeout=restante / self._velocidade)
                self._avancar_tempo()
            return not self._parada