"""Thread que representa um medico/CPU e executa fatias de pacientes."""

import threading
from functools import partial

from escalonador import EPSILON, FATIA, ROUND_ROBIN, Escalonador
from modelos import Paciente, RegistroAtendimento, TrechoGantt
from recursos import RecursosCompartilhados, Fore


class Medico(threading.Thread):
    def __init__(
        self,
        identificador: int,
        escalonador: Escalonador,
        recursos: RecursosCompartilhados,
        trechos: list[TrechoGantt],
        lock_trechos: threading.Lock,
        fatia: float = FATIA,
    ) -> None:
        super().__init__(name=f"Medico-{identificador}")
        self.daemon = True
        self.identificador = identificador
        self.escalonador = escalonador
        self.recursos = recursos
        self.trechos = trechos
        self.lock_trechos = lock_trechos
        self.fatia = fatia

    def _assumir(self, paciente: Paciente, anunciar_retomada: bool) -> bool:
        """Anuncia o paciente recebido do escalonador e atende seus recursos."""
        if paciente.despachos == 1:
            self.recursos.emitir_evento(
                "medico_iniciou",
                self.identificador,
                paciente.id,
                {
                    "gravidade": paciente.gravidade.name,
                    "prioridade": paciente.prioridade,
                    "chegada": paciente.chegada,
                    "inicio": paciente.inicio,
                },
                f"Medico {self.identificador} iniciou paciente {paciente.id} "
                f"({paciente.gravidade.name}).",
                Fore.YELLOW,
            )
        elif anunciar_retomada:
            # Paciente preemptado que voltou da fila de prontos para um medico livre.
            self.recursos.emitir_evento(
                "medico_retomou",
                self.identificador,
                paciente.id,
                {"gravidade": paciente.gravidade.name},
                f"Medico {self.identificador} retomou paciente {paciente.id}.",
                Fore.YELLOW,
            )
        if not paciente.recursos_atendidos:
            # Raio-X, leito e prontuario acontecem aqui, ANTES das fatias de consulta:
            # o paciente nunca e trocado segurando um recurso, e esperar semaforo
            # nao consome quantum nem 'restante'.
            antes = self.recursos.controle.tempo
            atendido = self.recursos.atender_recursos(paciente, self.identificador)
            paciente.tempo_recursos += self.recursos.controle.tempo - antes
            if not atendido:
                return False
            paciente.recursos_atendidos = True
        return not self.recursos.controle.parada

    def _anunciar_troca(self, interrompido: Paciente, proximo: Paciente) -> None:
        """Chamado pelo escalonador ainda com o lock da fila de prontos."""
        motivo = self.escalonador.motivo_troca
        if motivo == "quantum":
            mensagem = (
                f"RR: P{interrompido.id} usou o quantum e voltou ao fim da fila "
                f"(restante {interrompido.restante:.2f} s)"
            )
        else:
            mensagem = (
                f"Preempção: medico {self.identificador} trocou paciente "
                f"{interrompido.id} pelo paciente {proximo.id}."
            )
        self.recursos.emitir_evento(
            "preempcao",
            self.identificador,
            proximo.id,
            {
                "paciente_interrompido": interrompido.id,
                "motivo": motivo,
                "restante": interrompido.restante,
                "texto": mensagem,
            },
            mensagem,
            Fore.CYAN,
        )

    def run(self) -> None:
        escalonador = self.escalonador
        controle = self.recursos.controle
        round_robin = escalonador.algoritmo == ROUND_ROBIN
        paciente = escalonador.proximo_paciente()
        while paciente is not None and not controle.parada:
            if not self._assumir(paciente, anunciar_retomada=True):
                break
            # Quantum deste medico para este paciente: zera quando o paciente e
            # ESCOLHIDO, nao a cada fatia, e nao e compartilhado entre medicos.
            usado = 0.0
            while paciente.restante > EPSILON:
                duracao_fatia = min(self.fatia, paciente.restante)
                if round_robin:
                    duracao_fatia = min(duracao_fatia, escalonador.quantum - usado)
                inicio_fatia = controle.tempo
                restante_antes = paciente.restante
                if not controle.aguardar(duracao_fatia):
                    return
                fim_fatia = controle.tempo
                # Tempo realmente consumido (>= o pedido, por causa do timer do SO):
                # assim consulta + espera + recursos fecham com o retorno.
                gasto = max(duracao_fatia, fim_fatia - inicio_fatia)
                paciente.restante = max(0.0, restante_antes - gasto)
                usado += gasto
                with self.lock_trechos:
                    self.trechos.append(
                        TrechoGantt(
                            medico=self.identificador,
                            paciente_id=paciente.id,
                            gravidade=paciente.gravidade,
                            inicio=inicio_fatia,
                            fim=fim_fatia,
                        )
                    )

                if paciente.restante <= EPSILON:
                    paciente.restante = 0.0
                    # Fim ideal da consulta: descarta o atraso de timer da ultima fatia.
                    paciente.fim = min(fim_fatia, inicio_fatia + restante_antes)
                    registro = RegistroAtendimento.de_paciente(paciente)
                    self.recursos.emitir_evento(
                        "medico_concluiu",
                        self.identificador,
                        paciente.id,
                        {"registro": registro},
                        f"Medico {self.identificador} concluiu paciente {paciente.id}.",
                        Fore.GREEN,
                    )
                    escalonador.concluir()
                    break

                if round_robin:
                    if usado < escalonador.quantum - EPSILON:
                        continue  # quantum ainda nao acabou: mesma fatia de consulta
                    proximo = escalonador.fim_quantum(
                        paciente, ao_trocar=partial(self._anunciar_troca, paciente)
                    )
                else:
                    proximo = escalonador.apos_fatia(
                        paciente, ao_trocar=partial(self._anunciar_troca, paciente)
                    )
                if proximo is not paciente:
                    paciente = proximo
                    if not self._assumir(paciente, anunciar_retomada=False):
                        return
                if round_robin:
                    usado = 0.0  # novo turno: paciente novo ou novo quantum
            paciente = escalonador.proximo_paciente()
