"""Menu do Trabalho Pratico 3 - Semaforos."""

import argparse
import random
import threading

from controle import CallbackEvento, ControleSimulacao
from escalonador import (
    ALGORITMOS,
    PRIORIDADE,
    QUANTUM_PADRAO,
    ROUND_ROBIN,
    Escalonador,
    descrever_algoritmo,
)
from medico import Medico
from metricas import (
    Metricas,
    calcular_metricas,
    formatar_segundos,
    imprimir_comparacao,
    imprimir_metricas,
)
from modelos import Gravidade, Paciente, RegistroAtendimento, TrechoGantt
from recursos import RecursosCompartilhados, Fore


# O menu altera esta flag para executar os dois experimentos.
USAR_SINCRONIZACAO = True
MOSTRAR_GANTT = False
NUM_MEDICOS = 2
NUM_PACIENTES = 16
ALGORITMO = PRIORIDADE
QUANTUM = QUANTUM_PADRAO


def gerar_pacientes(semente: int, num_pacientes: int) -> list[Paciente]:
    """Gera uma carga reproduzivel; os dois primeiros disputam recursos juntos.

    Depende SO de (semente, num_pacientes): PS e RR recebem exatamente os mesmos
    pacientes. Tempos em segundos simulados: consultas de 1,2 a 3,0 s (com quantum
    de 1,0 s o RR faz de 1 a 3 turnos) e chegadas espacadas de 0,15 a 0,45 s.
    """
    gerador = random.Random(semente)
    vermelhos = min(num_pacientes, max(1, int(num_pacientes * 0.25 + 0.5)))
    amarelos = min(
        num_pacientes - vermelhos,
        max(0, int(num_pacientes / 3 + 0.5)),
    )
    verdes = num_pacientes - vermelhos - amarelos
    gravidades = (
        [Gravidade.VERMELHO] * vermelhos
        + [Gravidade.AMARELO] * amarelos
        + [Gravidade.VERDE] * verdes
    )

    # Mantem uma chegada de alta prioridade depois de outras classes quando possivel.
    prefixo = []
    if vermelhos >= 2 and amarelos >= 1 and verdes >= 1:
        prefixo = [
            Gravidade.VERMELHO,
            Gravidade.AMARELO,
            Gravidade.VERDE,
            Gravidade.VERMELHO,
        ]
        for gravidade in prefixo:
            gravidades.remove(gravidade)
    gerador.shuffle(gravidades)
    gravidades = prefixo + gravidades

    total = num_pacientes
    usuarios_leito = set(range(min(2, total)))
    if total > 2:
        usuarios_leito.add(gerador.randrange(2, total))
    pacientes: list[Paciente] = []
    chegada = 0.0
    for indice, gravidade in enumerate(gravidades):
        if indice >= 2:
            chegada += gerador.uniform(0.15, 0.45)
        pacientes.append(
            Paciente(
                id=indice + 1,
                gravidade=gravidade,
                duracao=gerador.uniform(1.2, 3.0),
                chegada=chegada,
                restante=0.0,
                usa_raio_x=indice < 2 or gerador.random() < 0.35,
                usa_leito=indice in usuarios_leito,
                usa_prontuario=indice < 2 or gerador.random() < 0.6,
            )
        )
        pacientes[-1].restante = pacientes[-1].duracao
    return pacientes


def executar_simulacao(
    usar_sincronizacao: bool,
    semente: int,
    num_medicos: int = NUM_MEDICOS,
    num_pacientes: int = NUM_PACIENTES,
    mostrar_gantt: bool = False,
    callback_evento: CallbackEvento | None = None,
    controle: ControleSimulacao | None = None,
    mostrar_saida_terminal: bool = True,
    algoritmo: str = PRIORIDADE,
    quantum: float = QUANTUM_PADRAO,
    pacientes: list[Paciente] | None = None,
    trechos: list[TrechoGantt] | None = None,
) -> tuple[RecursosCompartilhados, Metricas]:
    """Roda uma simulacao completa.

    pacientes e trechos existem para testes: permitem injetar uma carga propria
    e inspecionar o que cada medico executou.
    """
    if pacientes is None:
        pacientes = gerar_pacientes(semente, num_pacientes)
    else:
        num_pacientes = len(pacientes)
    controle = controle or ControleSimulacao()
    recursos = RecursosCompartilhados(
        usar_sincronizacao, controle, callback_evento
    )

    def publicar_evento(
        tipo: str,
        medico_id: int | None,
        paciente_id: int | None,
        dados: dict[str, object],
    ) -> None:
        recursos.emitir_evento(tipo, medico_id, paciente_id, dados)

    escalonador = Escalonador(
        pacientes, controle, publicar_evento, algoritmo, quantum
    )
    if trechos is None:
        trechos = []
    lock_trechos = threading.Lock()
    modo = "COM sincronizacao" if usar_sincronizacao else "SEM sincronizacao"
    nome_algoritmo = descrever_algoritmo(algoritmo, quantum)
    if mostrar_saida_terminal:
        print(
            f"\n{Fore.CYAN}=== {modo} | {num_medicos} médicos | "
            f"{num_pacientes} pacientes | {nome_algoritmo} | seed={semente} ==="
        )

    medicos = [
        Medico(i, escalonador, recursos, trechos, lock_trechos)
        for i in range(1, num_medicos + 1)
    ]
    thread_chegadas = threading.Thread(
        target=escalonador.publicar_chegadas,
        name="Publicador-chegadas",
        daemon=True,
    )
    thread_chegadas.start()
    for medico in medicos:
        medico.start()
    for medico in medicos:
        medico.join()
    thread_chegadas.join()

    recursos.preempcoes = escalonador.preempcoes
    if controle.parada:
        recursos.liberar_leitos_ao_parar()
    if mostrar_gantt:
        from gantt import mostrar_gantt

        mostrar_gantt(trechos, f"{modo} - {nome_algoritmo}", num_medicos)
    # Mesmo criterio do painel da interface: somente pacientes concluidos.
    metricas = calcular_metricas(
        RegistroAtendimento.de_paciente(paciente)
        for paciente in pacientes
        if paciente.fim is not None
    )
    concluidos = metricas.geral.quantidade
    notas_salvas = recursos.notas_salvas
    recursos.emitir_evento(
        "fim",
        dados={
            "modo": modo,
            "algoritmo": algoritmo,
            "num_medicos": num_medicos,
            "num_pacientes": num_pacientes,
            "concluidos": concluidos,
            "colisoes": recursos.colisoes_raio_x,
            "carga_pacientes": len(pacientes),
            "carga_consulta": sum(paciente.duracao for paciente in pacientes),
            "quantum": quantum,
            "leitos_livres": recursos.leitos_livres,
            "notas_salvas": notas_salvas,
            "notas_total": recursos.gravacoes_concluidas,
            "preempcoes": escalonador.preempcoes,
            "metricas": metricas,
            "cancelada": controle.parada,
        },
        mensagem=(
            f"Concluido: {concluidos}/{len(pacientes)} pacientes; preempcoes="
            f"{escalonador.preempcoes}; notas salvas={notas_salvas}/"
            f"{recursos.gravacoes_concluidas}."
        ),
        cor=Fore.GREEN,
    )
    if mostrar_saida_terminal:
        imprimir_metricas(metricas, f"Metricas - {modo} - {nome_algoritmo}")
    return recursos, metricas


def imprimir_placar(
    recursos_sem: RecursosCompartilhados,
    recursos_com: RecursosCompartilhados,
    num_medicos: int,
    num_pacientes: int,
) -> None:
    print(
        f"\nPlacar de recursos compartilhados: {num_medicos} médicos | "
        f"{num_pacientes} pacientes"
    )
    print("Modo             Colisoes raio-X  Leitos livres  Notas salvas / esperadas")
    for nome, recursos in (
        ("SEM sincronizacao", recursos_sem),
        ("COM sincronizacao", recursos_com),
    ):
        print(
            f"{nome:<18} {recursos.colisoes_raio_x:>8}"
            f" {recursos.leitos_livres:>14}"
            f" {recursos.notas_salvas:>10} / {recursos.gravacoes_concluidas:<10}"
        )
    print("Esperado no modo COM: 0 colisoes, 0 leitos livres e todas as notas salvas.")


def perguntar_quantidade(rotulo: str, padrao: int) -> int:
    while True:
        valor = input(f"Quantos {rotulo}? [{padrao}]: ").strip()
        if not valor:
            return padrao
        try:
            quantidade = int(valor)
        except ValueError:
            quantidade = 0
        if quantidade > 0:
            return quantidade
        print("Informe um numero inteiro maior que zero.")


def perguntar_algoritmo(padrao: str) -> str:
    opcoes = list(ALGORITMOS)
    descricao = ", ".join(
        f"{indice} = {descrever_algoritmo(algoritmo, QUANTUM)}"
        for indice, algoritmo in enumerate(opcoes, start=1)
    )
    while True:
        valor = input(
            f"Algoritmo de escalonamento ({descricao})? "
            f"[{opcoes.index(padrao) + 1}]: "
        ).strip()
        if not valor:
            return padrao
        try:
            indice = int(valor)
        except ValueError:
            indice = 0
        if 1 <= indice <= len(opcoes):
            return opcoes[indice - 1]
        print("Escolha uma das opcoes listadas.")


def executar_bateria(
    semente: int, mostrar_gantt: bool, algoritmo: str, quantum: float = QUANTUM_PADRAO
) -> None:
    combinacoes = [(2, 16), (10, 16), (2, 40), (10, 40)]
    resultados: list[tuple[int, int, bool, RecursosCompartilhados, Metricas]] = []
    for num_medicos, num_pacientes in combinacoes:
        for sincronizado in (False, True):
            recursos, metricas = executar_simulacao(
                sincronizado,
                semente,
                num_medicos,
                num_pacientes,
                mostrar_gantt,
                algoritmo=algoritmo,
                quantum=quantum,
            )
            resultados.append(
                (num_medicos, num_pacientes, sincronizado, recursos, metricas)
            )

    print(f"\nResultado da bateria de testes - {descrever_algoritmo(algoritmo, quantum)}")
    print(
        "Medicos Pacientes Modo               Colisoes raio-X  Leitos livres"
        "  Notas salvas/total  Espera media"
    )
    for num_medicos, num_pacientes, sincronizado, recursos, metricas in resultados:
        modo = "COM" if sincronizado else "SEM"
        print(
            f"{num_medicos:>7} {num_pacientes:>9} {modo:<18}"
            f" {recursos.colisoes_raio_x:>8}"
            f" {recursos.leitos_livres:>14}"
            f" {recursos.notas_salvas:>7}/{recursos.gravacoes_concluidas:<10}"
            f" {formatar_segundos(metricas.geral.espera):>11}"
        )


def comparar_algoritmos(
    semente: int,
    num_medicos: int,
    num_pacientes: int,
    mostrar_gantt: bool,
    usar_sincronizacao: bool = True,
    quantum: float = QUANTUM_PADRAO,
) -> None:
    """Roda o mesmo cenario (seed, modo e carga) em cada politica e compara."""
    linhas = []
    for algoritmo in ALGORITMOS:
        recursos, metricas = executar_simulacao(
            usar_sincronizacao,
            semente,
            num_medicos,
            num_pacientes,
            mostrar_gantt,
            algoritmo=algoritmo,
            quantum=quantum,
        )
        linhas.append((algoritmo, metricas, recursos))
    carga = gerar_pacientes(semente, num_pacientes)
    print(
        f"\nComparar politicas ({'COM' if usar_sincronizacao else 'SEM'} sincronizacao): "
        f"{num_medicos} médicos | seed={semente}"
    )
    print(
        f"Carga: {len(carga)} pacientes / "
        f"{sum(p.duracao for p in carga):.1f} s de consulta"
    )
    imprimir_comparacao(
        [
            (
                descrever_algoritmo(algoritmo, quantum),
                metricas,
                recursos.preempcoes,
                recursos.colisoes_raio_x,
            )
            for algoritmo, metricas, recursos in linhas
        ]
    )


def executar_menu(semente: int, mostrar_gantt: bool) -> None:
    global ALGORITMO, NUM_MEDICOS, NUM_PACIENTES, USAR_SINCRONIZACAO
    while True:
        print(
            "\nPronto-Socorro Concorrente\n"
            f"Algoritmo atual: {descrever_algoritmo(ALGORITMO, QUANTUM)}\n"
            "1 - Executar sem sincronizacao\n"
            "2 - Executar com sincronizacao\n"
            "3 - Comparar os dois modos\n"
            "4 - Rodar bateria de testes (algoritmo atual)\n"
            "5 - Comparar políticas (Prioridade preemptiva × Round Robin)\n"
            "0 - Sair"
        )
        opcao = input("Opcao: ").strip()
        if opcao == "0":
            return
        if opcao in {"1", "2"}:
            NUM_MEDICOS = perguntar_quantidade("médicos", NUM_MEDICOS)
            NUM_PACIENTES = perguntar_quantidade("pacientes", NUM_PACIENTES)
            ALGORITMO = perguntar_algoritmo(ALGORITMO)
            USAR_SINCRONIZACAO = opcao == "2"
            executar_simulacao(
                USAR_SINCRONIZACAO,
                semente,
                NUM_MEDICOS,
                NUM_PACIENTES,
                mostrar_gantt,
                algoritmo=ALGORITMO,
                quantum=QUANTUM,
            )
        elif opcao == "3":
            NUM_MEDICOS = perguntar_quantidade("médicos", NUM_MEDICOS)
            NUM_PACIENTES = perguntar_quantidade("pacientes", NUM_PACIENTES)
            ALGORITMO = perguntar_algoritmo(ALGORITMO)
            USAR_SINCRONIZACAO = False
            recursos_sem, _ = executar_simulacao(
                USAR_SINCRONIZACAO,
                semente,
                NUM_MEDICOS,
                NUM_PACIENTES,
                mostrar_gantt,
                algoritmo=ALGORITMO,
                quantum=QUANTUM,
            )
            USAR_SINCRONIZACAO = True
            recursos_com, _ = executar_simulacao(
                USAR_SINCRONIZACAO,
                semente,
                NUM_MEDICOS,
                NUM_PACIENTES,
                mostrar_gantt,
                algoritmo=ALGORITMO,
                quantum=QUANTUM,
            )
            imprimir_placar(
                recursos_sem, recursos_com, NUM_MEDICOS, NUM_PACIENTES
            )
        elif opcao == "4":
            executar_bateria(semente, mostrar_gantt, ALGORITMO, QUANTUM)
        elif opcao == "5":
            NUM_MEDICOS = perguntar_quantidade("médicos", NUM_MEDICOS)
            NUM_PACIENTES = perguntar_quantidade("pacientes", NUM_PACIENTES)
            comparar_algoritmos(
                semente, NUM_MEDICOS, NUM_PACIENTES, mostrar_gantt, quantum=QUANTUM
            )
        else:
            print("Opcao invalida.")


def main() -> None:
    global ALGORITMO, QUANTUM
    parser = argparse.ArgumentParser(description="Simulador concorrente de pronto-socorro")
    parser.add_argument("--seed", type=int, default=42, help="semente para resultados reproduziveis")
    parser.add_argument("--gantt", action="store_true", help="exibe o Gantt (requer matplotlib)")
    parser.add_argument(
        "--algoritmo",
        choices=list(ALGORITMOS),
        default=ALGORITMO,
        help=f"escalonamento inicial: {PRIORIDADE} (prioridade preemptiva) ou {ROUND_ROBIN} (Round Robin)",
    )
    parser.add_argument(
        "--quantum",
        type=float,
        default=QUANTUM_PADRAO,
        help="quantum do Round Robin em segundos simulados (padrao 1,0)",
    )
    argumentos = parser.parse_args()
    if argumentos.quantum <= 0:
        parser.error("--quantum precisa ser maior que zero")
    QUANTUM = argumentos.quantum
    ALGORITMO = argumentos.algoritmo
    executar_menu(argumentos.seed, argumentos.gantt or MOSTRAR_GANTT)


if __name__ == "__main__":
    main()
