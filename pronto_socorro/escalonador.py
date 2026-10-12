"""Fila de prontos com preempcao entre fatias de CPU (PS ou RR)."""

import threading
from collections.abc import Callable

from controle import ControleSimulacao
from modelos import Paciente

PRIORIDADE = "prioridade"
ROUND_ROBIN = "rr"
ALGORITMOS = {
    PRIORIDADE: "Prioridade preemptiva",
    ROUND_ROBIN: "Round Robin",
}
SIGLAS = {PRIORIDADE: "PS", ROUND_ROBIN: "RR"}
# Por que o medico troca de paciente em cada algoritmo, e como isso e exibido.
MOTIVO_TROCA = {PRIORIDADE: "prioridade", ROUND_ROBIN: "quantum"}
TEXTO_TROCA = {"prioridade": "Preempção", "quantum": "Quantum esgotado"}
# Fatia de CPU em segundos simulados; no Round Robin e o quantum de tempo.
QUANTUM = 0.1


def descrever_quantum() -> str:
    return f"quantum {QUANTUM:g}s"


def descrever_algoritmo(algoritmo: str) -> str:
    if algoritmo == ROUND_ROBIN:
        return f"{ALGORITMOS[algoritmo]} ({descrever_quantum()})"
    return ALGORITMOS[algoritmo]


class Escalonador:
    """Fila de prontos comum aos medicos, coordenada por uma Condition.

    - Prioridade preemptiva (PS): vermelho > amarelo > verde, empate em FCFS.
      Ao fim de cada fatia, o medico troca de paciente se houver alguem mais grave.
    - Round Robin (RR): fila circular FIFO que ignora a gravidade. Ao fim de cada
      quantum, o paciente volta ao final da fila se houver outro pronto esperando.

    Nos dois casos nao ha troca enquanto algum medico estiver ocioso: ele mesmo
    atende quem esta na fila.
    """

    def __init__(
        self,
        pacientes: list[Paciente],
        controle: ControleSimulacao,
        publicar_evento: Callable[
            [str, int | None, int | None, dict[str, object]], None
        ] | None = None,
        algoritmo: str = PRIORIDADE,
    ) -> None:
        if algoritmo not in ALGORITMOS:
            raise ValueError(f"Algoritmo de escalonamento desconhecido: {algoritmo}")
        self.algoritmo = algoritmo
        self.motivo_troca = MOTIVO_TROCA[algoritmo]
        self.controle = controle
        self.publicar_evento = publicar_evento
        self._condicao = threading.Condition()
        self._fila = list(pacientes)
        for paciente in self._fila:
            paciente.entrou_na_fila = paciente.chegada
        self._chegadas_publicadas: set[int] = set()
        self._total = len(pacientes)
        self._concluidos = 0
        self._ociosos = 0
        self.preempcoes = 0
        controle.registrar_ouvinte(self._acordar)

    def _acordar(self) -> None:
        with self._condicao:
            self._condicao.notify_all()

    def _anunciar_chegadas(self, agora: float) -> None:
        houve_chegada = False
        for paciente in self._fila:
            if paciente.chegada <= agora and paciente.id not in self._chegadas_publicadas:
                self._chegadas_publicadas.add(paciente.id)
                houve_chegada = True
                if self.publicar_evento is not None:
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
        if houve_chegada:
            # Medicos ociosos acordam ja, sem esperar o proprio timeout.
            self._condicao.notify_all()

    def publicar_chegadas(self) -> None:
        """Anuncia admissões em uma thread leve, sem interferir na fila de CPU."""
        with self._condicao:
            while True:
                if self.controle.parada:
                    return
                agora = self.controle.tempo
                self._anunciar_chegadas(agora)
                pendentes = [
                    paciente.chegada
                    for paciente in self._fila
                    if paciente.id not in self._chegadas_publicadas
                ]
                if not pendentes:
                    return
                if self.controle.pausada:
                    timeout = None
                else:
                    timeout = max(0.001, (min(pendentes) - agora) / self.controle.velocidade)
                self._condicao.wait(timeout=timeout)

    def _chave(self, paciente: Paciente) -> tuple[float, ...]:
        if self.algoritmo == ROUND_ROBIN:
            # Ordem de entrada na fila de prontos: chegada ou volta apos o quantum.
            return paciente.entrou_na_fila, paciente.id
        return paciente.prioridade, paciente.chegada, paciente.id

    @staticmethod
    def _despachar(paciente: Paciente, agora: float) -> Paciente:
        """Tira o paciente da fila de prontos e contabiliza quanto ele esperou nela."""
        paciente.espera += agora - paciente.entrou_na_fila
        if paciente.inicio is None:
            paciente.inicio = agora
        paciente.despachos += 1
        return paciente

    def proximo_paciente(self) -> Paciente | None:
        """Aguarda a chegada de um paciente elegivel sem consumir CPU."""
        with self._condicao:
            while self._concluidos < self._total:
                if self.controle.parada:
                    return None
                agora_simulado = self.controle.tempo
                self._anunciar_chegadas(agora_simulado)
                elegiveis = [
                    paciente
                    for paciente in self._fila
                    if paciente.chegada <= agora_simulado
                ]
                if elegiveis:
                    escolhido = min(elegiveis, key=self._chave)
                    self._fila.remove(escolhido)
                    return self._despachar(escolhido, agora_simulado)

                proximas = [
                    paciente.chegada - agora_simulado for paciente in self._fila
                ]
                if self.controle.pausada:
                    timeout = None
                elif proximas:
                    timeout = max(0.001, min(proximas) / self.controle.velocidade)
                else:
                    timeout = None
                # A Condition libera o lock enquanto espera: ha progresso sem busy waiting.
                self._ociosos += 1
                try:
                    self._condicao.wait(timeout=timeout)
                finally:
                    self._ociosos -= 1
            return None

    def apos_fatia(
        self,
        atual: Paciente,
        fim_quantum: float,
        ao_trocar: Callable[[Paciente], None] | None = None,
    ) -> Paciente:
        """Ao fim da fatia, decide se o medico continua ou troca de paciente.

        fim_quantum e o fim nominal da fatia (inicio + duracao). ao_trocar recebe o
        novo paciente com o lock ainda preso: o evento de preempcao sai antes que
        outro medico possa retomar o paciente interrompido.
        """
        with self._condicao:
            agora_simulado = self.controle.tempo
            self._anunciar_chegadas(agora_simulado)
            if self._ociosos:
                # Um medico livre atende quem esta na fila; trocar seria desperdicio.
                self._condicao.notify_all()
                return atual
            elegiveis = [
                paciente
                for paciente in self._fila
                if paciente.chegada <= agora_simulado
            ]
            if not elegiveis:
                return atual

            melhor = min(elegiveis, key=self._chave)
            if self.algoritmo == PRIORIDADE:
                if melhor.prioridade >= atual.prioridade:
                    return atual
            elif melhor.entrou_na_fila >= fim_quantum:
                # FIFO: o paciente atual volta a fila no fim do quantum; quem entrou
                # depois (ex.: acabou de ser devolvido por outro medico) fica atras dele.
                return atual

            atual.entrou_na_fila = agora_simulado
            self._fila.append(atual)
            self._fila.remove(melhor)
            self.preempcoes += 1
            proximo = self._despachar(melhor, agora_simulado)
            if ao_trocar is not None:
                ao_trocar(proximo)
            self._condicao.notify_all()
            return proximo

    def concluir(self) -> None:
        with self._condicao:
            self._concluidos += 1
            self._condicao.notify_all()
