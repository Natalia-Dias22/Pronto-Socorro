"""Thread que representa um medico/CPU e executa fatias de pacientes."""

import threading
from functools import partial

from escalonador import QUANTUM, TEXTO_TROCA, Escalonador
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
        fatia: float = QUANTUM,
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
            if not self.recursos.atender_recursos(paciente, self.identificador):
                return False
            paciente.recursos_atendidos = True
        return not self.recursos.controle.parada

    def _anunciar_troca(self, interrompido: Paciente, proximo: Paciente) -> None:
        """Chamado pelo escalonador ainda com o lock da fila de prontos."""
        motivo = self.escalonador.motivo_troca
        self.recursos.emitir_evento(
            "preempcao",
            self.identificador,
            proximo.id,
            {"paciente_interrompido": interrompido.id, "motivo": motivo},
            f"{TEXTO_TROCA[motivo]}: medico {self.identificador} trocou paciente "
            f"{interrompido.id} pelo paciente {proximo.id}.",
            Fore.CYAN,
        )

    def run(self) -> None:
        paciente = self.escalonador.proximo_paciente()
        while paciente is not None and not self.recursos.controle.parada:
            if not self._assumir(paciente, anunciar_retomada=True):
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
                            inicio=inicio_fatia,
                            fim=fim_fatia,
                        )
                    )

                if paciente.restante <= 0.000001:
                    paciente.fim = self.recursos.controle.tempo
                    registro = RegistroAtendimento.de_paciente(paciente)
                    self.recursos.emitir_evento(
                        "medico_concluiu",
                        self.identificador,
                        paciente.id,
                        {"registro": registro},
                        f"Medico {self.identificador} concluiu paciente {paciente.id}.",
                        Fore.GREEN,
                    )
                    self.escalonador.concluir()
                    break

                proximo = self.escalonador.apos_fatia(
                    paciente,
                    inicio_fatia + duracao_fatia,
                    ao_trocar=partial(self._anunciar_troca, paciente),
                )
                if proximo is not paciente:
                    paciente = proximo
                    if not self._assumir(paciente, anunciar_retomada=False):
                        return
            paciente = self.escalonador.proximo_paciente()
