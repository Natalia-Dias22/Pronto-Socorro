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
# Granularidade do medico (s simulados): de quanto em quanto tempo ele olha a fila.
# E ela que limita o atraso da preempcao por prioridade; no RR o quantum e outro.
FATIA = 0.1
# Quantum padrao do Round Robin, em segundos simulados (configuravel na tela).
QUANTUM_PADRAO = 1.0
EPSILON = 1e-6


def descrever_quantum(quantum: float = QUANTUM_PADRAO) -> str:
    return f"quantum {quantum:g}s"


def descrever_algoritmo(algoritmo: str, quantum: float = QUANTUM_PADRAO) -> str:
    if algoritmo == ROUND_ROBIN:
        return f"{ALGORITMOS[algoritmo]} ({descrever_quantum(quantum)})"
    return ALGORITMOS[algoritmo]


class Escalonador:
    """Fila de prontos comum aos medicos, coordenada por uma Condition.

    - Prioridade preemptiva (PS): vermelho > amarelo > verde, empate por chegada e
      depois por id. Ao fim de cada fatia, o medico troca de paciente somente se
      houver alguem ESTRITAMENTE mais grave.
    - Round Robin (RR): fila FIFO que ignora a gravidade. Chegada nao causa
      preempcao; so o fim do quantum devolve o paciente ao FIM da fila. O quantum
      e contado por medico (ver Medico.run), nunca neste objeto compartilhado.

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
        quantum: float = QUANTUM_PADRAO,
    ) -> None:
        if algoritmo not in ALGORITMOS:
            raise ValueError(f"Algoritmo de escalonamento desconhecido: {algoritmo}")
        if quantum <= 0:
            raise ValueError("O quantum precisa ser maior que zero.")
        self.algoritmo = algoritmo
        self.quantum = quantum
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

    def _elegiveis(self, agora: float) -> list[Paciente]:
        return [paciente for paciente in self._fila if paciente.chegada <= agora]

    def _trocar(
        self,
        atual: Paciente,
        melhor: Paciente,
        agora: float,
        ao_trocar: Callable[[Paciente], None] | None,
    ) -> Paciente:
        """Devolve o atual ao FIM da fila e despacha o escolhido (lock ja preso)."""
        atual.entrou_na_fila = agora
        self._fila.append(atual)
        self._fila.remove(melhor)
        self.preempcoes += 1
        proximo = self._despachar(melhor, agora)
        if ao_trocar is not None:
            ao_trocar(proximo)
        self._condicao.notify_all()
        return proximo

    def apos_fatia(
        self,
        atual: Paciente,
        ao_trocar: Callable[[Paciente], None] | None = None,
    ) -> Paciente:
        """Prioridade preemptiva: ao fim da fatia, troca so por alguem MAIS grave.

        ao_trocar recebe o novo paciente com o lock ainda preso: o evento de
        preempcao sai antes que outro medico possa retomar o paciente interrompido.
        No RR a chegada nunca preempta; use fim_quantum.
        """
        if self.algoritmo != PRIORIDADE:
            return atual
        with self._condicao:
            agora = self.controle.tempo
            self._anunciar_chegadas(agora)
            if self._ociosos:
                # Um medico livre atende quem esta na fila; trocar seria desperdicio.
                self._condicao.notify_all()
                return atual
            elegiveis = self._elegiveis(agora)
            if not elegiveis:
                return atual
            melhor = min(elegiveis, key=self._chave)
            if melhor.prioridade >= atual.prioridade:
                return atual  # igual ou menos grave: nao interrompe
            return self._trocar(atual, melhor, agora, ao_trocar)

    def fim_quantum(
        self,
        atual: Paciente,
        ao_trocar: Callable[[Paciente], None] | None = None,
    ) -> Paciente:
        """Round Robin: o quantum do medico acabou e o paciente nao terminou.

        Se ha alguem esperando, o atual vai para o FIM da fila (mantendo o
        'restante') e o medico pega o primeiro. Sem ninguem esperando, o atual
        segue com um novo quantum e nada conta como preempcao.
        """
        with self._condicao:
            agora = self.controle.tempo
            self._anunciar_chegadas(agora)
            if self._ociosos:
                self._condicao.notify_all()
                return atual
            elegiveis = self._elegiveis(agora)
            if not elegiveis:
                return atual
            return self._trocar(atual, min(elegiveis, key=self._chave), agora, ao_trocar)

    def concluir(self) -> None:
        with self._condicao:
            self._concluidos += 1
            self._condicao.notify_all()
