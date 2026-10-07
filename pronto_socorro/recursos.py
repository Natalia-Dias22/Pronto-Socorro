"""Recursos compartilhados: raio-X, leitos de UTI e prontuario."""

import threading
from collections.abc import Callable

from controle import ControleSimulacao
from modelos import Paciente

try:
    from colorama import Fore, Style, init

    init(autoreset=True)
except ImportError:  # Colorama e conveniente, mas nao impede executar o projeto.
    class Fore:
        RED = ""
        GREEN = ""
        YELLOW = ""
        CYAN = ""

    class Style:
        RESET_ALL = ""


class RecursosCompartilhados:
    def __init__(
        self,
        usar_sincronizacao: bool,
        controle: ControleSimulacao | None = None,
        callback_evento: Callable[
            [tuple[str, int | None, int | None, dict[str, object], float]], None
        ]
        | None = None,
    ) -> None:
        self.usar_sincronizacao = usar_sincronizacao
        self.controle = controle or ControleSimulacao()
        self.callback_evento = callback_evento

        self._semaforo_raio_x = threading.Semaphore(1)
        self._lock_medicao_raio_x = threading.Lock()
        self._ocupantes_raio_x = 0
        self.colisoes_raio_x = 0

        self._semaforo_leitos = threading.Semaphore(3)
        self._lock_leitos = threading.Lock()
        self.leitos_livres = 3

        # Leitores podem compartilhar a leitura; escritores sao exclusivos.
        self._mutex_leitores = threading.Semaphore(1)
        self._semaforo_escrita = threading.Semaphore(1)
        self._leitores_ativos = 0
        self.notas: list[str] = []
        self.tentativas_gravacao = 0
        self._lock_estatisticas = threading.Lock()
        self._lock_saida = threading.Lock()
        self._lock_leitos_ocupados = threading.Lock()
        self._leitos_ocupados: dict[int, Paciente] = {}
        self._notas_concluidas: set[str] = set()
        self._notas_perdidas: set[str] = set()

    def _log(self, mensagem: str, cor: str = "") -> None:
        with self._lock_saida:
            print(f"{cor}{mensagem}{Style.RESET_ALL}")

    def emitir_evento(
        self,
        tipo: str,
        medico_id: int | None = None,
        paciente_id: int | None = None,
        dados: dict[str, object] | None = None,
        mensagem: str = "",
        cor: str = "",
    ) -> None:
        evento = (
            tipo,
            medico_id,
            paciente_id,
            dados or {},
            self.controle.tempo,
        )
        if self.callback_evento is not None:
            self.callback_evento(evento)
        elif mensagem:
            self._log(mensagem, cor)

    def _adquirir(
        self,
        semaforo: threading.Semaphore,
        recurso: str,
        medico: int,
        paciente: Paciente,
    ) -> bool:
        if semaforo.acquire(blocking=False):
            return True
        self.emitir_evento(
            "aguardando_semaforo",
            medico,
            paciente.id,
            {"recurso": recurso},
            f"Medico {medico} aguardando semaforo: {recurso}.",
            Fore.YELLOW,
        )
        while not self.controle.parada:
            if semaforo.acquire(timeout=0.1):
                return True
        return False

    def _usar_raio_x(self, paciente: Paciente, medico: int) -> bool:
        if self.usar_sincronizacao:
            # Semaforo binario: somente um medico entra no aparelho por vez.
            if not self._adquirir(
                self._semaforo_raio_x, "raio-X", medico, paciente
            ):
                return False
        with self._lock_medicao_raio_x:
            colisao = self._ocupantes_raio_x > 0
            self._ocupantes_raio_x += 1
            ocupantes = self._ocupantes_raio_x
            if colisao:
                self.colisoes_raio_x += 1
        if colisao:
            self.emitir_evento(
                "colisao",
                medico,
                paciente.id,
                {"ocupantes": ocupantes},
                f"COLISAO: medico {medico} e paciente {paciente.id} "
                "encontraram o raio-X ocupado.",
                Fore.RED,
            )
        self.emitir_evento(
            "raio_x_entrou",
            medico,
            paciente.id,
            {"ocupantes": ocupantes},
            f"Raio-X: paciente {paciente.id} iniciou o exame.",
            Fore.GREEN,
        )
        try:
            self.controle.aguardar(0.025)
        finally:
            with self._lock_medicao_raio_x:
                self._ocupantes_raio_x -= 1
                ocupantes = self._ocupantes_raio_x
            if self.usar_sincronizacao:
                self._semaforo_raio_x.release()
            self.emitir_evento(
                "raio_x_saiu",
                medico,
                paciente.id,
                {"ocupantes": ocupantes},
                f"Raio-X: paciente {paciente.id} liberou o aparelho.",
                Fore.GREEN,
            )
        return not self.controle.parada

    def _usar_leito(self, paciente: Paciente, medico: int) -> bool:
        if self.usar_sincronizacao:
            if not self._adquirir(
                self._semaforo_leitos, "leitos de UTI", medico, paciente
            ):
                return False
            with self._lock_leitos:
                self.leitos_livres -= 1
        else:
            # A pausa entre leitura e escrita torna a atualizacao nao atomica.
            temporario = self.leitos_livres
            if not self.controle.aguardar(0.001):
                return False
            self.leitos_livres = temporario - 1
        with self._lock_leitos_ocupados:
            self._leitos_ocupados[paciente.id] = paciente
            esperado = max(0, 3 - len(self._leitos_ocupados))
        self.emitir_evento(
            "leito_ocupou",
            medico,
            paciente.id,
            {"livres": self.leitos_livres, "esperado": esperado},
            f"UTI: paciente {paciente.id} ocupou um leito; "
            f"livres={self.leitos_livres}.",
            Fore.CYAN,
        )
        # Leitos representam internacoes que continuam ocupadas ao fim da simulacao.
        return True

    def liberar_leitos_ao_parar(self) -> None:
        """Libera reservas somente ao cancelar a simulacao, para encerrar limpo."""
        with self._lock_leitos_ocupados:
            ocupados = list(self._leitos_ocupados.values())
            self._leitos_ocupados.clear()
        for paciente in ocupados:
            if self.usar_sincronizacao:
                with self._lock_leitos:
                    self.leitos_livres += 1
                self._semaforo_leitos.release()
            else:
                self.leitos_livres += 1
            self.emitir_evento(
                "leito_liberou",
                None,
                paciente.id,
                {"livres": self.leitos_livres},
                f"UTI: paciente {paciente.id} liberou um leito; "
                f"livres={self.leitos_livres}.",
                Fore.GREEN,
            )

    def ler_prontuario(self, medico: int, paciente: Paciente) -> list[str]:
        if not self.usar_sincronizacao:
            copia = list(self.notas)
            self.controle.aguardar(0.002)
            return copia

        if not self._adquirir(
            self._mutex_leitores, "mutex de leitores", medico, paciente
        ):
            return []
        self._leitores_ativos += 1
        if self._leitores_ativos == 1:
            if not self._adquirir(
                self._semaforo_escrita, "escrita do prontuario", medico, paciente
            ):
                self._leitores_ativos -= 1
                self._mutex_leitores.release()
                return []
        self._mutex_leitores.release()
        try:
            if not self.controle.aguardar(0.002):
                return []
            return list(self.notas)
        finally:
            self._mutex_leitores.acquire()
            self._leitores_ativos -= 1
            if self._leitores_ativos == 0:
                self._semaforo_escrita.release()
            self._mutex_leitores.release()

    def gravar_prontuario(self, nota: str, medico: int, paciente: Paciente) -> bool:
        with self._lock_estatisticas:
            self.tentativas_gravacao += 1

        if not self.usar_sincronizacao:
            # Dois gravadores podem copiar o mesmo estado e sobrescrever a nota alheia.
            copia = list(self.notas)
            if not self.controle.aguardar(0.02):
                return False
            copia.append(nota)
            self.notas = copia
            with self._lock_estatisticas:
                self._notas_concluidas.add(nota)
                perdidas = self._notas_concluidas - set(self.notas)
                novas_perdas = perdidas - self._notas_perdidas
                self._notas_perdidas.update(novas_perdas)
            self.emitir_evento(
                "nota_gravada",
                medico,
                paciente.id,
                {"salvas": len(self.notas), "total": self.tentativas_gravacao},
                f"Prontuario: nota do paciente {paciente.id} gravada.",
                Fore.GREEN,
            )
            for nota_perdida in novas_perdas:
                id_perdido = int(nota_perdida.split(":", 1)[0].split()[-1])
                self.emitir_evento(
                    "nota_perdida",
                    medico,
                    id_perdido,
                    {"nota": nota_perdida},
                    f"NOTA PERDIDA: registro do paciente {id_perdido} foi sobrescrito.",
                    Fore.RED,
                )
            return True

        if not self._adquirir(
            self._semaforo_escrita, "escrita do prontuario", medico, paciente
        ):
            return False
        try:
            if self.controle.parada:
                return False
            copia = list(self.notas)
            if not self.controle.aguardar(0.02):
                return False
            copia.append(nota)
            self.notas = copia
        finally:
            self._semaforo_escrita.release()
        with self._lock_estatisticas:
            self._notas_concluidas.add(nota)
        self.emitir_evento(
            "nota_gravada",
            medico,
            paciente.id,
            {"salvas": len(self.notas), "total": self.tentativas_gravacao},
            f"Prontuario: nota do paciente {paciente.id} gravada.",
            Fore.GREEN,
        )
        return True

    def atender_recursos(self, paciente: Paciente, medico: int) -> bool:
        """Adquire recursos sempre na mesma ordem para evitar deadlock."""
        if paciente.usa_raio_x and not self._usar_raio_x(paciente, medico):
            return False
        if paciente.usa_leito and not self._usar_leito(paciente, medico):
            return False
        if paciente.usa_prontuario:
            self.ler_prontuario(medico, paciente)
            if not self.gravar_prontuario(
                f"Paciente {paciente.id}: atendimento registrado.", medico, paciente
            ):
                return False
        return not self.controle.parada