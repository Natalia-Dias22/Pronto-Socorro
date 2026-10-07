"""Menu do Trabalho Pratico 3 - Semaforos."""

import argparse
import random
import threading
import time

from controle import CallbackEvento, ControleSimulacao
from escalonador import Escalonador, PoliticaEscalonamento
from medico import Medico
from metricas import Metricas, calcular_metricas, imprimir_metricas
from modelos import Gravidade, Paciente, TrechoGantt
from recursos import RecursosCompartilhados, Fore


# O menu altera esta flag para executar os dois experimentos.
USAR_SINCRONIZACAO = True
MOSTRAR_GANTT = False
NUM_MEDICOS = 2
NUM_PACIENTES = 16

# Janela padrao (em segundos de tempo simulado) em que as chegadas a partir do
# terceiro paciente sao espalhadas uniformemente. Chegadas mais espalhadas (em
# vez de quase todas no instante zero) criam sobreposicoes reais entre
# consultas, o cenario necessario para que a preempcao por tempo (SJF/SRTF)
# tenha chance de acontecer.
JANELA_CHEGADAS = 10.0

# Distribuicao de duracoes: a maior parte das consultas e curta, mas uma
# fracao e bem mais longa. E essa mistura que permite que um paciente de
# consulta curta, ao chegar durante uma consulta longa em andamento, tenha
# RESTANTE menor que o da consulta longa e dispare uma preempcao SRTF.
PROPORCAO_DURACAO_LONGA = 0.3
DURACAO_LONGA = (3.0, 5.0)
DURACAO_CURTA = (0.3, 1.0)


def gerar_pacientes(
    semente: int,
    num_pacientes: int,
    janela_chegadas: float = JANELA_CHEGADAS,
) -> list[Paciente]:
    """Gera uma carga reproduzivel; os dois primeiros disputam recursos juntos."""
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

    # Os dois primeiros pacientes chegam juntos (t=0) para disputar os
    # recursos compartilhados desde o inicio. Os demais sao espalhados de
    # forma uniforme e reproduzivel dentro da janela configurada, em vez de
    # quase todos chegarem nos primeiros instantes.
    num_extras = max(0, total - 2)
    chegadas_extras = sorted(
        gerador.uniform(0.0, max(0.0, janela_chegadas)) for _ in range(num_extras)
    )

    pacientes: list[Paciente] = []
    for indice, gravidade in enumerate(gravidades):
        chegada = 0.0 if indice < 2 else chegadas_extras[indice - 2]
        # 30% das consultas sao longas (3 a 5s) e 70% sao curtas (0.3 a 1s).
        if gerador.random() < PROPORCAO_DURACAO_LONGA:
            duracao = gerador.uniform(*DURACAO_LONGA)
        else:
            duracao = gerador.uniform(*DURACAO_CURTA)
        pacientes.append(
            Paciente(
                id=indice + 1,
                gravidade=gravidade,
                duracao=duracao,
                chegada=chegada,
                restante=duracao,
                usa_raio_x=indice < 2 or gerador.random() < 0.35,
                usa_leito=indice in usuarios_leito,
                usa_prontuario=indice < 2 or gerador.random() < 0.6,
            )
        )
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
    politica: PoliticaEscalonamento | str = PoliticaEscalonamento.PRIORIDADE,
    janela_chegadas: float = JANELA_CHEGADAS,
) -> tuple[RecursosCompartilhados, Metricas]:
    pacientes = gerar_pacientes(semente, num_pacientes, janela_chegadas)
    controle = controle or ControleSimulacao()
    instante_zero = time.monotonic()
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
        pacientes, instante_zero, controle, publicar_evento, politica
    )
    trechos: list[TrechoGantt] = []
    lock_trechos = threading.Lock()
    modo = "COM sincronizacao" if usar_sincronizacao else "SEM sincronizacao"
    if mostrar_saida_terminal:
        print(
            f"\n{Fore.CYAN}=== {modo} | {num_medicos} médicos | "
            f"{num_pacientes} pacientes | {PoliticaEscalonamento(politica).value} "
            f"preemptivo | seed={semente} ==="
        )

    medicos = [
        Medico(i, escalonador, recursos, instante_zero, trechos, lock_trechos)
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

    if controle.parada:
        recursos.liberar_leitos_ao_parar()
    if mostrar_gantt:
        from gantt import mostrar_gantt

        mostrar_gantt(
            trechos, f"{modo} - {PoliticaEscalonamento(politica).value} preemptivo"
        )
    metricas = calcular_metricas(pacientes)
    recursos.emitir_evento(
        "fim",
        dados={
            "modo": modo,
            "num_medicos": num_medicos,
            "num_pacientes": num_pacientes,
            "concluidos": sum(paciente.fim is not None for paciente in pacientes),
            "colisoes": recursos.colisoes_raio_x,
            "leitos_livres": recursos.leitos_livres,
            "notas_salvas": len(recursos.notas),
            "notas_total": recursos.tentativas_gravacao,
            "preempcoes": escalonador.preempcoes,
            "metricas": metricas,
            "registros": [
                {
                    "id": paciente.id,
                    "gravidade": paciente.gravidade.name,
                    "duracao": paciente.duracao,
                    "chegada": paciente.chegada,
                    "inicio": paciente.inicio,
                    "fim": paciente.fim,
                    "espera": max(
                        0.0, (paciente.inicio or 0.0) - paciente.chegada
                    ),
                    "retorno": max(
                        0.0, (paciente.fim or 0.0) - paciente.chegada
                    ),
                }
                for paciente in pacientes
                if paciente.fim is not None
            ],
            "cancelada": controle.parada,
        },
        mensagem=(
            f"Concluido: {len(pacientes)} pacientes; preempcoes="
            f"{escalonador.preempcoes}; notas salvas={len(recursos.notas)}/"
            f"{recursos.tentativas_gravacao}."
        ),
        cor=Fore.GREEN,
    )
    if mostrar_saida_terminal:
        imprimir_metricas(metricas, f"Metricas - {modo}")
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
            f" {len(recursos.notas):>10} / {recursos.tentativas_gravacao:<10}"
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


def executar_bateria(semente: int, mostrar_gantt: bool) -> None:
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
            )
            resultados.append(
                (num_medicos, num_pacientes, sincronizado, recursos, metricas)
            )

    print("\nResultado da bateria de testes")
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
            f" {len(recursos.notas):>7}/{recursos.tentativas_gravacao:<10}"
            f" {metricas.espera_media:>10.3f}s"
        )


def executar_menu(semente: int, mostrar_gantt: bool) -> None:
    global NUM_MEDICOS, NUM_PACIENTES, USAR_SINCRONIZACAO
    while True:
        print(
            "\nPronto-Socorro Concorrente\n"
            "1 - Executar sem sincronizacao\n"
            "2 - Executar com sincronizacao\n"
            "3 - Comparar os dois modos\n"
            "4 - Rodar bateria de testes\n"
            "0 - Sair"
        )
        opcao = input("Opcao: ").strip()
        if opcao == "0":
            return
        if opcao in {"1", "2"}:
            NUM_MEDICOS = perguntar_quantidade("médicos", NUM_MEDICOS)
            NUM_PACIENTES = perguntar_quantidade("pacientes", NUM_PACIENTES)
            USAR_SINCRONIZACAO = opcao == "2"
            executar_simulacao(
                USAR_SINCRONIZACAO,
                semente,
                NUM_MEDICOS,
                NUM_PACIENTES,
                mostrar_gantt,
            )
        elif opcao == "3":
            NUM_MEDICOS = perguntar_quantidade("médicos", NUM_MEDICOS)
            NUM_PACIENTES = perguntar_quantidade("pacientes", NUM_PACIENTES)
            USAR_SINCRONIZACAO = False
            recursos_sem, _ = executar_simulacao(
                USAR_SINCRONIZACAO,
                semente,
                NUM_MEDICOS,
                NUM_PACIENTES,
                mostrar_gantt,
            )
            USAR_SINCRONIZACAO = True
            recursos_com, _ = executar_simulacao(
                USAR_SINCRONIZACAO,
                semente,
                NUM_MEDICOS,
                NUM_PACIENTES,
                mostrar_gantt,
            )
            imprimir_placar(
                recursos_sem, recursos_com, NUM_MEDICOS, NUM_PACIENTES
            )
        elif opcao == "4":
            executar_bateria(semente, mostrar_gantt)
        else:
            print("Opcao invalida.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador concorrente de pronto-socorro")
    parser.add_argument("--seed", type=int, default=42, help="semente para resultados reproduziveis")
    parser.add_argument("--gantt", action="store_true", help="exibe o Gantt (requer matplotlib)")
    argumentos = parser.parse_args()
    executar_menu(argumentos.seed, argumentos.gantt or MOSTRAR_GANTT)


if __name__ == "__main__":
    main()