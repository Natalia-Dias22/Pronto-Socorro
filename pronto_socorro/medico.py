"""Thread que representa um medico/CPU e executa fatias de pacientes."""

import threading

from escalonador import Escalonador, PoliticaEscalonamento
from modelos import Paciente, TrechoGantt
from recursos import RecursosCompartilhados, Fore


class Medico(threading.Thread):
    def __init__(
        self,
        identificador: int,
        escalonador: Escalonador,
        recursos: RecursosCompartilhados,
        instante_zero: float,
        trechos: list[TrechoGantt],
        lock_trechos: threading.Lock,
        fatia: float = 0.1,
    ) -> None:
        super().__init__(name=f"Medico-{identificador}")
        self.daemon = True
        self.identificador = identificador
        self.escalonador = escalonador
        self.recursos = recursos
        self.instante_zero = instante_zero
        self.trechos = trechos
        self.lock_trechos = lock_trechos
        self.fatia = fatia

    def _iniciar_se_preciso(self, paciente: Paciente) -> bool:
        if paciente.inicio is None:
            paciente.inicio = self.recursos.controle.tempo
            self.recursos.emitir_evento(
                "medico_iniciou",
                self.identificador,
                paciente.id,
                {
                    "gravidade": paciente.gravidade.name,
                    "prioridade": paciente.prioridade,
                    "chegada": paciente.chegada,
                    "inicio": paciente.inicio,
                    "duracao": paciente.duracao,
                    "restante": paciente.restante,
                },
                f"Medico {self.identificador} iniciou paciente {paciente.id} "
                f"({paciente.gravidade.name}).",
                Fore.YELLOW,
            )
        if not paciente.recursos_atendidos:
            if not self.recursos.atender_recursos(paciente, self.identificador):
                return False
            paciente.recursos_atendidos = True
        return not self.recursos.controle.parada

    def _mensagem_preempcao(self, interrompido: Paciente, assumiu: Paciente) -> str:
        """Monta a mensagem de log/evento no formato pedido para cada politica."""
        if self.escalonador.politica is PoliticaEscalonamento.SJF:
            return (
                f"PREEMPÇÃO SJF: P{assumiu.id} (restante {assumiu.restante:.1f}s) "
                f"assume de P{interrompido.id} (restante {interrompido.restante:.1f}s)"
            )
        return (
            f"PREEMPÇÃO PRIORIDADE: P{assumiu.id} ({assumiu.gravidade.name}) "
            f"assume de P{interrompido.id} ({interrompido.gravidade.name})"
        )

    def run(self) -> None:
        paciente = self.escalonador.proximo_paciente()
        while paciente is not None and not self.recursos.controle.parada:
            if not self._iniciar_se_preciso(paciente):
                break
            while paciente.restante > 0.000001:
                duracao_fatia = min(self.fatia, paciente.restante)
                inicio_fatia = self.recursos.controle.tempo
                if not self.recursos.controle.aguardar(duracao_fatia):
                    return
                fim_fatia = self.recursos.controle.tempo
                # A CAUSA DO BUG DE PREEMPCAO POR TEMPO ESTAVA AQUI: descontar
                # sempre o valor NOMINAL da fatia (duracao_fatia) faz o
                # 'restante' derivar do relogio de tempo simulado
                # (controle.tempo), que avanca com base no tempo de PAREDE
                # multiplicado pela velocidade. Qualquer atraso real entre
                # duas leituras de controle.tempo (troca de contexto entre
                # threads, aquisicao de locks, notify_all, etc.) adianta o
                # relogio sem que o 'restante' acompanhe na mesma proporcao,
                # e esse desvio se acumula fatia a fatia. Em velocidades
                # maiores que 1x o desvio fica grande o suficiente para
                # comparar um 'restante' desatualizado contra o candidato da
                # fila, gerando preempcoes erradas (ou deixando de gerar as
                # corretas). A correcao e descontar o tempo REALMENTE
                # transcorrido nesta fatia (fim_fatia - inicio_fatia), que ja
                # inclui qualquer atraso: assim 'restante' fica sempre
                # sincronizado com o mesmo relogio usado em apos_fatia() para
                # decidir a preempcao.
                duracao_real = fim_fatia - inicio_fatia
                paciente.restante = max(
                    0.0, paciente.restante - duracao_real
                )
                with self.lock_trechos:
                    self.trechos.append(
                        TrechoGantt(
                            medico=self.identificador,
                            paciente_id=paciente.id,
                            gravidade=paciente.gravidade,
                            inicio=inicio_fatia - self.instante_zero,
                            fim=fim_fatia - self.instante_zero,
                        )
                    )

                if paciente.restante <= 0.000001:
                    paciente.fim = self.recursos.controle.tempo
                    self.recursos.emitir_evento(
                        "medico_concluiu",
                        self.identificador,
                        paciente.id,
                        {
                            "chegada": paciente.chegada,
                            "inicio": paciente.inicio,
                            "fim": paciente.fim,
                            "gravidade": paciente.gravidade.name,
                        },
                        f"Medico {self.identificador} concluiu paciente {paciente.id}.",
                        Fore.GREEN,
                    )
                    self.escalonador.concluir()
                    break

                # Avisa a interface do tempo restante atualizado desta fatia,
                # para a sala de espera e o card do medico mostrarem o
                # progresso ("P17 · 1.4s") sem a GUI precisar recalcular nada
                # por conta propria (ela so le eventos da fila, nunca o
                # objeto Paciente compartilhado entre threads).
                self.recursos.emitir_evento(
                    "fatia",
                    self.identificador,
                    paciente.id,
                    {"restante": paciente.restante, "duracao": paciente.duracao},
                )

                proximo = self.escalonador.apos_fatia(paciente)
                if proximo is not paciente:
                    mensagem = self._mensagem_preempcao(paciente, proximo)
                    self.recursos.emitir_evento(
                        "preempcao",
                        self.identificador,
                        proximo.id,
                        {
                            "paciente_interrompido": paciente.id,
                            "restante_interrompido": paciente.restante,
                            "restante_assumiu": proximo.restante,
                            "politica": self.escalonador.politica.value,
                            "mensagem": mensagem,
                        },
                        mensagem,
                        Fore.CYAN,
                    )
                    paciente = proximo
                    if not self._iniciar_se_preciso(paciente):
                        return
            paciente = self.escalonador.proximo_paciente()