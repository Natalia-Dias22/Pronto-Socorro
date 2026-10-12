"""Calculo e exibicao das metricas dos escalonamentos.

Definicoes do Cap. 5 (Criterios de Scheduling), calculadas sobre os pacientes
concluidos:
- espera (E): tempo total na fila de prontos, somando cada volta apos preempcao;
- retorno (turnaround): fim - chegada;
- resposta: inicio do primeiro atendimento - chegada.

Terminal e interface usam estas mesmas funcoes, para que o mesmo valor apareca
igual em qualquer lugar.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from modelos import Gravidade, RegistroAtendimento


@dataclass(frozen=True)
class Medias:
    quantidade: int
    espera: float
    retorno: float
    resposta: float
    espera_max: float = 0.0


@dataclass(frozen=True)
class Metricas:
    geral: Medias
    por_gravidade: dict[Gravidade, Medias]


def _medias(registros: list[RegistroAtendimento]) -> Medias:
    if not registros:
        return Medias(0, 0.0, 0.0, 0.0)
    quantidade = len(registros)
    return Medias(
        quantidade=quantidade,
        espera=sum(registro.espera for registro in registros) / quantidade,
        retorno=sum(registro.retorno for registro in registros) / quantidade,
        resposta=sum(registro.resposta for registro in registros) / quantidade,
        # A media esconde o starvation; o pior caso nao.
        espera_max=max(registro.espera for registro in registros),
    )


def calcular_metricas(registros: Iterable[RegistroAtendimento]) -> Metricas:
    # Ordem fixa: somas de float dependem da ordem, e o painel (ordem de conclusao)
    # precisa chegar exatamente ao mesmo valor do resultado final (ordem de id).
    lista = sorted(registros, key=lambda registro: registro.paciente_id)
    return Metricas(
        geral=_medias(lista),
        por_gravidade={
            gravidade: _medias([r for r in lista if r.gravidade == gravidade])
            for gravidade in Gravidade
        },
    )


def formatar_segundos(valor: float) -> str:
    return f"{valor:.2f}s"


def formatar_tempos(medias: Medias, vazio: str = "-") -> tuple[str, str, str]:
    """Espera, retorno e resposta formatados; grupo sem concluidos nao vira 0.00s."""
    if medias.quantidade == 0:
        return vazio, vazio, vazio
    return (
        formatar_segundos(medias.espera),
        formatar_segundos(medias.retorno),
        formatar_segundos(medias.resposta),
    )


def formatar_medias(medias: Medias) -> str:
    if medias.quantidade == 0:
        return "—"
    return (
        f"E {formatar_segundos(medias.espera)} "
        f"(máx {formatar_segundos(medias.espera_max)}) · "
        f"R {formatar_segundos(medias.retorno)} · "
        f"Resp {formatar_segundos(medias.resposta)}"
    )


GRUPOS = (
    ("geral", "Geral", None),
    ("vermelho", "Vermelho", Gravidade.VERMELHO),
    ("amarelo", "Amarelo", Gravidade.AMARELO),
    ("verde", "Verde", Gravidade.VERDE),
)


@dataclass(frozen=True)
class ColunaComparacao:
    chave: str
    grupo: str  # cabecalho do bloco de colunas
    titulo: str
    destacar: bool  # so espera e retorno: preempcoes e colisoes nunca sao "melhores"


def colunas_comparacao() -> list[ColunaComparacao]:
    colunas = []
    for chave, nome, _ in GRUPOS:
        colunas.append(ColunaComparacao(f"espera_{chave}", "Espera média", nome, True))
    for chave, nome, _ in GRUPOS:
        colunas.append(ColunaComparacao(f"max_{chave}", "Espera máxima", nome, True))
    colunas.append(ColunaComparacao("retorno", "Retorno", "médio", True))
    colunas.append(ColunaComparacao("preempcoes", "Preempções", "total", False))
    colunas.append(ColunaComparacao("colisoes", "Colisões", "raio-X", False))
    return colunas


def valores_comparacao(
    metricas: Metricas, preempcoes: int, colisoes: int
) -> dict[str, float | None]:
    """Uma linha da tabela "Comparar politicas"; None = grupo sem concluidos."""
    valores: dict[str, float | None] = {}
    for chave, _, gravidade in GRUPOS:
        medias = metricas.geral if gravidade is None else metricas.por_gravidade[gravidade]
        valores[f"espera_{chave}"] = medias.espera if medias.quantidade else None
        valores[f"max_{chave}"] = medias.espera_max if medias.quantidade else None
    valores["retorno"] = metricas.geral.retorno if metricas.geral.quantidade else None
    valores["preempcoes"] = preempcoes
    valores["colisoes"] = colisoes
    return valores


def formatar_valor_comparacao(coluna: ColunaComparacao, valor: float | None) -> str:
    if valor is None:
        return "—"
    if coluna.chave in {"preempcoes", "colisoes"}:
        return str(int(valor))
    return formatar_segundos(valor)


def melhores_da_coluna(coluna: ColunaComparacao, valores: list[float | None]) -> set[int]:
    """Indices (linhas) a destacar: o menor valor, so em colunas de espera/retorno.

    A decisao usa o valor formatado: se a tela mostra empate, ninguem e destacado.
    """
    if not coluna.destacar or len(valores) < 2 or any(v is None for v in valores):
        return set()
    textos = [formatar_segundos(v) for v in valores]
    if len(set(textos)) == 1:
        return set()
    menor = min(textos, key=float_do_texto)
    return {i for i, texto in enumerate(textos) if texto == menor}


def float_do_texto(texto: str) -> float:
    return float(texto.removesuffix("s"))


def imprimir_comparacao(linhas: list[tuple[str, Metricas, int, int]]) -> None:
    """Tabela PS x RR no terminal; '*' marca o menor valor (so espera e retorno)."""
    colunas = colunas_comparacao()
    valores = [valores_comparacao(m, p, c) for _, m, p, c in linhas]
    largura_nome = max(len(nome) for nome, *_ in linhas) + 2
    grupos, titulos, anterior = "", "", None
    for c in colunas:
        grupos += f"{(c.grupo if c.grupo != anterior else ''):>12}"
        titulos += f"{c.titulo:>12}"
        anterior = c.grupo
    print(f"{'':<{largura_nome}}{grupos}")
    print(f"{'Política':<{largura_nome}}{titulos}")
    escolhidos = {
        c.chave: melhores_da_coluna(c, [v[c.chave] for v in valores]) for c in colunas
    }
    for indice, (nome, *_resto) in enumerate(linhas):
        celulas = ""
        for c in colunas:
            texto = formatar_valor_comparacao(c, valores[indice][c.chave])
            if indice in escolhidos[c.chave]:
                texto += "*"
            celulas += f"{texto:>12}"
        print(f"{nome:<{largura_nome}}{celulas}")
    print(
        "Colunas: espera média/máxima (Geral, Vermelho, Amarelo, Verde), retorno "
        "médio, preempções, colisões. * = menor valor (só espera e retorno)."
    )


def imprimir_metricas(metricas: Metricas, titulo: str) -> None:
    print(f"\n{titulo}")
    print("E = espera na fila de prontos | R = retorno (fim - chegada) | Resp = resposta (inicio - chegada)")
    print(f"{'Grupo':<10} {'Concl.':>6} {'Espera':>9} {'Esp.max':>9} {'Retorno':>9} {'Resposta':>9}")
    linhas = [("Geral", metricas.geral)] + [
        (gravidade.name.capitalize(), metricas.por_gravidade[gravidade])
        for gravidade in Gravidade
    ]
    for nome, medias in linhas:
        espera, retorno, resposta = formatar_tempos(medias)
        maxima = formatar_segundos(medias.espera_max) if medias.quantidade else "-"
        print(
            f"{nome:<10} {medias.quantidade:>6} {espera:>9} {maxima:>9} "
            f"{retorno:>9} {resposta:>9}"
        )
