"""Recursos compartilhados: raio-X, leitos de UTI e prontuario."""

import threading
from collections.abc import Callable
from dataclasses import dataclass

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


# Tempo (s simulados) que o paciente fica dentro do raio-X. Precisa ser longo o
# bastante para que medicos que chegam em instantes proximos se sobreponham.
DURACAO_RAIO_X = 0.25


@dataclass
class UsoRaioX:
    """Uma passagem pelo raio-X, para a prova independente das colisoes."""

    paciente_id: int
    medico: int
    ordem_entrada: int  # numero de ordem dos eventos de medicao (entradas e saidas)
    entrada: float
    ordem_saida: int | None = None
    saida: float | None = None


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
        # Instrumentacao do raio-X. O lock abaixo NAO protege o aparelho (no modo
        # SEM ele continua sem exclusao mutua): so torna a CONTAGEM exata.
        # Todos os contadores nascem aqui, por execucao: nada e global.
        self._lock_medicao = threading.Lock()
        self._ocupantes_raio_x = 0
        self.colisoes_raio_x = 0
        self._ordem_medicao = 0
        self.usos_raio_x: list[UsoRaioX] = []

        self._semaforo_leitos = threading.Semaphore(3)
        self._lock_leitos = threading.Lock()
        self.leitos_livres = 3

        # Leitores podem compartilhar a leitura; escritores sao exclusivos.
        self._mutex_leitores = threading.Semaphore(1)
        self._semaforo_escrita = threading.Semaphore(1)
        self._leitores_ativos = 0
        self.notas: list[str] = []
        self.gravacoes_concluidas = 0
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

    def _entrar_raio_x(self, paciente: Paciente, medico: int) -> UsoRaioX:
        with self._lock_medicao:
            if self._ocupantes_raio_x > 0:
                # Entrou com outro ocupante ja dentro: UMA colisao por entrada.
                # Com 3 ocupantes simultaneos sao 2 colisoes.
                self.colisoes_raio_x += 1
                self.emitir_evento(
                    "colisao",
                    medico,
                    paciente.id,
                    {
                        "ocupantes": self._ocupantes_raio_x + 1,
                        "total": self.colisoes_raio_x,
                    },
                    f"COLISAO: medico {medico} e paciente {paciente.id} "
                    "encontraram o raio-X ocupado.",
                    Fore.RED,
                )
            self._ocupantes_raio_x += 1
            self._ordem_medicao += 1
            uso = UsoRaioX(
                paciente.id, medico, self._ordem_medicao, self.controle.tempo
            )
            self.usos_raio_x.append(uso)
            self.emitir_evento(
                "raio_x_entrou",
                medico,
                paciente.id,
                {"ocupantes": self._ocupantes_raio_x},
                f"Raio-X: paciente {paciente.id} iniciou o exame.",
                Fore.GREEN,
            )
            return uso

    def _sair_raio_x(self, uso: UsoRaioX, paciente: Paciente, medico: int) -> None:
        with self._lock_medicao:
            self._ocupantes_raio_x -= 1
            self._ordem_medicao += 1
            uso.ordem_saida = self._ordem_medicao
            uso.saida = self.controle.tempo
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

    def _usar_raio_x(self, paciente: Paciente, medico: int) -> bool:
        if self.usar_sincronizacao:
            # Semaforo binario: somente um medico entra no aparelho por vez.
            if not self._adquirir(
                self._semaforo_raio_x, "raio-X", medico, paciente
            ):
                return False
        uso = self._entrar_raio_x(paciente, medico)
        try:
            self.controle.aguardar(DURACAO_RAIO_X)
        finally:
            # Sempre sai: parada ou erro nunca deixam 'ocupantes' nem o semaforo presos.
            self._sair_raio_x(uso, paciente, medico)
        return not self.controle.parada

    def colisoes_por_forca_bruta(self) -> int:
        """Recontagem independente: entradas com outro uso ainda em andamento."""
        with self._lock_medicao:
            usos = list(self.usos_raio_x)
        total = 0
        for uso in usos:
            for outro in usos:
                if outro is uso or outro.ordem_entrada > uso.ordem_entrada:
                    continue
                if outro.ordem_saida is None or outro.ordem_saida > uso.ordem_entrada:
                    total += 1
                    break
        return total

    def _usar_leito(self, paciente: Paciente, medico: int) -> bool:
        if self.usar_sincronizacao:
            if not self._adquirir(
                self._semaforo_leitos, "leitos de UTI", medico, paciente
            ):
                return False
            # Decremento e publicacao sob o mesmo lock: o painel nunca ve um
            # contador ja decrementado por outro medico antes do proprio evento.
            with self._lock_leitos:
                self.leitos_livres -= 1
                self._registrar_leito(paciente, medico)
        else:
            # A pausa entre leitura e escrita torna a atualizacao nao atomica.
            temporario = self.leitos_livres
            if not self.controle.aguardar(0.001):
                return False
            self.leitos_livres = temporario - 1
            self._registrar_leito(paciente, medico)
        # Leitos representam internacoes que continuam ocupadas ao fim da simulacao.
        return True

    def _registrar_leito(self, paciente: Paciente, medico: int) -> None:
        with self._lock_leitos_ocupados:
            self._leitos_ocupados[paciente.id] = paciente
            esperado = max(0, 3 - len(self._leitos_ocupados))
            livres = self.leitos_livres
            self.emitir_evento(
                "leito_ocupou",
                medico,
                paciente.id,
                {"livres": livres, "esperado": esperado},
                f"UTI: paciente {paciente.id} ocupou um leito; livres={livres}.",
                Fore.CYAN,
            )

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

    @property
    def notas_salvas(self) -> int:
        """Notas de gravacoes concluidas que continuam no prontuario."""
        with self._lock_estatisticas:
            return len(self._notas_concluidas & set(self.notas))

    def _concluir_gravacao(self, nota: str, medico: int, paciente: Paciente) -> None:
        """Conta a gravacao e publica salvas/total como um unico retrato.

        O total conta gravacoes concluidas (nao iniciadas): assim, no modo COM, o
        painel nunca mostra "3/5" so porque duas gravacoes ainda estao em curso.
        """
        with self._lock_estatisticas:
            self.gravacoes_concluidas += 1
            self._notas_concluidas.add(nota)
            presentes = set(self.notas)
            salvas = len(self._notas_concluidas & presentes)
            ausentes = self._notas_concluidas - presentes
            novas_perdas = ausentes - self._notas_perdidas
            # Uma copia antiga pode trazer de volta uma nota perdida; se ela sumir
            # de novo, o alerta precisa aparecer outra vez.
            self._notas_perdidas = ausentes
            self.emitir_evento(
                "nota_gravada",
                medico,
                paciente.id,
                {"salvas": salvas, "total": self.gravacoes_concluidas},
                f"Prontuario: nota do paciente {paciente.id} gravada.",
                Fore.GREEN,
            )
            for nota_perdida in sorted(novas_perdas):
                id_perdido = int(nota_perdida.split(":", 1)[0].split()[-1])
                self.emitir_evento(
                    "nota_perdida",
                    medico,
                    id_perdido,
                    {"nota": nota_perdida},
                    f"NOTA PERDIDA: registro do paciente {id_perdido} foi sobrescrito.",
                    Fore.RED,
                )

    def gravar_prontuario(self, nota: str, medico: int, paciente: Paciente) -> bool:
        if not self.usar_sincronizacao:
            # Dois gravadores podem copiar o mesmo estado e sobrescrever a nota alheia.
            copia = list(self.notas)
            if not self.controle.aguardar(0.02):
                return False
            copia.append(nota)
            self.notas = copia
            self._concluir_gravacao(nota, medico, paciente)
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
            # Ainda dentro da secao critica: nenhum outro gravador altera as notas
            # entre a escrita e a contagem.
            self._concluir_gravacao(nota, medico, paciente)
        finally:
            self._semaforo_escrita.release()
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