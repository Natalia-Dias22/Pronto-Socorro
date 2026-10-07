"""Testes automatizados da preempcao por tempo (SJF/SRTF) e por prioridade.

Cada teste monta um cenario minimo (1 medico, modo COM sincronizacao, seed
fixo) e verifica o numero de preempcoes e, quando aplicavel, a ordem de
conclusao dos pacientes. Os testes rodam a simulacao de verdade (threads reais
de Medico/Escalonador), sem mockar relogio nem fila: e a mesma engine usada
pela GUI e pelo main.py.

Uso:
    python testes_preempcao.py
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from controle import ControleSimulacao
from escalonador import Escalonador, PoliticaEscalonamento
from medico import Medico
from modelos import Gravidade, Paciente
from recursos import RecursosCompartilhados

# Velocidade alta so para os testes rodarem rapido; nao influencia o
# resultado logico porque o 'restante' agora e descontado pelo tempo
# REALMENTE transcorrido em cada fatia (ver medico.py), nao por um valor
# nominal fixo.
VELOCIDADE_TESTE = 8.0


@dataclass
class ResultadoTeste:
    nome: str
    descricao: str
    esperado: str
    obtido: str
    passou: bool


def _rodar_cenario(
    pacientes: list[Paciente],
    politica: PoliticaEscalonamento,
    num_medicos: int = 1,
    velocidade: float = VELOCIDADE_TESTE,
) -> int:
    """Executa pacientes/politica num cenario COM sincronizacao e devolve o
    numero de preempcoes observadas pelo escalonador."""
    controle = ControleSimulacao(velocidade=velocidade)
    recursos = RecursosCompartilhados(True, controle, None)
    instante_zero = time.monotonic()
    escalonador = Escalonador(
        pacientes, instante_zero, controle, lambda *a: None, politica
    )
    trechos: list = []
    lock_trechos = threading.Lock()
    medicos = [
        Medico(i + 1, escalonador, recursos, instante_zero, trechos, lock_trechos, fatia=0.1)
        for i in range(num_medicos)
    ]
    thread_chegadas = threading.Thread(
        target=escalonador.publicar_chegadas, daemon=True
    )
    thread_chegadas.start()
    for medico in medicos:
        medico.start()
    for medico in medicos:
        medico.join()
    thread_chegadas.join()
    return escalonador.preempcoes


def teste_1_sjf_preempta() -> ResultadoTeste:
    """SJF: paciente curto chegando durante um atendimento longo preempta."""
    a = Paciente(id=1, gravidade=Gravidade.VERDE, duracao=4.0, chegada=0.0, restante=4.0)
    b = Paciente(id=2, gravidade=Gravidade.VERDE, duracao=0.5, chegada=1.0, restante=0.5)
    preempcoes = _rodar_cenario([a, b], PoliticaEscalonamento.SJF)
    ordem_ok = a.fim is not None and b.fim is not None and b.fim < a.fim
    passou = preempcoes == 1 and ordem_ok
    return ResultadoTeste(
        nome="Teste 1 - SJF preempta (restante menor chega durante o atendimento)",
        descricao=(
            "A (dur=4.0s, chega em 0s) e B (dur=0.5s, chega em 1.0s). "
            "Esperado: 1 preempcao perto de t=1.0s, B atendido primeiro, "
            "A retoma com restante ~3.0s e termina depois (ordem: B, A)."
        ),
        esperado="preempcoes=1; ordem de conclusao B antes de A",
        obtido=(
            f"preempcoes={preempcoes}; fim(A)={a.fim}; fim(B)={b.fim}; "
            f"ordem_B_antes_A={ordem_ok}"
        ),
        passou=passou,
    )


def teste_2_sjf_sem_preempcao() -> ResultadoTeste:
    """SJF: paciente mais longo que o restante do atual NAO preempta."""
    a = Paciente(id=1, gravidade=Gravidade.VERDE, duracao=1.0, chegada=0.0, restante=1.0)
    b = Paciente(id=2, gravidade=Gravidade.VERDE, duracao=2.0, chegada=0.5, restante=2.0)
    preempcoes = _rodar_cenario([a, b], PoliticaEscalonamento.SJF)
    passou = preempcoes == 0
    return ResultadoTeste(
        nome="Teste 2 - SJF sem preempcao (candidato mais longo que o restante)",
        descricao=(
            "A (dur=1.0s, chega em 0s) e B (dur=2.0s, chega em 0.5s). "
            "Em t=0.5s o restante de A e ~0.5s, menor que os 2.0s de B: "
            "nao deve haver preempcao."
        ),
        esperado="preempcoes=0",
        obtido=f"preempcoes={preempcoes}",
        passou=passou,
    )


def teste_3_sjf_compara_restante_nao_duracao() -> ResultadoTeste:
    """Prova que a comparacao usa o RESTANTE, nao a duracao total."""
    a = Paciente(id=1, gravidade=Gravidade.VERDE, duracao=4.0, chegada=0.0, restante=4.0)
    b = Paciente(id=2, gravidade=Gravidade.VERDE, duracao=1.0, chegada=3.5, restante=1.0)
    preempcoes = _rodar_cenario([a, b], PoliticaEscalonamento.SJF)
    passou = preempcoes == 0
    return ResultadoTeste(
        nome="Teste 3 - SJF compara RESTANTE, nao a duracao total",
        descricao=(
            "A (dur=4.0s, chega em 0s) e B (dur=1.0s, chega em 3.5s). "
            "A duracao TOTAL de A (4.0s) e maior que a de B (1.0s), mas em "
            "t=3.5s o RESTANTE de A e so ~0.5s, menor que o 1.0s de B: "
            "nao deve haver preempcao. Se a comparacao usasse a duracao "
            "total por engano, haveria uma preempcao incorreta aqui."
        ),
        esperado="preempcoes=0",
        obtido=f"preempcoes={preempcoes}",
        passou=passou,
    )


def teste_4_prioridade_preempta() -> ResultadoTeste:
    """Prioridade: paciente mais grave chegando durante o atendimento preempta."""
    a = Paciente(id=1, gravidade=Gravidade.VERDE, duracao=4.0, chegada=0.0, restante=4.0)
    b = Paciente(id=2, gravidade=Gravidade.VERMELHO, duracao=1.0, chegada=1.0, restante=1.0)
    preempcoes = _rodar_cenario([a, b], PoliticaEscalonamento.PRIORIDADE)
    passou = preempcoes == 1
    return ResultadoTeste(
        nome="Teste 4 - Preempcao por prioridade",
        descricao=(
            "A (VERDE, dur=4.0s, chega em 0s) e B (VERMELHO, dur=1.0s, "
            "chega em 1.0s). B e mais grave: deve preemptar A assim que "
            "chegar, independente dos restantes."
        ),
        esperado="preempcoes=1",
        obtido=f"preempcoes={preempcoes}",
        passou=passou,
    )


def teste_5_sjf_ordena_por_duracao_e_reduz_espera() -> ResultadoTeste:
    """1 medico, 5 pacientes chegando TODOS em 0s, duracoes 3,1,2,5,4.

    Como ninguem chega depois do inicio, nao ha preempcao possivel aqui: o
    teste prova a outra metade do SJF, a escolha do PROXIMO paciente (em
    proximo_paciente(), escalonador.py) pelo menor 'restante' sempre que o
    medico fica livre. O atendimento deve seguir a ordem CRESCENTE de
    duracao (P2=1s, P3=2s, P1=3s, P5=4s, P4=5s) e a espera media resultante
    deve ser menor que a de atender na ordem de chegada/id (FCFS) -- aqui
    obtida rodando a MESMA carga com a politica de Prioridade e todos os
    pacientes na mesma gravidade: como prioridade e chegada ficam empatadas,
    chave_prioridade() desempata por id, reproduzindo FCFS pela ordem em que
    main.py listaria os pacientes.
    """
    duracoes = [3.0, 1.0, 2.0, 5.0, 4.0]

    pacientes_sjf = [
        Paciente(id=i + 1, gravidade=Gravidade.VERDE, duracao=d, chegada=0.0, restante=d)
        for i, d in enumerate(duracoes)
    ]
    preempcoes_sjf = _rodar_cenario(pacientes_sjf, PoliticaEscalonamento.SJF)
    ordem_obtida = [p.id for p in sorted(pacientes_sjf, key=lambda p: p.inicio)]
    ordem_esperada = [2, 3, 1, 5, 4]  # ids ordenados por duracao crescente
    espera_sjf = sum(p.inicio - p.chegada for p in pacientes_sjf) / len(pacientes_sjf)

    pacientes_fcfs = [
        Paciente(id=i + 1, gravidade=Gravidade.VERDE, duracao=d, chegada=0.0, restante=d)
        for i, d in enumerate(duracoes)
    ]
    _rodar_cenario(pacientes_fcfs, PoliticaEscalonamento.PRIORIDADE)
    espera_fcfs = sum(p.inicio - p.chegada for p in pacientes_fcfs) / len(pacientes_fcfs)

    passou = (
        preempcoes_sjf == 0
        and ordem_obtida == ordem_esperada
        and espera_sjf < espera_fcfs
    )
    return ResultadoTeste(
        nome="Teste 5 - SJF ordena por duracao e reduz a espera media",
        descricao=(
            "5 pacientes chegam juntos em 0s (duracoes 3,1,2,5,4; ids 1-5). "
            "SJF deve atender na ordem crescente de duracao (ids 2,3,1,5,4) "
            "sem nenhuma preempcao (nada chega depois do inicio), com "
            "espera media menor que atender na ordem de chegada (FCFS)."
        ),
        esperado="ordem=[2,3,1,5,4]; preempcoes=0; espera(SJF) < espera(FCFS)",
        obtido=(
            f"ordem={ordem_obtida}; preempcoes={preempcoes_sjf}; "
            f"espera(SJF)={espera_sjf:.3f}s; espera(FCFS)={espera_fcfs:.3f}s"
        ),
        passou=passou,
    )


TESTES = (
    teste_1_sjf_preempta,
    teste_2_sjf_sem_preempcao,
    teste_3_sjf_compara_restante_nao_duracao,
    teste_4_prioridade_preempta,
    teste_5_sjf_ordena_por_duracao_e_reduz_espera,
)


def executar_testes() -> list[ResultadoTeste]:
    return [teste() for teste in TESTES]


def imprimir_resultados(resultados: list[ResultadoTeste]) -> bool:
    tudo_passou = True
    for resultado in resultados:
        status = "PASSOU" if resultado.passou else "FALHOU"
        tudo_passou = tudo_passou and resultado.passou
        print(f"\n[{status}] {resultado.nome}")
        print(f"  Cenario : {resultado.descricao}")
        print(f"  Esperado: {resultado.esperado}")
        print(f"  Obtido  : {resultado.obtido}")
    print(
        "\nResultado geral: "
        + ("TODOS OS TESTES PASSARAM" if tudo_passou else "HA TESTES FALHANDO")
    )
    return tudo_passou


def main() -> int:
    resultados = executar_testes()
    tudo_passou = imprimir_resultados(resultados)
    return 0 if tudo_passou else 1


if __name__ == "__main__":
    raise SystemExit(main())
