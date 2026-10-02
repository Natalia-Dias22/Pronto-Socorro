"""Thread que representa um medico/CPU e executa fatias de pacientes."""

import threading

from escalonador import Escalonador
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
                paciente.restante = max(
                    0.0, paciente.restante - duracao_fatia
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

                proximo = self.escalonador.apos_fatia(paciente)
                if proximo is not paciente:
                    self.recursos.emitir_evento(
                        "preempcao",
                        self.identificador,
                        proximo.id,
                        {"paciente_interrompido": paciente.id},
                        f"Preempcao: medico {self.identificador} trocou paciente "
                        f"{paciente.id} pelo paciente {proximo.id}.",
                        Fore.CYAN,
                    )
                    paciente = proximo
                    if not self._iniciar_se_preciso(paciente):
                        return
            paciente = self.escalonador.proximo_paciente()