"""Testes automaticos: colisoes no raio-X, Round Robin, Prioridade e regressao.

Uso: python testes.py [colisao|rr|ps|metricas|regressao]
Cada teste imprime PASSOU/FALHOU com o valor esperado e o obtido.
"""

import contextlib
import io
import re
import sys
import threading
import time

from controle import ControleSimulacao
from escalonador import PRIORIDADE, ROUND_ROBIN
from main import executar_simulacao, gerar_pacientes
from modelos import Gravidade, Paciente, TrechoGantt

VELOCIDADE = 4.0  # simulacao 4x mais rapida; o Windows limita a precisao do timer
TOLERANCIA = 0.12  # s simulados: um atraso de timer por fatia
resultados: list[bool] = []


def verificar(nome: str, esperado, obtido, ok: bool | None = None) -> bool:
    ok = (esperado == obtido) if ok is None else ok
    resultados.append(ok)
    print(f"  [{'PASSOU' if ok else 'FALHOU'}] {nome}: esperado={esperado} obtido={obtido}")
    return ok


def paciente(
    pid: int,
    duracao: float,
    chegada: float = 0.0,
    gravidade: Gravidade = Gravidade.VERDE,
    raio_x: bool = False,
) -> Paciente:
    return Paciente(
        id=pid,
        gravidade=gravidade,
        duracao=duracao,
        chegada=chegada,
        restante=duracao,
        usa_raio_x=raio_x,
    )


class Execucao:
    """Resultado de uma simulacao com tudo que os testes precisam inspecionar."""

    def __init__(self) -> None:
        self.eventos: list[tuple] = []
        self.trechos: list[TrechoGantt] = []
        self.saida = ""
        self.recursos = None
        self.metricas = None
        self.pacientes: list[Paciente] = []
        self.travou = False

    def preempcoes(self) -> int:
        return self.recursos.preempcoes

    def ordem_conclusao(self) -> list[int]:
        return [e[2] for e in self.eventos if e[0] == "medico_concluiu"]

    def rodizio(self) -> list[int]:
        """Sequencia de pacientes executados, fundindo fatias consecutivas iguais."""
        sequencia: list[int] = []
        for trecho in sorted(self.trechos, key=lambda t: t.inicio):
            if not sequencia or sequencia[-1] != trecho.paciente_id:
                sequencia.append(trecho.paciente_id)
        return sequencia

    def devolucoes(self) -> list[dict]:
        return [e[3] for e in self.eventos if e[0] == "preempcao"]


def rodar(
    algoritmo: str,
    medicos: int,
    sincronizado: bool = True,
    pacientes: list[Paciente] | None = None,
    semente: int = 42,
    num_pacientes: int = 0,
    quantum: float = 1.0,
    velocidade: float = VELOCIDADE,
    com_callback: bool = True,
    limite: float = 120.0,
) -> Execucao:
    execucao = Execucao()
    if pacientes is None:
        pacientes = gerar_pacientes(semente, num_pacientes)
    execucao.pacientes = pacientes
    lock = threading.Lock()

    def callback(evento) -> None:
        with lock:
            execucao.eventos.append(evento)

    def alvo() -> None:
        capturado = io.StringIO()
        with contextlib.redirect_stdout(capturado):
            execucao.recursos, execucao.metricas = executar_simulacao(
                sincronizado,
                semente,
                medicos,
                mostrar_saida_terminal=False,
                algoritmo=algoritmo,
                quantum=quantum,
                pacientes=pacientes,
                trechos=execucao.trechos,
                controle=controle,
                callback_evento=callback if com_callback else None,
            )
        execucao.saida = capturado.getvalue()

    controle = ControleSimulacao(velocidade)
    thread = threading.Thread(target=alvo, daemon=True)
    thread.start()
    thread.join(limite)
    if thread.is_alive():
        execucao.travou = True
        controle.parar()  # destrava as threads para o processo poder seguir
        thread.join(5)
    return execucao


def forca_bruta_por_tempo(recursos) -> int:
    """Prova independente: usa so os trios (entrada, saida, paciente) em tempo
    simulado, sem olhar para o contador nem para a ordem dos eventos."""
    trios = [(u.entrada, u.saida, u.paciente_id) for u in recursos.usos_raio_x]
    total = 0
    for i, (entrada_i, _, _) in enumerate(trios):
        if any(
            entrada_j <= entrada_i < saida_j
            for j, (entrada_j, saida_j, _) in enumerate(trios)
            if j != i
        ):
            total += 1
    return total


def linhas_colisao(texto: str) -> int:
    return len(re.findall(r"^.*COLISAO.*$", texto, flags=re.MULTILINE))


# --------------------------------------------------------------------------- A


def testes_colisao() -> None:
    print("\n=== A) COLISOES NO RAIO-X ===")

    print("\nA1. SEM sincronizacao, 2 medicos, 2 pacientes chegando juntos")
    for algoritmo in (PRIORIDADE, ROUND_ROBIN):
        ex = rodar(
            algoritmo,
            2,
            sincronizado=False,
            pacientes=[paciente(1, 1.0, raio_x=True), paciente(2, 1.0, raio_x=True)],
        )
        verificar(f"{algoritmo}: colisoes >= 1", ">= 1", ex.recursos.colisoes_raio_x,
                  ex.recursos.colisoes_raio_x >= 1)

    print("\nA2. SEM sincronizacao, 10 medicos, 20 pacientes: contador x bruta x log")
    for algoritmo in (PRIORIDADE, ROUND_ROBIN):
        ex = rodar(algoritmo, 10, False, num_pacientes=20, com_callback=False)
        contador = ex.recursos.colisoes_raio_x
        trios = [(round(u.entrada, 3), round(u.saida, 3), u.paciente_id)
                 for u in ex.recursos.usos_raio_x]
        print(f"  {algoritmo}: trios (entrada, saida, paciente) = {trios}")
        bruta = forca_bruta_por_tempo(ex.recursos)
        bruta_ordem = ex.recursos.colisoes_por_forca_bruta()
        log = linhas_colisao(ex.saida)
        verificar(f"{algoritmo}: contador > 1", "> 1", contador, contador > 1)
        verificar(f"{algoritmo}: contador == forca bruta (tempo)", bruta, contador)
        verificar(f"{algoritmo}: contador == forca bruta (ordem)", bruta_ordem, contador)
        verificar(f"{algoritmo}: contador == linhas COLISAO no log", log, contador)
        ex2 = rodar(algoritmo, 10, False, num_pacientes=20)
        eventos = sum(1 for e in ex2.eventos if e[0] == "colisao")
        verificar(f"{algoritmo}: eventos 'colisao' == contador (2a execucao)",
                  ex2.recursos.colisoes_raio_x, eventos)
        verificar(f"{algoritmo}: ultimo 'total' do evento == contador",
                  ex2.recursos.colisoes_raio_x,
                  max([e[3]["total"] for e in ex2.eventos if e[0] == "colisao"], default=0))
        verificar(f"{algoritmo}: ocupantes == 0 ao final", 0, ex2.recursos._ocupantes_raio_x)

    print("\nA3. Tres ocupantes simultaneos = 2 colisoes (3 medicos, 3 pacientes)")
    ex = rodar(PRIORIDADE, 3, False, pacientes=[paciente(i, 1.0, raio_x=True) for i in (1, 2, 3)])
    verificar("colisoes", 2, ex.recursos.colisoes_raio_x)
    verificar("forca bruta", 2, forca_bruta_por_tempo(ex.recursos))

    print("\nA4. COM sincronizacao, 10 medicos, 20 pacientes: exatamente 0")
    for algoritmo in (PRIORIDADE, ROUND_ROBIN):
        ex = rodar(algoritmo, 10, True, num_pacientes=20)
        verificar(f"{algoritmo}: colisoes", 0, ex.recursos.colisoes_raio_x)
        verificar(f"{algoritmo}: forca bruta", 0, forca_bruta_por_tempo(ex.recursos))

    print("\nA5. Contadores zeram entre execucoes (nada global)")
    a = rodar(PRIORIDADE, 10, False, num_pacientes=20)
    b = rodar(PRIORIDADE, 10, False, num_pacientes=20)
    verificar("2a execucao nao acumula a 1a", True,
              b.recursos.colisoes_raio_x <= len(b.recursos.usos_raio_x) - 1,)
    verificar("objetos de recursos distintos", True, a.recursos is not b.recursos)


# --------------------------------------------------------------------------- B


def testes_rr() -> None:
    print("\n=== B) ROUND ROBIN (1 medico, modo COM) ===")

    print("\nB1. A (4,0 s) e B (1,0 s) em 0 s, quantum 1,0 s")
    ex = rodar(ROUND_ROBIN, 1, True, pacientes=[paciente(1, 4.0), paciente(2, 1.0)])
    verificar("rodizio", [1, 2, 1], ex.rodizio())
    verificar("ordem de conclusao (B, A)", [2, 1], ex.ordem_conclusao())
    verificar("preempcoes", 1, ex.preempcoes())
    a = ex.trechos and sum(t.fim - t.inicio for t in ex.trechos if t.paciente_id == 1 and t.fim <= 1.2)
    verificar("A rodou ~1 s antes de ceder", 1.0, round(a, 2), abs(a - 1.0) <= TOLERANCIA)

    print("\nB2. Chegada durante o turno: A (3,0 s) em 0 s; B (0,5 s) em 0,5 s")
    ex = rodar(ROUND_ROBIN, 1, True, pacientes=[paciente(1, 3.0), paciente(2, 0.5, 0.5)])
    verificar("B nao interrompe A (rodizio A, B, A)", [1, 2, 1], ex.rodizio())
    verificar("ordem de conclusao (B, A)", [2, 1], ex.ordem_conclusao())
    verificar("preempcoes (so o fim do quantum)", 1, ex.preempcoes())
    primeiro = min(t.inicio for t in ex.trechos if t.paciente_id == 2)
    verificar("B so comeca apos o quantum de A (>= 1,0 s)", ">= 1.0", round(primeiro, 2),
              primeiro >= 1.0 - 0.02)

    print("\nB3. Quantum 10 s com duracoes menores: comporta-se como FCFS")
    ex = rodar(ROUND_ROBIN, 1, True, quantum=10.0,
               pacientes=[paciente(1, 2.0), paciente(2, 1.5), paciente(3, 1.0)])
    verificar("preempcoes", 0, ex.preempcoes())
    verificar("ordem de conclusao (FCFS)", [1, 2, 3], ex.ordem_conclusao())

    print("\nB4. Restante preservado apos cada devolucao")
    ex = rodar(ROUND_ROBIN, 1, True, pacientes=[paciente(1, 3.0), paciente(2, 2.5)])
    for devolucao in ex.devolucoes():
        pid = devolucao["paciente_interrompido"]
        gasto = sum(t.fim - t.inicio for t in ex.trechos if t.paciente_id == pid
                    and t.inicio <= _instante_devolucao(ex, devolucao))
        duracao = next(p.duracao for p in ex.pacientes if p.id == pid)
        verificar(f"P{pid}: restante = duracao - tempo usado",
                  round(duracao - gasto, 3), round(devolucao["restante"], 3),
                  abs(duracao - gasto - devolucao["restante"]) < 1e-6)
        verificar(f"P{pid}: restante != duracao total", True,
                  devolucao["restante"] < duracao - 0.5)
    inicios = {p.id: p.inicio for p in ex.pacientes}
    primeira = {pid: min(t.inicio for t in ex.trechos if t.paciente_id == pid)
                for pid in inicios}
    verificar("'inicio' gravado so no primeiro atendimento", True,
              all(abs(inicios[p] - primeira[p]) < 0.05 for p in inicios))

    print("\nB5. Tres pacientes de 2,0 s juntos, quantum 1,0 s")
    ex = rodar(ROUND_ROBIN, 1, True, pacientes=[paciente(i, 2.0) for i in (1, 2, 3)])
    verificar("rodizio P1,P2,P3,P1,P2,P3", [1, 2, 3, 1, 2, 3], ex.rodizio())
    verificar("preempcoes (termino no fim do 2o turno nao conta)", 3, ex.preempcoes())

    print("\nB6. Fila FIFO: quem volta fica atras de quem ja esperava")
    ex = rodar(ROUND_ROBIN, 1, True, pacientes=[
        paciente(1, 2.0, 0.0, Gravidade.VERDE),
        paciente(2, 2.0, 0.1, Gravidade.AMARELO),
        paciente(3, 1.0, 0.2, Gravidade.VERMELHO),
    ])
    verificar("gravidade ignorada; P3 vermelho espera sua vez", [1, 2, 3, 1, 2], ex.rodizio())

    print("\nB7. Log do RR e quantum por medico (2 medicos, 4 pacientes)")
    ex = rodar(ROUND_ROBIN, 2, True, pacientes=[paciente(i, 2.5) for i in (1, 2, 3, 4)])
    textos = [d["texto"] for d in ex.devolucoes()]
    padrao = re.compile(r"^RR: P\d+ usou o quantum e voltou ao fim da fila \(restante \d+\.\d\d s\)$")
    verificar("mensagem no formato pedido", True, bool(textos) and all(padrao.match(t) for t in textos))
    print(f"    exemplo: {textos[0] if textos else '-'}")
    maximo = 0.0
    for t in ex.trechos:
        maximo = max(maximo, t.fim - t.inicio)
    verificar("cada medico respeita 1,0 s por turno (fatia <= quantum)", True, maximo <= 1.0 + TOLERANCIA)

    print("\nB8. Paciente com raio-X nao e interrompido dentro do recurso; esperar semaforo nao gasta quantum")
    pacientes = [paciente(1, 2.0, raio_x=True), paciente(2, 2.0, raio_x=True)]
    ex = rodar(ROUND_ROBIN, 2, True, pacientes=pacientes)
    verificar("ocupantes do raio-X == 0 ao final", 0, ex.recursos._ocupantes_raio_x)
    verificar("colisoes (COM)", 0, ex.recursos.colisoes_raio_x)
    verificar("todos concluidos", 2, ex.metricas.geral.quantidade)
    for p in pacientes:
        consulta = sum(t.fim - t.inicio for t in ex.trechos if t.paciente_id == p.id)
        verificar(f"P{p.id}: consulta = duracao (espera de semaforo nao conta)",
                  p.duracao, round(consulta, 2), abs(consulta - p.duracao) <= TOLERANCIA)
    verificar("sem deadlock", False, ex.travou)
    verificar("semaforo do raio-X livre ao final", True, ex.recursos._semaforo_raio_x.acquire(blocking=False))


def _instante_devolucao(ex: Execucao, devolucao: dict) -> float:
    """Instante simulado do evento de preempcao correspondente."""
    for evento in ex.eventos:
        if evento[0] == "preempcao" and evento[3] is devolucao:
            return evento[4]
    return float("inf")


# --------------------------------------------------------------------------- C


def testes_ps() -> None:
    print("\n=== C) PRIORIDADE PREEMPTIVA ===")

    print("\nC1. A verde (4,0 s) em 0 s; B vermelho (1,0 s) em 1,0 s; 1 medico")
    a = paciente(1, 4.0, 0.0, Gravidade.VERDE)
    b = paciente(2, 1.0, 1.0, Gravidade.VERMELHO)
    ex = rodar(PRIORIDADE, 1, True, pacientes=[a, b])
    verificar("preempcoes", 1, ex.preempcoes())
    verificar("B termina antes de A", [2, 1], ex.ordem_conclusao())
    restante = ex.devolucoes()[0]["restante"] if ex.devolucoes() else None
    verificar("restante de A na troca ~3,0 s", 3.0, restante and round(restante, 2),
              restante is not None and abs(restante - 3.0) <= 0.25)

    print("\nC2. Dois do mesmo nivel nao se interrompem")
    ex = rodar(PRIORIDADE, 1, True, pacientes=[
        paciente(1, 2.0, 0.0, Gravidade.AMARELO), paciente(2, 1.0, 0.5, Gravidade.AMARELO)])
    verificar("preempcoes", 0, ex.preempcoes())
    verificar("ordem de conclusao", [1, 2], ex.ordem_conclusao())

    print("\nC3. Menos grave nao interrompe mais grave")
    ex = rodar(PRIORIDADE, 1, True, pacientes=[
        paciente(1, 2.0, 0.0, Gravidade.VERMELHO), paciente(2, 1.0, 0.5, Gravidade.VERDE)])
    verificar("preempcoes", 0, ex.preempcoes())

    print("\nC4. Amarelo e interrompido por vermelho; desempate por chegada e id")
    ex = rodar(PRIORIDADE, 1, True, pacientes=[
        paciente(1, 2.0, 0.0, Gravidade.AMARELO),
        paciente(3, 0.5, 0.5, Gravidade.VERMELHO),
        paciente(2, 0.5, 0.5, Gravidade.VERMELHO)])
    verificar("ordem de conclusao (P2 antes de P3: mesmo nivel e chegada, menor id)",
              [2, 3, 1], ex.ordem_conclusao())
    verificar("preempcoes", 1, ex.preempcoes())


# --------------------------------------------------------------------------- D


def testes_metricas() -> None:
    print("\n=== D) METRICAS ===")
    for algoritmo in (PRIORIDADE, ROUND_ROBIN):
        print(f"\nD1. {algoritmo}: identidade E = R - duracao - tempo em recursos")
        ex = rodar(algoritmo, 2, True, num_pacientes=10)
        registros = [e[3]["registro"] for e in ex.eventos if e[0] == "medico_concluiu"]
        pior = max(abs(r.espera - (r.retorno - r.duracao - r.tempo_recursos)) for r in registros)
        verificar("max |E - (R - D - recursos)| <= 0,05 s", "<= 0.05", round(pior, 4), pior <= 0.05)
        sem_recurso = [r for r in registros if r.tempo_recursos == 0]
        pior = max((abs(r.espera - (r.retorno - r.duracao)) for r in sem_recurso), default=0)
        verificar(f"sem recursos ({len(sem_recurso)} pacientes): E = R - duracao", "<= 0.05",
                  round(pior, 4), pior <= 0.05)
        verificar("Resp <= E para todo paciente", True,
                  all(r.resposta <= r.espera + 1e-9 for r in registros))
        geral = ex.metricas.geral
        verificar("espera maxima >= espera media", True, geral.espera_max >= geral.espera)
        print("    espera max por gravidade: " + ", ".join(
            f"{g.name} {m.espera_max:.2f}s" for g, m in ex.metricas.por_gravidade.items() if m.quantidade))

    print("\nD1b. Caso sem recursos (1 medico, 3 pacientes): E = retorno - duracao")
    for algoritmo in (PRIORIDADE, ROUND_ROBIN):
        ex = rodar(algoritmo, 1, True, pacientes=[
            paciente(1, 2.5, 0.0, Gravidade.VERDE),
            paciente(2, 1.5, 0.3, Gravidade.AMARELO),
            paciente(3, 2.0, 0.6, Gravidade.VERMELHO)])
        registros = [e[3]["registro"] for e in ex.eventos if e[0] == "medico_concluiu"]
        for r in sorted(registros, key=lambda r: r.paciente_id):
            diferenca = abs(r.espera - (r.retorno - r.duracao))
            verificar(f"{algoritmo} P{r.paciente_id}: E={r.espera:.2f} R={r.retorno:.2f} "
                      f"D={r.duracao:.2f}", "|E-(R-D)| <= 0.02", round(diferenca, 4),
                      diferenca <= 0.02)

    print("\nD2. Mesma carga nas duas politicas")
    a = gerar_pacientes(42, 16)
    b = gerar_pacientes(42, 16)
    verificar("mesmo seed => mesmos pacientes", True,
              [(p.id, p.gravidade, p.duracao, p.chegada) for p in a]
              == [(p.id, p.gravidade, p.duracao, p.chegada) for p in b])
    print(f"    Carga: {len(a)} pacientes / {sum(p.duracao for p in a):.1f} s de consulta")


# --------------------------------------------------------------------------- E


def testes_regressao() -> None:
    print("\n=== E) REGRESSAO GERAL ===")

    print("\nE1. Modo SEM mostra os 3 erros; modo COM nao mostra nenhum")
    for algoritmo in (PRIORIDADE, ROUND_ROBIN):
        sem = rodar(algoritmo, 10, False, num_pacientes=40)
        com = rodar(algoritmo, 10, True, num_pacientes=40)
        verificar(f"{algoritmo} SEM: colisoes > 0", "> 0", sem.recursos.colisoes_raio_x,
                  sem.recursos.colisoes_raio_x > 0)
        verificar(f"{algoritmo} SEM: leitos livres != 0 (esperado 0)", "!= 0",
                  sem.recursos.leitos_livres, sem.recursos.leitos_livres != 0)
        verificar(f"{algoritmo} SEM: notas salvas < total", "<",
                  f"{sem.recursos.notas_salvas}/{sem.recursos.gravacoes_concluidas}",
                  sem.recursos.notas_salvas < sem.recursos.gravacoes_concluidas)
        verificar(f"{algoritmo} COM: colisoes", 0, com.recursos.colisoes_raio_x)
        verificar(f"{algoritmo} COM: leitos livres", 0, com.recursos.leitos_livres)
        verificar(f"{algoritmo} COM: notas salvas == total", com.recursos.gravacoes_concluidas,
                  com.recursos.notas_salvas)

    print("\nE2. Sem deadlock: 12 medicos e 60 pacientes, 2 politicas x 2 modos")
    for algoritmo in (PRIORIDADE, ROUND_ROBIN):
        for sincronizado in (False, True):
            inicio = time.monotonic()
            ex = rodar(algoritmo, 12, sincronizado, num_pacientes=60,
                       velocidade=8.0, limite=90.0)
            nome = f"{algoritmo} {'COM' if sincronizado else 'SEM'}"
            verificar(f"{nome}: terminou sem travar", False, ex.travou)
            verificar(f"{nome}: 60 concluidos", 60, ex.metricas.geral.quantidade if ex.metricas else 0)
            print(f"      ({time.monotonic() - inicio:.1f} s reais; colisoes={ex.recursos.colisoes_raio_x}"
                  f", preempcoes={ex.recursos.preempcoes})")

    print("\nE3. Sem busy waiting: medico ocioso espera na Condition")
    cpu = time.process_time()
    ex = rodar(PRIORIDADE, 2, True, pacientes=[paciente(1, 0.2, chegada=6.0)], velocidade=4.0)
    gasto = time.process_time() - cpu
    verificar("CPU gasta durante ~1,5 s de espera real", "< 0.4 s", round(gasto, 3), gasto < 0.4)

    print("\nE4. Threads dos medicos so postam eventos (sem acesso a interface)")
    ok = True
    for arquivo in ("medico.py", "recursos.py", "escalonador.py", "main.py"):
        with open(arquivo, encoding="utf-8") as f:
            codigo = f.read()
        ok &= "tkinter" not in codigo and "messagebox" not in codigo
    verificar("nenhum modulo de simulacao importa tkinter", True, ok)
    with open("gui.py", encoding="utf-8") as f:
        codigo = f.read()
    verificar("GUI entrega eventos por queue.Queue", True,
              "self.eventos.put" in codigo and "self.eventos.get_nowait" in codigo)

    print("\nE5. Fechar a janela encerra as threads sem travar")
    try:
        import tkinter as tk
        from gui import ProntoSocorroGUI

        raiz = tk.Tk()
        raiz.withdraw()
        gui = ProntoSocorroGUI(raiz)
        gui.medicos_var.set("4")
        gui.pacientes_var.set("20")
        gui.iniciar()
        fim = time.monotonic() + 1.2
        while time.monotonic() < fim:
            raiz.update()
            time.sleep(0.01)
        antes = threading.active_count()
        inicio = time.monotonic()
        gui.fechar()
        for _ in range(100):
            if threading.active_count() <= 2:
                break
            time.sleep(0.05)
        verificar("threads vivas apos fechar", "<= 2", threading.active_count(),
                  threading.active_count() <= 2)
        verificar("fechar em menos de 3 s", "< 3.0", round(time.monotonic() - inicio, 2),
                  time.monotonic() - inicio < 3.0)
        print(f"      (threads antes de fechar: {antes})")
    except Exception as erro:  # sem display, por exemplo
        print(f"  [PULADO] teste de interface: {erro!r}")


GRUPOS_TESTE = {
    "colisao": testes_colisao,
    "rr": testes_rr,
    "ps": testes_ps,
    "metricas": testes_metricas,
    "regressao": testes_regressao,
}


def main() -> int:
    escolhidos = sys.argv[1:] or list(GRUPOS_TESTE)
    for nome in escolhidos:
        GRUPOS_TESTE[nome]()
    passou = sum(resultados)
    print(f"\nResumo: {passou} PASSOU, {len(resultados) - passou} FALHOU de {len(resultados)} verificacoes.")
    return 0 if passou == len(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
