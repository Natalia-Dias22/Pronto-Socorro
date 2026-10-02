"""Interface grafica Tkinter do Pronto-Socorro Concorrente."""

import queue
import math
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from controle import ControleSimulacao, Evento
from main import executar_simulacao
from modelos import Gravidade


CORES = {
    "fundo": "#101820",
    "painel": "#172630",
    "painel_claro": "#203540",
    "texto": "#eef5f4",
    "muted": "#a9bdc2",
    "accent": "#f2b84b",
    "verde": "#38b985",
    "amarelo": "#efb64c",
    "vermelho": "#e75d67",
    "agua": "#57c6c2",
}

COR_GRAVIDADE = {
    Gravidade.VERMELHO.name: CORES["vermelho"],
    Gravidade.AMARELO.name: CORES["amarelo"],
    Gravidade.VERDE.name: CORES["verde"],
}


class ProntoSocorroGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Pronto-Socorro Concorrente")
        self.root.geometry("1400x900")
        self.root.minsize(1180, 740)
        self.root.configure(bg=CORES["fundo"])

        self.eventos: queue.Queue[tuple[bool | None, Evento]] = queue.Queue()
        self.controle: ControleSimulacao | None = None
        self.controles_comparacao: dict[bool, ControleSimulacao] = {}
        self.thread_simulacao: threading.Thread | None = None
        self.executando = False
        self.comparando = False
        self.reiniciar_pendente = False
        self.fechando = False
        self.modo_atual = False
        self.num_medicos = 2
        self.num_pacientes = 16
        self.seed_atual = 42

        self.pacientes: dict[int, dict[str, object]] = {}
        self.medicos: dict[int, dict[str, object]] = {}
        self.leitos_ocupados: set[int] = set()
        self.leitos_livres_real = 3
        self.notas_salvas = 0
        self.notas_total = 0
        self.notas_ids: list[int] = []
        self.colisoes = 0
        self.preempcoes = 0
        self.metricas_concluidas: list[dict[str, object]] = []
        self.ids_concluidos: set[int] = set()
        self.colisao_ate = 0.0
        self.piscar_colisao = False
        self.aviso_preempcao = ""
        self.aviso_ate = 0.0
        self.nota_perdida = ""
        self.nota_perdida_ate = 0.0
        self.resultado_final: dict[str, object] | None = None
        self.estado_comparacao: dict[bool, dict[str, object]] = {}
        self.visuais: dict[bool | None, dict[str, object]] = {}
        self.ultimo_frame = time.monotonic()

        self.modo_var = tk.IntVar(value=0)
        self.medicos_var = tk.StringVar(value="2")
        self.pacientes_var = tk.StringVar(value="16")
        self.seed_var = tk.StringVar(value="42")
        self.velocidade_var = tk.DoubleVar(value=1.0)
        self.pause_var = tk.StringVar(value="Pausar")
        self.metric_vars: dict[str, tk.StringVar] = {}
        self.metric_labels: dict[str, ttk.Label] = {}
        self.gravity_metric_vars: dict[str, tk.StringVar] = {}

        self._configurar_estilos()
        self._montar_janela()
        self.root.protocol("WM_DELETE_WINDOW", self.fechar)
        self.root.after(30, self._consumir_eventos)
        self.root.after(180, self._animar)

    def _configurar_estilos(self) -> None:
        estilo = ttk.Style(self.root)
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass
        estilo.configure(
            "TFrame", background=CORES["fundo"]
        )
        estilo.configure(
            "Panel.TFrame", background=CORES["painel"]
        )
        estilo.configure(
            "TLabel",
            background=CORES["painel"],
            foreground=CORES["texto"],
            font=("Segoe UI", 10),
        )
        estilo.configure(
            "Title.TLabel",
            background=CORES["fundo"],
            foreground=CORES["texto"],
            font=("Segoe UI Semibold", 20),
        )
        estilo.configure(
            "Section.TLabel",
            background=CORES["painel"],
            foreground=CORES["accent"],
            font=("Segoe UI Semibold", 12),
        )
        estilo.configure(
            "Muted.TLabel",
            background=CORES["painel"],
            foreground=CORES["muted"],
        )
        estilo.configure(
            "TButton",
            background=CORES["painel_claro"],
            foreground=CORES["texto"],
            padding=(10, 8),
            font=("Segoe UI Semibold", 10),
        )
        estilo.map(
            "TButton",
            background=[("active", "#2d4955"), ("disabled", "#25343a")],
            foreground=[("disabled", "#71848a")],
        )
        estilo.configure(
            "Accent.TButton",
            background=CORES["accent"],
            foreground=CORES["fundo"],
        )
        estilo.map("Accent.TButton", background=[("active", "#ffd16b")])
        estilo.configure(
            "TRadiobutton",
            background=CORES["painel"],
            foreground=CORES["texto"],
            font=("Segoe UI", 10),
        )
        estilo.map("TRadiobutton", background=[("active", CORES["painel"])])
        estilo.configure(
            "TEntry",
            fieldbackground=CORES["painel_claro"],
            foreground=CORES["texto"],
            insertcolor=CORES["texto"],
        )
        estilo.configure(
            "TSpinbox",
            fieldbackground=CORES["painel_claro"],
            foreground=CORES["texto"],
            arrowcolor=CORES["texto"],
        )

    def _montar_janela(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        topo = ttk.Frame(self.root, padding=(18, 14, 18, 8))
        topo.grid(row=0, column=0, sticky="ew")
        ttk.Label(topo, text="PRONTO-SOCORRO", style="Title.TLabel").pack(side="left")
        ttk.Label(
            topo,
            text="CONCORRENTE  /  PRIORIDADE PREEMPTIVA",
            foreground=CORES["agua"],
            background=CORES["fundo"],
            font=("Segoe UI Semibold", 10),
        ).pack(side="left", padx=(16, 0), pady=(7, 0))

        corpo = ttk.Frame(self.root, padding=(14, 6, 14, 14))
        corpo.grid(row=1, column=0, sticky="nsew")
        corpo.columnconfigure(0, weight=0, minsize=250)
        corpo.columnconfigure(1, weight=3, minsize=570)
        corpo.columnconfigure(2, weight=2, minsize=330)
        corpo.rowconfigure(0, weight=1)

        self._montar_controles(corpo)
        self._montar_cenario(corpo)
        self._montar_metricas(corpo)

    def _montar_controles(self, pai: ttk.Frame) -> None:
        painel = ttk.Frame(pai, style="Panel.TFrame", padding=16)
        painel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        painel.columnconfigure(0, weight=1)
        ttk.Label(painel, text="CONTROLE", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 14)
        )

        ttk.Label(painel, text="Modo de sincronização").grid(
            row=1, column=0, sticky="w"
        )
        ttk.Radiobutton(
            painel,
            text="SEM sincronização",
            variable=self.modo_var,
            value=0,
        ).grid(row=2, column=0, sticky="w", pady=(7, 1))
        ttk.Radiobutton(
            painel,
            text="COM sincronização",
            variable=self.modo_var,
            value=1,
        ).grid(row=3, column=0, sticky="w", pady=(1, 12))

        ttk.Label(painel, text="Médicos (1–12)").grid(row=4, column=0, sticky="w")
        self.medicos_spin = ttk.Spinbox(
            painel, from_=1, to=12, textvariable=self.medicos_var, width=12
        )
        self.medicos_spin.grid(row=5, column=0, sticky="ew", pady=(4, 10))

        ttk.Label(painel, text="Pacientes (1–60)").grid(row=6, column=0, sticky="w")
        self.pacientes_spin = ttk.Spinbox(
            painel, from_=1, to=60, textvariable=self.pacientes_var, width=12
        )
        self.pacientes_spin.grid(row=7, column=0, sticky="ew", pady=(4, 10))

        ttk.Label(painel, text="Seed reproduzível").grid(row=8, column=0, sticky="w")
        self.seed_entry = ttk.Entry(painel, textvariable=self.seed_var)
        self.seed_entry.grid(row=9, column=0, sticky="ew", pady=(4, 13))

        ttk.Label(painel, text="Velocidade da simulação").grid(
            row=10, column=0, sticky="w"
        )
        self.velocidade_label = ttk.Label(
            painel, text="1.00×", foreground=CORES["agua"]
        )
        self.velocidade_label.grid(row=10, column=0, sticky="e")
        self.velocidade_scale = tk.Scale(
            painel,
            from_=0.25,
            to=4.0,
            resolution=0.25,
            orient="horizontal",
            variable=self.velocidade_var,
            command=self._alterar_velocidade,
            showvalue=False,
            length=210,
            bg=CORES["painel"],
            fg=CORES["texto"],
            troughcolor=CORES["painel_claro"],
            activebackground=CORES["accent"],
            highlightthickness=0,
            bd=0,
        )
        self.velocidade_scale.grid(row=11, column=0, sticky="ew", pady=(1, 3))
        ttk.Label(
            painel,
            text="0.25×                                      4×",
            style="Muted.TLabel",
            font=("Segoe UI", 8),
        ).grid(row=12, column=0, sticky="ew", pady=(0, 16))

        self.iniciar_button = ttk.Button(
            painel,
            text="▶  Iniciar atendimento",
            style="Accent.TButton",
            command=self.iniciar,
        )
        self.iniciar_button.grid(row=13, column=0, sticky="ew", pady=(0, 7))
        self.comparar_button = ttk.Button(
            painel,
            text="Comparar SEM × COM",
            command=self.iniciar_comparacao,
        )
        self.comparar_button.grid(row=14, column=0, sticky="ew", pady=(0, 7))
        self.pausar_button = ttk.Button(
            painel,
            textvariable=self.pause_var,
            command=self.alternar_pausa,
            state="disabled",
        )
        self.pausar_button.grid(row=15, column=0, sticky="ew", pady=3)
        ttk.Button(
            painel,
            text="↻  Reiniciar cenário",
            command=self.reiniciar,
        ).grid(row=16, column=0, sticky="ew", pady=(3, 12))

        self.estado_var = tk.StringVar(value="Pronto para iniciar")
        ttk.Label(
            painel,
            textvariable=self.estado_var,
            style="Muted.TLabel",
            wraplength=210,
            justify="left",
        ).grid(row=17, column=0, sticky="sw", pady=(8, 0))

    def _montar_cenario(self, pai: ttk.Frame) -> None:
        painel = ttk.Frame(pai, style="Panel.TFrame", padding=10)
        painel.grid(row=0, column=1, sticky="nsew", padx=5)
        painel.rowconfigure(1, weight=1)
        painel.columnconfigure(0, weight=1)
        ttk.Label(painel, text="CENÁRIO AO VIVO", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", padx=6, pady=(2, 8)
        )
        area = ttk.Frame(painel, style="Panel.TFrame")
        area.grid(row=1, column=0, sticky="nsew")
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            area,
            background="#0c151b",
            highlightthickness=0,
            bd=0,
        )
        barra = ttk.Scrollbar(area, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=barra.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.canvas.bind("<Configure>", lambda _event: self._desenhar_cenario())

    def _montar_metricas(self, pai: ttk.Frame) -> None:
        painel = ttk.Frame(pai, style="Panel.TFrame", padding=15)
        painel.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
        painel.columnconfigure(0, weight=1)
        painel.rowconfigure(16, weight=1)
        ttk.Label(painel, text="PAINEL DA EMERGÊNCIA", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 12)
        )

        nomes = [
            ("colisoes", "Colisões no raio-X"),
            ("leitos", "Leitos livres · esperado / real"),
            ("notas", "Notas salvas / total"),
            ("preempcoes", "Preempções"),
            ("concluidos", "Pacientes concluídos"),
        ]
        for indice, (chave, nome) in enumerate(nomes, start=1):
            linha = ttk.Frame(painel, style="Panel.TFrame")
            linha.grid(row=indice, column=0, sticky="ew", pady=2)
            linha.columnconfigure(0, weight=1)
            ttk.Label(linha, text=nome, style="Muted.TLabel").grid(
                row=0, column=0, sticky="w"
            )
            variavel = tk.StringVar(value="0")
            self.metric_vars[chave] = variavel
            valor_label = ttk.Label(
                linha,
                textvariable=variavel,
                font=("Segoe UI Semibold", 11),
            )
            valor_label.grid(row=0, column=1, sticky="e")
            self.metric_labels[chave] = valor_label

        self.progresso_var = tk.DoubleVar(value=0.0)
        self.progresso_texto = tk.StringVar(value="0 / 16")
        progresso_linha = ttk.Frame(painel, style="Panel.TFrame")
        progresso_linha.grid(row=6, column=0, sticky="ew", pady=(9, 2))
        progresso_linha.columnconfigure(0, weight=1)
        ttk.Label(progresso_linha, text="ATENDIMENTOS", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(progresso_linha, textvariable=self.progresso_texto, style="Muted.TLabel").grid(row=0, column=1, sticky="e")
        ttk.Progressbar(
            painel,
            maximum=100,
            variable=self.progresso_var,
            mode="determinate",
        ).grid(row=7, column=0, sticky="ew", pady=(0, 6))
        ttk.Separator(painel).grid(row=8, column=0, sticky="ew", pady=8)
        ttk.Label(painel, text="MÉDIAS AO VIVO", style="Section.TLabel").grid(
            row=9, column=0, sticky="w", pady=(0, 5)
        )
        for indice, (chave, nome) in enumerate(
            (("geral", "Geral"), ("vermelho", "Vermelho"),
             ("amarelo", "Amarelo"), ("verde", "Verde")),
            start=10,
        ):
            ttk.Label(painel, text=nome, style="Muted.TLabel").grid(
                row=indice, column=0, sticky="w", pady=2
            )
            variavel = tk.StringVar(value="E —  R —  Resp —")
            self.gravity_metric_vars[chave] = variavel
            ttk.Label(
                painel,
                textvariable=variavel,
                font=("Segoe UI", 9),
                wraplength=275,
                justify="right",
            ).grid(row=indice, column=0, sticky="e", pady=2)

        ttk.Separator(painel).grid(row=14, column=0, sticky="ew", pady=8)
        ttk.Label(painel, text="EVENTOS", style="Section.TLabel").grid(
            row=15, column=0, sticky="w", pady=(0, 5)
        )
        log_frame = ttk.Frame(painel, style="Panel.TFrame")
        log_frame.grid(row=16, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_frame,
            height=12,
            wrap="word",
            bg="#0c151b",
            fg=CORES["muted"],
            insertbackground=CORES["texto"],
            relief="flat",
            font=("Consolas", 9),
            padx=8,
            pady=6,
            state="disabled",
        )
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.tag_configure("red", foreground=CORES["vermelho"])
        self.log_text.tag_configure("green", foreground=CORES["verde"])
        self.log_text.tag_configure("amber", foreground=CORES["accent"])

    def _ler_configuracao(self) -> tuple[bool, int, int, int] | None:
        try:
            medicos = int(self.medicos_var.get())
            pacientes = int(self.pacientes_var.get())
            seed = int(self.seed_var.get())
        except ValueError:
            messagebox.showerror("Configuração inválida", "Use números inteiros nos campos.")
            return None
        if not 1 <= medicos <= 12 or not 1 <= pacientes <= 60:
            messagebox.showerror(
                "Configuração inválida",
                "Escolha de 1 a 12 médicos e de 1 a 60 pacientes.",
            )
            return None
        return bool(self.modo_var.get()), medicos, pacientes, seed

    def iniciar(self) -> None:
        if self.executando or self.fechando:
            return
        configuracao = self._ler_configuracao()
        if configuracao is None:
            return
        modo, medicos, pacientes, seed = configuracao
        self._preparar_simulacao(modo, medicos, pacientes, seed)

    def iniciar_comparacao(self) -> None:
        if self.executando or self.fechando:
            return
        configuracao = self._ler_configuracao()
        if configuracao is None:
            return
        _, medicos, pacientes, seed = configuracao
        self.comparando = True
        self.executando = True
        self.reiniciar_pendente = False
        self.num_medicos = medicos
        self.num_pacientes = pacientes
        self.seed_atual = seed
        self.controles_comparacao = {
            False: ControleSimulacao(self.velocidade_var.get()),
            True: ControleSimulacao(self.velocidade_var.get()),
        }
        self.estado_comparacao = {
            modo: self._novo_estado_comparacao(modo, medicos)
            for modo in (False, True)
        }
        self.visuais = {
            modo: estado["visual"]
            for modo, estado in self.estado_comparacao.items()
        }
        self.resultado_final = None
        self._limpar_log()
        self.iniciar_button.configure(state="disabled")
        self.comparar_button.configure(state="disabled")
        self.pausar_button.configure(state="normal")
        self.pause_var.set("Pausar")
        self.estado_var.set(
            f"Comparando o mesmo seed {seed} · {medicos} médicos · {pacientes} pacientes"
        )
        for modo, controle in self.controles_comparacao.items():
            thread = threading.Thread(
                target=self._executar_comparacao_em_background,
                args=(modo, medicos, pacientes, seed, controle),
                name=f"Comparacao-{'COM' if modo else 'SEM'}",
                daemon=True,
            )
            thread.start()
        self._desenhar_cenario()

    def _novo_estado_comparacao(
        self, modo: bool, num_medicos: int
    ) -> dict[str, object]:
        return {
            "modo": modo,
            "pacientes": {},
            "medicos": {
                medico_id: {"paciente": None, "estado": "livre"}
                for medico_id in range(1, num_medicos + 1)
            },
            "leitos": set(),
            "leitos_livres": 3,
            "notas_ids": [],
            "notas_salvas": 0,
            "notas_total": 0,
            "colisoes": 0,
            "preempcoes": 0,
            "concluidos": set(),
            "registros": [],
            "resultado": None,
            "colisao_ate": 0.0,
            "preempcao_texto": "",
            "preempcao_ate": 0.0,
            "nota_perdida": "",
            "nota_perdida_ate": 0.0,
            "visual": self._novo_visual(),
        }

    @staticmethod
    def _novo_visual() -> dict[str, object]:
        return {
            "layout": {},
            "medico_posicoes": {},
            "medico_filas": {},
            "medico_movimentos": {},
            "paciente_posicoes": {},
            "paciente_movimentos": {},
            "notas_tempo": {},
        }

    def _mover_medico(
        self,
        faixa: bool | None,
        medico_id: int,
        destino: str,
        paciente_id: int | None,
    ) -> None:
        visual = self.visuais.setdefault(faixa, self._novo_visual())
        filas = visual["medico_filas"]
        filas.setdefault(medico_id, []).append((destino, paciente_id))

    def _mover_paciente(
        self,
        faixa: bool | None,
        paciente_id: int,
        destino: str,
        medico_id: int | None,
    ) -> None:
        visual = self.visuais.setdefault(faixa, self._novo_visual())
        posicoes = visual["paciente_posicoes"]
        layout = visual["layout"]
        atual = posicoes.get(paciente_id)
        if atual is None:
            atual = layout.get("espera", {}).get(paciente_id)
        if atual is None:
            atual = (layout.get("centro_x", 300), layout.get("espera_y", 100))
        visual["paciente_movimentos"][paciente_id] = {
            "inicio": atual,
            "destino": destino,
            "medico_id": medico_id,
            "progresso": 0.0,
        }

    def _executar_comparacao_em_background(
        self,
        modo: bool,
        medicos: int,
        pacientes: int,
        seed: int,
        controle: ControleSimulacao,
    ) -> None:
        try:
            executar_simulacao(
                modo,
                seed,
                medicos,
                pacientes,
                False,
                lambda evento: self.eventos.put((modo, evento)),
                controle,
                False,
            )
        except Exception as erro:
            self.eventos.put(
                (
                    modo,
                    ("erro", None, None, {"mensagem": str(erro)}, time.monotonic()),
                )
            )

    def _tratar_evento_comparacao(self, modo: bool, evento: Evento) -> None:
        estado = self.estado_comparacao[modo]
        visual = estado["visual"]
        tipo, medico_id, paciente_id, dados, _timestamp = evento
        pacientes = estado["pacientes"]
        medicos = estado["medicos"]
        if tipo == "paciente_chegou" and paciente_id is not None:
            pacientes[paciente_id] = {
                "gravidade": str(dados.get("gravidade", "VERDE")),
                "prioridade": int(dados.get("prioridade", 2)),
                "chegada": float(dados.get("chegada", 0.0)),
                "inicio": None,
                "fim": None,
                "estado": "espera",
            }
        elif tipo == "medico_iniciou" and medico_id is not None and paciente_id is not None:
            pacientes.setdefault(paciente_id, {}).update(
                {
                    "gravidade": str(dados.get("gravidade", "VERDE")),
                    "prioridade": int(dados.get("prioridade", 2)),
                    "chegada": float(dados.get("chegada", 0.0)),
                    "inicio": float(dados.get("inicio", 0.0)),
                    "estado": "transito",
                }
            )
            medicos[medico_id] = {"paciente": paciente_id, "estado": "atendendo"}
            self._mover_paciente(modo, paciente_id, "medico", medico_id)
        elif tipo == "preempcao" and medico_id is not None and paciente_id is not None:
            interrompido = int(dados.get("paciente_interrompido", -1))
            if interrompido in pacientes:
                pacientes[interrompido]["estado"] = "espera"
                self._mover_paciente(modo, interrompido, "espera", None)
            pacientes[paciente_id]["estado"] = "transito"
            self._mover_paciente(modo, paciente_id, "medico", medico_id)
            medicos[medico_id] = {"paciente": paciente_id, "estado": "atendendo"}
            estado["preempcoes"] += 1
            estado["preempcao_texto"] = f"PREEMPÇÃO · P{paciente_id}"
            estado["preempcao_ate"] = time.monotonic() + 1.5
        elif tipo == "medico_concluiu" and medico_id is not None and paciente_id is not None:
            paciente = pacientes[paciente_id]
            paciente.update(
                {
                    "gravidade": str(dados.get("gravidade", "VERDE")),
                    "chegada": float(dados.get("chegada", 0.0)),
                    "inicio": float(dados.get("inicio", 0.0) or 0.0),
                    "fim": float(dados.get("fim", 0.0)),
                    "estado": "concluido",
                }
            )
            if paciente_id not in estado["concluidos"]:
                estado["concluidos"].add(paciente_id)
                estado["registros"].append(paciente)
            medicos[medico_id] = {"paciente": None, "estado": "livre"}
            self._mover_medico(modo, medico_id, "equipe", paciente_id)
        elif tipo == "aguardando_semaforo" and medico_id is not None:
            medicos[medico_id] = {"paciente": paciente_id, "estado": "aguardando"}
            self._mover_medico(modo, medico_id, "porta", paciente_id)
        elif tipo == "raio_x_entrou" and medico_id is not None:
            medicos[medico_id] = {"paciente": paciente_id, "estado": "raio-x"}
            self._mover_medico(modo, medico_id, "raio-x", paciente_id)
        elif tipo == "raio_x_saiu" and medico_id is not None:
            medicos[medico_id] = {"paciente": paciente_id, "estado": "atendendo"}
            self._mover_medico(modo, medico_id, "equipe", paciente_id)
        elif tipo == "colisao":
            estado["colisoes"] += 1
            estado["colisao_ate"] = time.monotonic() + 1.4
        elif tipo == "leito_ocupou" and paciente_id is not None:
            estado["leitos"].add(paciente_id)
            estado["leitos_livres"] = int(dados.get("livres", estado["leitos_livres"]))
            if medico_id is not None:
                self._mover_medico(modo, medico_id, "leito", paciente_id)
        elif tipo == "leito_liberou" and paciente_id is not None:
            estado["leitos"].discard(paciente_id)
            estado["leitos_livres"] = int(dados.get("livres", estado["leitos_livres"]))
        elif tipo == "nota_gravada":
            estado["notas_salvas"] = int(dados.get("salvas", estado["notas_salvas"] + 1))
            estado["notas_total"] = int(dados.get("total", estado["notas_total"] + 1))
            if paciente_id is not None:
                estado["notas_ids"].append(paciente_id)
                visual["notas_tempo"][paciente_id] = time.monotonic()
                if medico_id is not None:
                    self._mover_medico(modo, medico_id, "prontuario", paciente_id)
        elif tipo == "nota_perdida":
            estado["nota_perdida"] = f"NOTA PERDIDA · P{paciente_id}"
            estado["nota_perdida_ate"] = time.monotonic() + 2.5
        elif tipo == "fim":
            estado["resultado"] = dados
            estado["colisoes"] = int(dados.get("colisoes", estado["colisoes"]))
            estado["leitos_livres"] = int(dados.get("leitos_livres", estado["leitos_livres"]))
            estado["notas_salvas"] = int(dados.get("notas_salvas", estado["notas_salvas"]))
            estado["notas_total"] = int(dados.get("notas_total", estado["notas_total"]))
            estado["preempcoes"] = int(dados.get("preempcoes", estado["preempcoes"]))
            for id_medico in medicos:
                self._mover_medico(modo, id_medico, "equipe", None)
            if all(item["resultado"] is not None for item in self.estado_comparacao.values()):
                self.executando = False
                self.pausar_button.configure(state="disabled")
                self.pause_var.set("Pausar")
                self.iniciar_button.configure(state="normal")
                self.comparar_button.configure(state="normal")
                self.estado_var.set("Comparação encerrada · mesmo cenário, dois modos")
                if self.reiniciar_pendente:
                    self.reiniciar_pendente = False
                    self.root.after(60, self._reiniciar_agora)
                else:
                    self.root.after(120, self._mostrar_placar_final)
        elif tipo == "erro":
            estado["resultado"] = {"erro": dados.get("mensagem", "Erro")}
            self.estado_var.set(f"Falha no modo {'COM' if modo else 'SEM'}")
            if all(item["resultado"] is not None for item in self.estado_comparacao.values()):
                self.executando = False
                self.pausar_button.configure(state="disabled")
                self.iniciar_button.configure(state="normal")
                self.comparar_button.configure(state="normal")
                self.root.after(100, self._mostrar_placar_final)
        self._atualizar_metricas()

    def _preparar_simulacao(
        self, modo: bool, medicos: int, pacientes: int, seed: int
    ) -> None:
        self.modo_atual = modo
        self.comparando = False
        self.num_medicos = medicos
        self.num_pacientes = pacientes
        self.seed_atual = seed
        self.pacientes.clear()
        self.medicos = {
            medico_id: {"paciente": None, "estado": "livre"}
            for medico_id in range(1, medicos + 1)
        }
        self.leitos_ocupados.clear()
        self.leitos_livres_real = 3
        self.notas_salvas = 0
        self.notas_total = 0
        self.notas_ids.clear()
        self.colisoes = 0
        self.preempcoes = 0
        self.metricas_concluidas.clear()
        self.ids_concluidos.clear()
        self.resultado_final = None
        self.comparando = False
        self.estado_comparacao.clear()
        self.visuais = {None: self._novo_visual()}
        self.aviso_preempcao = ""
        self.nota_perdida = ""
        self._limpar_log()
        self._atualizar_metricas()

        self.controle = ControleSimulacao(self.velocidade_var.get())
        self.controles_comparacao.clear()
        self.executando = True
        self.pause_var.set("Pausar")
        self.estado_var.set(
            f"Executando {'COM' if modo else 'SEM'} sincronização · "
            f"{medicos} médicos · {pacientes} pacientes"
        )
        self.iniciar_button.configure(state="disabled")
        self.comparar_button.configure(state="disabled")
        self.pausar_button.configure(state="normal")
        self.thread_simulacao = threading.Thread(
            target=self._executar_em_background,
            args=(modo, medicos, pacientes, seed, self.controle),
            name="Simulacao-UI",
            daemon=True,
        )
        self.thread_simulacao.start()
        self._desenhar_cenario()

    def _executar_em_background(
        self,
        modo: bool,
        medicos: int,
        pacientes: int,
        seed: int,
        controle: ControleSimulacao,
    ) -> None:
        try:
            executar_simulacao(
                modo,
                seed,
                medicos,
                pacientes,
                False,
                lambda evento: self.eventos.put((None, evento)),
                controle,
                False,
            )
        except Exception as erro:
            self.eventos.put(
                (
                    None,
                    ("erro", None, None, {"mensagem": str(erro)}, time.monotonic()),
                )
            )

    def alternar_pausa(self) -> None:
        if not self.executando:
            return
        pausada = not self._pausada()
        controles = (
            list(self.controles_comparacao.values())
            if self.comparando
            else ([self.controle] if self.controle is not None else [])
        )
        for controle in controles:
            controle.definir_pausa(pausada)
        self.pause_var.set("Continuar" if pausada else "Pausar")
        self.estado_var.set("Simulação pausada" if pausada else "Simulação em andamento")

    def _pausada(self) -> bool:
        controles = (
            list(self.controles_comparacao.values())
            if self.comparando
            else ([self.controle] if self.controle is not None else [])
        )
        return bool(controles) and all(controle.pausada for controle in controles)

    def _alterar_velocidade(self, valor: str) -> None:
        velocidade = float(valor)
        self.velocidade_label.configure(text=f"{velocidade:.2f}×")
        if self.controle is not None and self.executando:
            self.controle.definir_velocidade(velocidade)
        for controle in self.controles_comparacao.values():
            if self.executando:
                controle.definir_velocidade(velocidade)

    def reiniciar(self) -> None:
        if self.executando:
            self.reiniciar_pendente = True
            if self.controle is not None:
                self.controle.parar()
            for controle in self.controles_comparacao.values():
                controle.parar()
            self.estado_var.set("Encerrando cenário anterior…")
            return
        self.iniciar()

    def _consumir_eventos(self) -> None:
        if self.fechando:
            return
        houve_eventos = False
        while True:
            try:
                faixa, evento = self.eventos.get_nowait()
            except queue.Empty:
                break
            houve_eventos = True
            if faixa is None:
                self._tratar_evento(evento)
            else:
                self._tratar_evento_comparacao(faixa, evento)
        self._atualizar_metricas()
        if houve_eventos:
            self._desenhar_cenario()
        self.root.after(30, self._consumir_eventos)

    def _tratar_evento(self, evento: Evento) -> None:
        tipo, medico_id, paciente_id, dados, _timestamp = evento
        if tipo == "paciente_chegou" and paciente_id is not None:
            self.pacientes[paciente_id] = {
                "gravidade": str(dados.get("gravidade", "VERDE")),
                "prioridade": int(dados.get("prioridade", 2)),
                "chegada": float(dados.get("chegada", 0.0)),
                "inicio": None,
                "fim": None,
                "estado": "espera",
            }
            self._log_evento(f"Paciente {paciente_id} chegou à triagem.", "muted")
        elif tipo == "medico_iniciou" and medico_id is not None and paciente_id is not None:
            self.pacientes.setdefault(paciente_id, {}).update(
                {
                    "gravidade": str(dados.get("gravidade", "VERDE")),
                    "prioridade": int(dados.get("prioridade", 2)),
                    "chegada": float(dados.get("chegada", 0.0)),
                    "inicio": float(dados.get("inicio", 0.0)),
                    "estado": "atendimento",
                }
            )
            self.medicos[medico_id] = {"paciente": paciente_id, "estado": "atendendo"}
            self.pacientes[paciente_id]["estado"] = "transito"
            self._mover_paciente(None, paciente_id, "medico", medico_id)
            self._log_evento(f"Médico {medico_id} iniciou paciente {paciente_id}.", "amber")
        elif tipo == "preempcao" and medico_id is not None and paciente_id is not None:
            interrompido = int(dados.get("paciente_interrompido", -1))
            if interrompido in self.pacientes:
                self.pacientes[interrompido]["estado"] = "espera"
                self._mover_paciente(None, interrompido, "espera", None)
            if paciente_id in self.pacientes:
                self.pacientes[paciente_id]["estado"] = "transito"
                self._mover_paciente(None, paciente_id, "medico", medico_id)
            self.medicos[medico_id] = {"paciente": paciente_id, "estado": "atendendo"}
            self.preempcoes += 1
            self.aviso_preempcao = f"PREEMPÇÃO · P{paciente_id} assume de P{interrompido}"
            self.aviso_ate = time.monotonic() + 1.6
            self._log_evento(self.aviso_preempcao, "amber")
        elif tipo == "medico_concluiu" and medico_id is not None and paciente_id is not None:
            paciente = self.pacientes.setdefault(paciente_id, {})
            paciente.update(
                {
                    "gravidade": str(dados.get("gravidade", "VERDE")),
                    "chegada": float(dados.get("chegada", 0.0)),
                    "inicio": float(dados.get("inicio", 0.0) or 0.0),
                    "fim": float(dados.get("fim", 0.0)),
                    "estado": "concluido",
                }
            )
            self.medicos[medico_id] = {"paciente": None, "estado": "livre"}
            self._mover_medico(None, medico_id, "equipe", paciente_id)
            if paciente_id not in self.ids_concluidos:
                self.ids_concluidos.add(paciente_id)
                self.metricas_concluidas.append(paciente)
            self._log_evento(f"Paciente {paciente_id} concluído.", "green")
        elif tipo == "aguardando_semaforo" and medico_id is not None:
            self.medicos[medico_id] = {
                "paciente": paciente_id,
                "estado": "aguardando",
            }
            self._mover_medico(None, medico_id, "porta", paciente_id)
            self._log_evento(f"Médico {medico_id} aguardando {dados.get('recurso')}.", "amber")
        elif tipo == "raio_x_entrou" and medico_id is not None:
            self.medicos[medico_id] = {"paciente": paciente_id, "estado": "raio-x"}
            self._mover_medico(None, medico_id, "raio-x", paciente_id)
            self._log_evento(f"Raio-X ocupado pelo paciente {paciente_id}.", "muted")
        elif tipo == "raio_x_saiu" and medico_id is not None:
            self.medicos[medico_id] = {"paciente": paciente_id, "estado": "atendendo"}
            self._mover_medico(None, medico_id, "equipe", paciente_id)
        elif tipo == "colisao":
            self.colisoes += 1
            self.colisao_ate = time.monotonic() + 1.4
            self.piscar_colisao = True
            self._log_evento("COLISÃO no raio-X", "red")
        elif tipo == "leito_ocupou" and paciente_id is not None:
            self.leitos_ocupados.add(paciente_id)
            self.leitos_livres_real = int(dados.get("livres", self.leitos_livres_real))
            if medico_id is not None:
                self._mover_medico(None, medico_id, "leito", paciente_id)
            self._log_evento(f"Paciente {paciente_id} ocupou leito de UTI.", "muted")
        elif tipo == "leito_liberou" and paciente_id is not None:
            self.leitos_ocupados.discard(paciente_id)
            self.leitos_livres_real = int(dados.get("livres", self.leitos_livres_real))
            self._log_evento(f"Paciente {paciente_id} liberou leito de UTI.", "green")
        elif tipo == "nota_gravada":
            self.notas_salvas = int(dados.get("salvas", self.notas_salvas + 1))
            self.notas_total = int(dados.get("total", self.notas_total + 1))
            if paciente_id is not None:
                self.notas_ids.append(paciente_id)
                self.visuais[None]["notas_tempo"][paciente_id] = time.monotonic()
                if medico_id is not None:
                    self._mover_medico(None, medico_id, "prontuario", paciente_id)
            self._log_evento(f"Nota do paciente {paciente_id} gravada.", "green")
        elif tipo == "nota_perdida":
            self.nota_perdida = f"NOTA PERDIDA · PACIENTE {paciente_id}"
            self.nota_perdida_ate = time.monotonic() + 2.5
            self._log_evento(self.nota_perdida, "red")
        elif tipo == "fim":
            self.resultado_final = dados
            self.colisoes = int(dados.get("colisoes", self.colisoes))
            self.leitos_livres_real = int(
                dados.get("leitos_livres", self.leitos_livres_real)
            )
            self.notas_salvas = int(dados.get("notas_salvas", self.notas_salvas))
            self.notas_total = int(dados.get("notas_total", self.notas_total))
            self.preempcoes = int(dados.get("preempcoes", self.preempcoes))
            self.executando = False
            self.pausar_button.configure(state="disabled")
            self.pause_var.set("Pausar")
            if self.reiniciar_pendente:
                self.reiniciar_pendente = False
                self.estado_var.set("Preparando novo cenário…")
                self.root.after(60, self._reiniciar_agora)
            elif not self.fechando:
                self.estado_var.set("Simulação encerrada")
                self.iniciar_button.configure(state="normal")
                self.comparar_button.configure(state="normal")
                self.root.after(120, self._mostrar_placar_final)
        elif tipo == "erro":
            self.executando = False
            self.pausar_button.configure(state="disabled")
            self.iniciar_button.configure(state="normal")
            self.comparar_button.configure(state="normal")
            self.estado_var.set("Falha na simulação")
            messagebox.showerror("Erro na simulação", str(dados.get("mensagem", "Erro")))

    def _reiniciar_agora(self) -> None:
        if self.fechando:
            return
        if self.comparando:
            self.iniciar_comparacao()
        else:
            self.iniciar()

    def _atualizar_metricas(self) -> None:
        if self.comparando and self.estado_comparacao:
            sem = self.estado_comparacao[False]
            com = self.estado_comparacao[True]
            total_concluidos = len(sem["concluidos"]) + len(com["concluidos"])
            self.progresso_texto.set(
                f"SEM {len(sem['concluidos'])}/{self.num_pacientes} · "
                f"COM {len(com['concluidos'])}/{self.num_pacientes}"
            )
            self.progresso_var.set(
                100.0 * total_concluidos / max(1, 2 * self.num_pacientes)
            )
            self.metric_vars["colisoes"].set(f"{sem['colisoes']} / {com['colisoes']}")
            sem_esperado = max(0, 3 - len(sem["leitos"]))
            com_esperado = max(0, 3 - len(com["leitos"]))
            self.metric_vars["leitos"].set(
                f"S {sem_esperado}/{sem['leitos_livres']} · C {com_esperado}/{com['leitos_livres']}"
            )
            self.metric_vars["notas"].set(
                f"S {sem['notas_salvas']}/{sem['notas_total']} · C {com['notas_salvas']}/{com['notas_total']}"
            )
            self.metric_vars["preempcoes"].set(
                f"{sem['preempcoes']} / {com['preempcoes']}"
            )
            self.metric_vars["concluidos"].set(
                f"{len(sem['concluidos'])} / {len(com['concluidos'])}"
            )
            self.metric_labels["colisoes"].configure(
                foreground=CORES["vermelho"]
                if sem["colisoes"] or com["colisoes"]
                else CORES["texto"]
            )
            self.metric_labels["leitos"].configure(
                foreground=CORES["vermelho"]
                if sem_esperado != sem["leitos_livres"]
                or com_esperado != com["leitos_livres"]
                else CORES["texto"]
            )
            for chave in self.gravity_metric_vars:
                sem_media = self._metricas_por_grupo(sem["registros"], chave)
                com_media = self._metricas_por_grupo(com["registros"], chave)
                self.gravity_metric_vars[chave].set(
                    f"SEM {sem_media}\nCOM {com_media}"
                )
            return

        concluidos = len(self.ids_concluidos)
        self.progresso_texto.set(f"{concluidos} / {self.num_pacientes}")
        self.progresso_var.set(
            100.0 * concluidos / max(1, self.num_pacientes)
        )
        self.metric_vars["colisoes"].set(str(self.colisoes))
        self.metric_labels["colisoes"].configure(
            foreground=CORES["vermelho"] if self.colisoes else CORES["texto"]
        )
        livres_esperados = max(0, 3 - len(self.leitos_ocupados))
        self.metric_vars["leitos"].set(
            f"{livres_esperados} / {self.leitos_livres_real}"
        )
        self.metric_labels["leitos"].configure(
            foreground=CORES["vermelho"]
            if livres_esperados != self.leitos_livres_real
            else CORES["texto"]
        )
        self.metric_vars["notas"].set(f"{self.notas_salvas} / {self.notas_total}")
        self.metric_vars["preempcoes"].set(str(self.preempcoes))
        self.metric_vars["concluidos"].set(f"{concluidos} / {self.num_pacientes}")

        grupos: dict[str, list[tuple[float, float, float]]] = {"geral": []}
        grupos.update({gravidade.name.lower(): [] for gravidade in Gravidade})
        for paciente in self.metricas_concluidas:
            chegada = float(paciente.get("chegada", 0.0))
            inicio = float(paciente.get("inicio", chegada))
            fim = float(paciente.get("fim", inicio))
            espera = max(0.0, inicio - chegada)
            valores = (espera, max(0.0, fim - chegada), espera)
            grupos["geral"].append(valores)
            grupos[str(paciente.get("gravidade", "VERDE")).lower()].append(valores)

        for chave, valores in grupos.items():
            if not valores:
                self.gravity_metric_vars[chave].set("E —  R —  Resp —")
                continue
            quantidade = len(valores)
            espera = sum(item[0] for item in valores) / quantidade
            retorno = sum(item[1] for item in valores) / quantidade
            resposta = sum(item[2] for item in valores) / quantidade
            self.gravity_metric_vars[chave].set(
                f"E {espera:.2f}s  R {retorno:.2f}s  Resp {resposta:.2f}s"
            )

    @staticmethod
    def _metricas_por_grupo(
        registros: list[dict[str, object]], grupo: str
    ) -> str:
        valores = []
        for paciente in registros:
            if grupo != "geral" and str(paciente.get("gravidade", "")).lower() != grupo:
                continue
            chegada = float(paciente.get("chegada", 0.0))
            inicio = float(paciente.get("inicio", chegada) or chegada)
            fim = float(paciente.get("fim", inicio) or inicio)
            valores.append((max(0.0, inicio - chegada), max(0.0, fim - chegada)))
        if not valores:
            return "—"
        espera = sum(item[0] for item in valores) / len(valores)
        retorno = sum(item[1] for item in valores) / len(valores)
        return f"E {espera:.1f}s · R {retorno:.1f}s · Resp {espera:.1f}s"

    def _log_evento(self, texto: str, tag: str = "muted") -> None:
        if not hasattr(self, "log_text"):
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", texto + "\n", tag)
        linhas = int(self.log_text.index("end-1c").split(".")[0])
        if linhas > 120:
            self.log_text.delete("1.0", f"{linhas - 120}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _limpar_log(self) -> None:
        if not hasattr(self, "log_text"):
            return
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _animar(self) -> None:
        if self.fechando:
            return
        agora = time.monotonic()
        self._avancar_animacoes(agora)
        animando = self.executando or self._tem_animacoes()
        if animando:
            self._desenhar_cenario()
        self.root.after(16 if animando else 90, self._animar)

    def _estado_exibicao(self, faixa: bool | None) -> dict[str, object]:
        if faixa is not None:
            return self.estado_comparacao[faixa]
        return {
            "modo": self.modo_atual,
            "pacientes": self.pacientes,
            "medicos": self.medicos,
            "leitos": self.leitos_ocupados,
            "leitos_livres": self.leitos_livres_real,
            "notas_ids": self.notas_ids,
            "notas_salvas": self.notas_salvas,
            "notas_total": self.notas_total,
            "colisoes": self.colisoes,
            "preempcoes": self.preempcoes,
            "concluidos": self.ids_concluidos,
            "resultado": self.resultado_final,
            "colisao_ate": self.colisao_ate,
            "preempcao_texto": self.aviso_preempcao,
            "preempcao_ate": self.aviso_ate,
            "nota_perdida": self.nota_perdida,
            "nota_perdida_ate": self.nota_perdida_ate,
            "visual": self.visuais.setdefault(None, self._novo_visual()),
        }

    @staticmethod
    def _resolver_destino(
        layout: dict[str, object],
        destino: str,
        medico_id: int | None,
        paciente_id: int | None,
    ) -> tuple[float, float] | None:
        if destino == "espera":
            return layout.get("espera", {}).get(paciente_id)
        if destino == "medico":
            return layout.get("equipe", {}).get(medico_id)
        if destino == "equipe":
            return layout.get("equipe", {}).get(medico_id)
        if destino == "porta":
            return layout.get("porta", {}).get(medico_id)
        if destino == "raio-x":
            return layout.get("raio-x", {}).get(medico_id)
        if destino == "leito":
            return layout.get("leitos", {}).get(paciente_id)
        if destino == "prontuario":
            return layout.get("prontuario")
        return None

    def _avancar_animacoes(self, agora: float) -> None:
        delta = min(0.06, max(0.0, agora - self.ultimo_frame))
        self.ultimo_frame = agora
        velocidade = 0.0 if self._pausada() else self.velocidade_var.get()
        passo = delta * velocidade / 0.2
        for faixa, visual in self.visuais.items():
            layout = visual.get("layout", {})
            if not layout:
                continue
            estado = self._estado_exibicao(faixa)
            medico_filas = visual["medico_filas"]
            medico_movimentos = visual["medico_movimentos"]
            medico_posicoes = visual["medico_posicoes"]
            for medico_id in estado["medicos"]:
                movimento = medico_movimentos.get(medico_id)
                fila = medico_filas.setdefault(medico_id, [])
                if movimento is None and fila:
                    destino, paciente_id = fila.pop(0)
                    origem = medico_posicoes.get(medico_id)
                    if origem is None:
                        origem = layout.get("equipe", {}).get(medico_id)
                    movimento = {
                        "inicio": origem,
                        "destino": destino,
                        "paciente_id": paciente_id,
                        "progresso": 0.0,
                    }
                    medico_movimentos[medico_id] = movimento
                if movimento is None or velocidade == 0.0:
                    continue
                destino = self._resolver_destino(
                    layout,
                    movimento["destino"],
                    medico_id,
                    movimento["paciente_id"],
                )
                origem = movimento["inicio"]
                if destino is None or origem is None:
                    continue
                movimento["progresso"] = min(1.0, movimento["progresso"] + passo)
                proporcao = movimento["progresso"]
                suave = proporcao * proporcao * (3.0 - 2.0 * proporcao)
                medico_posicoes[medico_id] = (
                    origem[0] + (destino[0] - origem[0]) * suave,
                    origem[1] + (destino[1] - origem[1]) * suave,
                )
                if proporcao >= 1.0:
                    medico_posicoes[medico_id] = destino
                    del medico_movimentos[medico_id]

            paciente_movimentos = visual["paciente_movimentos"]
            paciente_posicoes = visual["paciente_posicoes"]
            for paciente_id, movimento in list(paciente_movimentos.items()):
                if velocidade == 0.0:
                    continue
                destino = self._resolver_destino(
                    layout,
                    movimento["destino"],
                    movimento["medico_id"],
                    paciente_id,
                )
                origem = movimento["inicio"]
                if destino is None or origem is None:
                    continue
                movimento["progresso"] = min(1.0, movimento["progresso"] + passo)
                proporcao = movimento["progresso"]
                suave = proporcao * proporcao * (3.0 - 2.0 * proporcao)
                paciente_posicoes[paciente_id] = (
                    origem[0] + (destino[0] - origem[0]) * suave,
                    origem[1] + (destino[1] - origem[1]) * suave,
                )
                if proporcao >= 1.0:
                    paciente_posicoes[paciente_id] = destino
                    del paciente_movimentos[paciente_id]
                    if (
                        movimento["destino"] == "medico"
                        and estado["pacientes"][paciente_id].get("estado") == "transito"
                    ):
                        estado["pacientes"][paciente_id]["estado"] = "atendimento"

    def _tem_animacoes(self) -> bool:
        for visual in self.visuais.values():
            if visual["paciente_movimentos"] or visual["medico_movimentos"]:
                return True
            if any(visual["medico_filas"].values()):
                return True
        return False

    def _desenhar_cenario_legado(self) -> None:
        if not hasattr(self, "canvas") or self.fechando:
            return
        canvas = self.canvas
        largura = max(500, canvas.winfo_width())
        canvas.delete("all")
        x0, x1 = 18, largura - 18
        canvas.create_text(
            x0,
            12,
            anchor="nw",
            text=f"{self.num_medicos} MÉDICOS   /   {self.num_pacientes} PACIENTES",
            fill=CORES["muted"],
            font=("Segoe UI Semibold", 9),
        )

        pacientes_espera = sorted(
            (
                (paciente_id, dados)
                for paciente_id, dados in self.pacientes.items()
                if dados.get("estado") == "espera"
            ),
            key=lambda item: (
                int(item[1].get("prioridade", 2)),
                float(item[1].get("chegada", 0.0)),
                item[0],
            ),
        )
        colunas = max(7, min(13, (largura - 45) // 48))
        linhas = max(1, (len(pacientes_espera) + colunas - 1) // colunas)
        espera_topo = 35
        espera_base = espera_topo + 29 + linhas * 43
        self._caixa(canvas, x0, espera_topo, x1, espera_base, "SALA DE ESPERA", CORES["painel_claro"])
        for indice, (paciente_id, dados) in enumerate(pacientes_espera):
            coluna, linha = indice % colunas, indice // colunas
            x = x0 + 30 + coluna * ((x1 - x0 - 55) / max(1, colunas - 1))
            y = espera_topo + 52 + linha * 43
            cor = COR_GRAVIDADE.get(str(dados.get("gravidade", "VERDE")), CORES["verde"])
            canvas.create_oval(x - 17, y - 17, x + 17, y + 17, fill=cor, outline="#f6f8f4", width=1)
            canvas.create_text(x, y, text=str(paciente_id), fill="#101820", font=("Segoe UI Semibold", 9))

        medicos_topo = espera_base + 18
        self._caixa(canvas, x0, medicos_topo, x1, medicos_topo + 24, "EQUIPE MÉDICA", CORES["painel_claro"])
        medicos_topo += 34
        colunas_medicos = max(1, min(4, int((x1 - x0 - 24) // 142)))
        cartao_largura = (x1 - x0 - 12 * (colunas_medicos - 1)) / colunas_medicos
        for indice, medico_id in enumerate(sorted(self.medicos)):
            coluna, linha = indice % colunas_medicos, indice // colunas_medicos
            left = x0 + coluna * (cartao_largura + 12)
            top = medicos_topo + linha * 66
            right = left + cartao_largura
            bottom = top + 56
            info = self.medicos[medico_id]
            estado = str(info.get("estado", "livre"))
            fill = "#314652" if estado == "livre" else "#25454b"
            if estado == "aguardando":
                fill = "#51452a"
            canvas.create_rectangle(left, top, right, bottom, fill=fill, outline="#405862", width=1)
            canvas.create_text(left + 9, top + 9, anchor="nw", text=f"MÉDICO {medico_id}", fill=CORES["agua"], font=("Segoe UI Semibold", 9))
            paciente = info.get("paciente")
            status = "LIVRE" if paciente is None else f"PACIENTE {paciente}"
            canvas.create_text(left + 9, top + 31, anchor="nw", text=status, fill=CORES["texto"], font=("Segoe UI", 9))
            if estado == "aguardando":
                canvas.create_text(right - 8, top + 9, anchor="ne", text="aguardando", fill=CORES["accent"], font=("Segoe UI", 8))
            elif estado == "raio-x":
                canvas.create_text(right - 8, top + 9, anchor="ne", text="raio-X", fill=CORES["agua"], font=("Segoe UI", 8))

        total_medico_linhas = (len(self.medicos) + colunas_medicos - 1) // colunas_medicos
        base_medicos = medicos_topo + total_medico_linhas * 66 + 4
        area_topo = base_medicos + 12
        altura_area = 150
        largura_area = (x1 - x0 - 20) / 3

        raio_left = x0
        raio_right = raio_left + largura_area
        raio_fill = CORES["vermelho"] if self.piscar_colisao else "#263c46"
        canvas.create_rectangle(raio_left, area_topo, raio_right, area_topo + altura_area, fill=raio_fill, outline="#50656d", width=1)
        canvas.create_text(raio_left + 12, area_topo + 12, anchor="nw", text="RAIO-X", fill=CORES["texto"], font=("Segoe UI Semibold", 10))
        canvas.create_text((raio_left + raio_right) / 2, area_topo + 65, text="◉", fill=CORES["agua"] if not self.piscar_colisao else "white", font=("Segoe UI", 30))
        if self.piscar_colisao:
            canvas.create_text((raio_left + raio_right) / 2, area_topo + 113, text="COLISÃO", fill="white", font=("Segoe UI Semibold", 13))
        else:
            canvas.create_text((raio_left + raio_right) / 2, area_topo + 119, text="1 aparelho", fill=CORES["muted"], font=("Segoe UI", 9))

        leito_left = raio_right + 10
        leito_right = leito_left + largura_area
        canvas.create_rectangle(leito_left, area_topo, leito_right, area_topo + altura_area, fill="#1e3038", outline="#50656d", width=1)
        canvas.create_text(leito_left + 10, area_topo + 12, anchor="nw", text="UTI · 3 LEITOS", fill=CORES["texto"], font=("Segoe UI Semibold", 10))
        for cama in range(3):
            x = leito_left + 14 + cama * ((leito_right - leito_left - 44) / 3)
            y = area_topo + 57
            ocupado = cama < len(self.leitos_ocupados)
            cama_cor = CORES["vermelho"] if ocupado else CORES["verde"]
            canvas.create_rectangle(x, y, x + 28, y + 31, outline=cama_cor, width=2)
            canvas.create_rectangle(x + 3, y + 4, x + 11, y + 12, fill=cama_cor, outline=cama_cor)
            canvas.create_line(x + 3, y + 17, x + 25, y + 17, fill=cama_cor, width=3)
        canvas.create_text(leito_left + 12, area_topo + 116, anchor="nw", text=f"Esperado {max(0, 3 - len(self.leitos_ocupados))}   ·   Real {self.leitos_livres_real}", fill=CORES["muted"], font=("Segoe UI", 8))

        pront_left = leito_right + 10
        pront_right = x1
        canvas.create_rectangle(pront_left, area_topo, pront_right, area_topo + altura_area, fill="#263c46", outline="#50656d", width=1)
        canvas.create_text(pront_left + 10, area_topo + 12, anchor="nw", text="PRONTUÁRIO", fill=CORES["texto"], font=("Segoe UI Semibold", 10))
        for indice, nota in enumerate(self.notas_ids[-4:]):
            canvas.create_text(pront_left + 12, area_topo + 42 + indice * 18, anchor="nw", text=f"• Paciente {nota} · registro salvo", fill=CORES["muted"], font=("Segoe UI", 8))
        if self.nota_perdida and self.nota_perdida_ate > time.monotonic():
            canvas.create_text(pront_left + 10, area_topo + 126, anchor="nw", text=self.nota_perdida, fill=CORES["vermelho"], font=("Segoe UI Semibold", 8))
        if self.aviso_preempcao and self.aviso_ate > time.monotonic():
            canvas.create_rectangle(x0 + 5, medicos_topo - 25, x1 - 5, medicos_topo - 4, fill="#5a4724", outline="")
            canvas.create_text((x0 + x1) / 2, medicos_topo - 14, text=self.aviso_preempcao, fill=CORES["accent"], font=("Segoe UI Semibold", 9))

        canvas.configure(scrollregion=(0, 0, largura, area_topo + altura_area + 14))

    @staticmethod
    def _caixa(
        canvas: tk.Canvas,
        esquerda: float,
        topo: float,
        direita: float,
        base: float,
        titulo: str,
        cor: str,
    ) -> None:
        canvas.create_rectangle(esquerda, topo, direita, base, fill=cor, outline="#405862", width=1)
        canvas.create_text(esquerda + 10, topo + 8, anchor="nw", text=titulo, fill=CORES["muted"], font=("Segoe UI Semibold", 9))

    def _desenhar_cenario(self) -> None:
        if not hasattr(self, "canvas") or self.fechando:
            return
        canvas = self.canvas
        largura = max(620, canvas.winfo_width())
        canvas.delete("all")
        if self.comparando:
            margem = 12
            meio = largura / 2
            altura_sem = self._desenhar_pista(
                canvas, False, margem, meio - 8, 8, pequeno=True
            )
            altura_com = self._desenhar_pista(
                canvas, True, meio + 8, largura - margem, 8, pequeno=True
            )
            canvas.create_line(meio, 8, meio, max(altura_sem, altura_com), fill="#50656d", dash=(4, 4))
            placar_topo = max(altura_sem, altura_com) + 14
            self._desenhar_placar_compartilhado(canvas, margem, largura - margem, placar_topo)
            altura_total = placar_topo + 104
        else:
            altura_total = self._desenhar_pista(
                canvas, None, 18, largura - 18, 8, pequeno=False
            )
        canvas.configure(scrollregion=(0, 0, largura, altura_total + 12))

    def _estado_pista(self, faixa: bool | None) -> dict[str, object]:
        if faixa is not None:
            estado = self.estado_comparacao[faixa]
            return {
                "modo": faixa,
                "pacientes": estado["pacientes"],
                "medicos": estado["medicos"],
                "leitos": estado["leitos"],
                "leitos_livres": estado["leitos_livres"],
                "notas_ids": estado["notas_ids"],
                "notas_salvas": estado["notas_salvas"],
                "notas_total": estado["notas_total"],
                "colisoes": estado["colisoes"],
                "preempcoes": estado["preempcoes"],
                "concluidos": estado["concluidos"],
                "colisao_ate": estado["colisao_ate"],
                "preempcao_texto": estado["preempcao_texto"],
                "preempcao_ate": estado["preempcao_ate"],
                "nota_perdida": estado["nota_perdida"],
                "nota_perdida_ate": estado["nota_perdida_ate"],
                "resultado": estado["resultado"],
                "visual": estado["visual"],
            }
        return self._estado_exibicao(None)

    def _desenhar_pista(
        self,
        canvas: tk.Canvas,
        faixa: bool | None,
        esquerda: float,
        direita: float,
        topo: float,
        pequeno: bool,
    ) -> float:
        estado = self._estado_pista(faixa)
        visual = estado["visual"]
        pacientes = estado["pacientes"]
        medicos = estado["medicos"]
        escala_fonte = 8 if pequeno else 9
        largura = direita - esquerda
        titulo = "MODO COM" if estado["modo"] else "MODO SEM"
        canvas.create_text(
            esquerda + 4,
            topo,
            anchor="nw",
            text=f"{titulo}  ·  {len(medicos)} médicos",
            fill=CORES["verde"] if estado["modo"] else CORES["vermelho"],
            font=("Segoe UI Semibold", 10 if pequeno else 11),
        )

        concluidos = estado["concluidos"]
        todos = sorted(
            pacientes.items(),
            key=lambda item: (
                int(item[1].get("prioridade", 2)),
                float(item[1].get("chegada", 0.0)),
                item[0],
            ),
        )
        colunas = max(4, min(15, int((largura - 18) // (34 if pequeno else 43))))
        linhas = max(1, math.ceil(max(1, len(todos)) / colunas))
        espaco_x = (largura - 18) / colunas
        espaco_y = 29 if pequeno else 36
        raio = max(8, min(15 if not pequeno else 11, espaco_x * 0.34))
        espera_topo = topo + 22
        espera_base = espera_topo + 25 + linhas * espaco_y
        self._caixa(
            canvas,
            esquerda,
            espera_topo,
            direita,
            espera_base,
            f"TRIAGEM  ·  {sum(p.get('estado') == 'espera' for _, p in todos)} na espera",
            CORES["painel_claro"],
        )
        pos_espera: dict[int, tuple[float, float]] = {}
        for indice, (paciente_id, paciente) in enumerate(todos):
            coluna, linha = indice % colunas, indice // colunas
            x = esquerda + 9 + espaco_x * (coluna + 0.5)
            y = espera_topo + 39 + linha * espaco_y
            pos_espera[paciente_id] = (x, y)
            if paciente.get("estado") != "espera":
                continue
            if paciente_id in visual["paciente_movimentos"]:
                continue
            self._desenhar_paciente(canvas, x, y, raio, paciente_id, paciente)

        equipe_topo = espera_base + 10
        equipe_base = equipe_topo + 22
        self._caixa(canvas, esquerda, equipe_topo, direita, equipe_base, "EQUIPE MÉDICA", CORES["painel_claro"])
        equipe_topo = equipe_base + 7
        colunas_medicos = max(1, min(4, int((largura - 12) // (82 if pequeno else 116))))
        gap = 5 if pequeno else 8
        card_largura = (largura - 10 - gap * (colunas_medicos - 1)) / colunas_medicos
        altura_card = 47 if pequeno else 54
        passo_y = altura_card + (8 if pequeno else 10)
        pos_equipe: dict[int, tuple[float, float]] = {}
        pos_porta: dict[int, tuple[float, float]] = {}
        for indice, medico_id in enumerate(sorted(medicos)):
            coluna, linha = indice % colunas_medicos, indice // colunas_medicos
            card_left = esquerda + 5 + coluna * (card_largura + gap)
            card_top = equipe_topo + linha * passo_y
            card_right = card_left + card_largura
            info = medicos[medico_id]
            situacao = str(info.get("estado", "livre"))
            fill = "#263b45" if situacao == "livre" else "#24434a"
            if situacao == "aguardando":
                fill = "#4b4027"
            canvas.create_rectangle(card_left, card_top, card_right, card_top + altura_card, fill=fill, outline="#405862")
            fonte = 7 if pequeno else 8
            canvas.create_text(card_left + 6, card_top + 5, anchor="nw", text=f"MÉDICO {medico_id}", fill=CORES["agua"], font=("Segoe UI Semibold", fonte))
            paciente_atual = info.get("paciente")
            label = "LIVRE" if paciente_atual is None else f"PACIENTE {paciente_atual}"
            canvas.create_text(card_left + 6, card_top + 25, anchor="nw", text=label, fill=CORES["texto"], font=("Segoe UI", fonte))
            pos_equipe[medico_id] = (card_left + card_largura / 2, card_top + altura_card / 2)
            pos_porta[medico_id] = (esquerda + 7, equipe_topo + (linha + 0.5) * passo_y)

        linhas_medicos = math.ceil(max(1, len(medicos)) / colunas_medicos)
        recursos_topo = equipe_topo + linhas_medicos * passo_y + 3
        altura_recurso = 62 if pequeno else 68
        intervalo = 5
        pos_raio: dict[int, tuple[float, float]] = {}
        raio_y = recursos_topo
        raio_h = altura_recurso
        flash = float(estado["colisao_ate"]) > time.monotonic()
        shake = math.sin(time.monotonic() * 62) * 4 if flash else 0.0
        raio_cor = CORES["vermelho"] if flash and int(time.monotonic() * 9) % 2 else "#243942"
        canvas.create_rectangle(esquerda + shake, raio_y, direita + shake, raio_y + raio_h, fill=raio_cor, outline="#52666e", width=1)
        canvas.create_text(esquerda + 9, raio_y + 6, anchor="nw", text=f"RAIO-X  ·  {estado['colisoes']} colisões", fill=CORES["texto"], font=("Segoe UI Semibold", escala_fonte))
        canvas.create_text((esquerda + direita) / 2 + shake, raio_y + raio_h / 2 + 5, text="COLISÃO!" if flash else "APARELHO", fill="white" if flash else CORES["agua"], font=("Segoe UI Semibold", 10 if pequeno else 12))
        for indice, medico_id in enumerate(sorted(medicos)):
            delta = (indice % 3 - 1) * (10 if pequeno else 15)
            faixa_y = ((indice // 3) % 2 - 0.5) * (12 if pequeno else 18)
            pos_raio[medico_id] = (
                (esquerda + direita) / 2 + delta + shake,
                raio_y + raio_h / 2 + faixa_y,
            )

        camas_y = raio_y + raio_h + intervalo
        camas_h = altura_recurso
        canvas.create_rectangle(esquerda, camas_y, direita, camas_y + camas_h, fill="#1d3038", outline="#52666e")
        ocupados = sorted(estado["leitos"])
        esperado = max(0, 3 - len(ocupados))
        real = int(estado["leitos_livres"])
        discrepante = esperado != real
        canvas.create_text(esquerda + 9, camas_y + 5, anchor="nw", text="UTI · 3 LEITOS", fill=CORES["texto"], font=("Segoe UI Semibold", escala_fonte))
        cell_w = largura / 3
        pos_leitos: dict[int, tuple[float, float]] = {}
        for slot in range(3):
            left = esquerda + slot * cell_w + 5
            bed_top = camas_y + 23
            bed_bottom = camas_y + camas_h - 5
            paciente_leito = ocupados[slot] if slot < len(ocupados) else None
            cor_cama = CORES["vermelho"] if paciente_leito is not None else CORES["verde"]
            canvas.create_rectangle(left, bed_top, left + cell_w - 10, bed_bottom, outline=cor_cama, width=2)
            canvas.create_text(left + 7, bed_top + 4, anchor="nw", text=f"CAMA {slot + 1}", fill=CORES["muted"], font=("Segoe UI", 7 if pequeno else 8))
            if paciente_leito is not None:
                cx = left + (cell_w - 10) / 2
                cy = (bed_top + bed_bottom) / 2 + 5
                pos_leitos[paciente_leito] = (cx, cy)
                canvas.create_oval(cx - 9, cy - 9, cx + 9, cy + 9, fill=CORES["vermelho"], outline="white")
                canvas.create_text(cx, cy, text=str(paciente_leito), fill=CORES["fundo"], font=("Segoe UI Semibold", 7))
        canvas.create_text(direita - 8, camas_y + 7, anchor="ne", text=f"ESP. {esperado}  /  REAL {real}", fill=CORES["vermelho"] if discrepante else CORES["verde"], font=("Segoe UI Semibold", 8 if pequeno else 9))

        chart_y = camas_y + camas_h + intervalo
        chart_h = altura_recurso + 8
        canvas.create_rectangle(esquerda, chart_y, direita, chart_y + chart_h, fill="#263c46", outline="#52666e")
        canvas.create_text(esquerda + 9, chart_y + 6, anchor="nw", text=f"PRONTUÁRIO · {estado['notas_salvas']}/{estado['notas_total']} notas", fill=CORES["texto"], font=("Segoe UI Semibold", escala_fonte))
        notas = estado["notas_ids"][-3:]
        for indice, nota in enumerate(notas):
            instante = visual["notas_tempo"].get(nota, 0.0)
            idade = max(0.0, time.monotonic() - instante)
            deslocamento = max(0.0, 0.22 - idade) * 24
            canvas.create_text(esquerda + 12, chart_y + 27 + indice * 13 + deslocamento, anchor="nw", text=f"P{nota} · registro salvo", fill=CORES["muted"], font=("Segoe UI", 7 if pequeno else 8))
        lost = str(estado["nota_perdida"])
        if lost and float(estado["nota_perdida_ate"]) > time.monotonic():
            canvas.create_text(direita - 8, chart_y + chart_h - 5, anchor="se", text=lost, fill=CORES["vermelho"], font=("Segoe UI Semibold", 8))

        layout = {
            "espera": pos_espera,
            "equipe": pos_equipe,
            "porta": pos_porta,
            "raio-x": pos_raio,
            "leitos": pos_leitos,
            "prontuario": ((esquerda + direita) / 2, chart_y + chart_h / 2),
            "centro_x": (esquerda + direita) / 2,
            "espera_y": espera_topo + 40,
        }
        visual["layout"] = layout
        for medico_id, info in medicos.items():
            posicao = visual["medico_posicoes"].get(medico_id, pos_equipe.get(medico_id))
            if posicao is None:
                continue
            px, py = posicao
            estado_medico = str(info.get("estado", "livre"))
            cor_personagem = CORES["accent"]
            if estado_medico == "aguardando":
                cor_personagem = CORES["amarelo"]
            elif estado_medico == "raio-x":
                cor_personagem = CORES["agua"]
            personagem_raio = 12 if pequeno else 15
            canvas.create_oval(px - personagem_raio, py - personagem_raio, px + personagem_raio, py + personagem_raio, fill=cor_personagem, outline="#f8faf5", width=2)
            canvas.create_text(px, py, text=f"M{medico_id}", fill=CORES["fundo"], font=("Segoe UI Semibold", 7 if pequeno else 8))
            if estado_medico == "aguardando":
                canvas.create_text(px + personagem_raio + 3, py - 7, anchor="w", text="◷ aguardando", fill=CORES["accent"], font=("Segoe UI Semibold", 7 if pequeno else 8))

        for paciente_id, paciente in pacientes.items():
            if paciente.get("estado") not in {"transito", "atendimento"}:
                continue
            posicao = visual["paciente_posicoes"].get(paciente_id)
            if posicao is None:
                medico_atual = next(
                    (mid for mid, info in medicos.items() if info.get("paciente") == paciente_id),
                    None,
                )
                posicao = pos_equipe.get(medico_atual, (layout["centro_x"], layout["espera_y"]))
            self._desenhar_paciente(
                canvas, posicao[0], posicao[1], 10 if pequeno else 13,
                paciente_id, paciente,
            )
        if str(estado["preempcao_texto"]) and float(estado["preempcao_ate"]) > time.monotonic():
            aviso_y = equipe_topo - 4
            canvas.create_rectangle(esquerda + 4, aviso_y - 15, direita - 4, aviso_y + 3, fill="#564522", outline="")
            canvas.create_text((esquerda + direita) / 2, aviso_y - 6, text=estado["preempcao_texto"], fill=CORES["accent"], font=("Segoe UI Semibold", 8))
        return chart_y + chart_h

    @staticmethod
    def _desenhar_paciente(
        canvas: tk.Canvas,
        x: float,
        y: float,
        raio: float,
        paciente_id: int,
        paciente: dict[str, object],
    ) -> None:
        cor = COR_GRAVIDADE.get(str(paciente.get("gravidade", "VERDE")), CORES["verde"])
        canvas.create_oval(x - raio, y - raio, x + raio, y + raio, fill=cor, outline="#f6f8f4", width=1)
        canvas.create_text(x, y, text=str(paciente_id), fill=CORES["fundo"], font=("Segoe UI Semibold", 7 if raio < 12 else 8))

    def _desenhar_placar_compartilhado(
        self, canvas: tk.Canvas, esquerda: float, direita: float, topo: float
    ) -> None:
        largura = direita - esquerda
        canvas.create_rectangle(esquerda, topo, direita, topo + 96, fill=CORES["painel_claro"], outline="#50656d")
        canvas.create_text(esquerda + 12, topo + 8, anchor="nw", text="PLACAR COMPARTILHADO · MESMO SEED", fill=CORES["accent"], font=("Segoe UI Semibold", 10))
        estados = (self.estado_comparacao[False], self.estado_comparacao[True])
        col_largura = (largura - 24) / 2
        for indice, estado in enumerate(estados):
            x = esquerda + 12 + indice * col_largura
            nome = "SEM sincronização" if not estado["modo"] else "COM sincronização"
            cor = CORES["vermelho"] if not estado["modo"] else CORES["verde"]
            canvas.create_text(x, topo + 31, anchor="nw", text=nome, fill=cor, font=("Segoe UI Semibold", 9))
            canvas.create_text(
                x,
                topo + 52,
                anchor="nw",
                text=(
                    f"Colisões {estado['colisoes']}  ·  Leitos {estado['leitos_livres']} livres\n"
                    f"Notas {estado['notas_salvas']}/{estado['notas_total']}  ·  "
                    f"Espera média {self._espera_media(estado['registros']):.2f}s"
                ),
                fill=CORES["texto"],
                font=("Segoe UI", 8),
            )

    @staticmethod
    def _espera_media(registros: list[dict[str, object]]) -> float:
        if not registros:
            return 0.0
        return sum(
            max(0.0, float(item.get("inicio", 0.0) or 0.0) - float(item.get("chegada", 0.0)))
            for item in registros
        ) / len(registros)

    def _mostrar_placar_final(self) -> None:
        if self.fechando:
            return
        if self._tem_animacoes():
            self.root.after(60, self._mostrar_placar_final)
            return
        if self.comparando:
            self._mostrar_placar_comparacao()
            return
        if self.resultado_final is None:
            return
        dados = self.resultado_final
        janela = tk.Toplevel(self.root)
        janela.title("Placar final")
        janela.configure(bg=CORES["fundo"])
        janela.resizable(False, False)
        janela.transient(self.root)
        janela.grab_set()
        painel = ttk.Frame(janela, style="Panel.TFrame", padding=22)
        painel.pack(fill="both", expand=True, padx=16, pady=16)
        modo = "COM sincronização" if self.modo_atual else "SEM sincronização"
        ttk.Label(painel, text="ATENDIMENTO ENCERRADO", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            painel,
            text=f"{modo} · {self.num_medicos} médicos · {self.num_pacientes} pacientes",
            font=("Segoe UI Semibold", 13),
        ).pack(anchor="w", pady=(7, 14))
        ttk.Label(
            painel,
            text=(
                f"Colisões no raio-X: {dados.get('colisoes', 0)}\n"
                f"Leitos livres: {dados.get('leitos_livres', 3)}\n"
                f"Notas salvas: {dados.get('notas_salvas', 0)}/{dados.get('notas_total', 0)}\n"
                f"Preempções: {dados.get('preempcoes', 0)}\n"
                f"Pacientes concluídos: {dados.get('concluidos', 0)}/{self.num_pacientes}"
            ),
            justify="left",
        ).pack(anchor="w", pady=(0, 16))

        def comparar_outro_modo() -> None:
            janela.grab_release()
            janela.destroy()
            self.modo_var.set(0 if self.modo_atual else 1)
            self.iniciar()

        ttk.Button(
            painel,
            text="Rodar de novo no outro modo",
            style="Accent.TButton",
            command=comparar_outro_modo,
        ).pack(fill="x")
        ttk.Button(painel, text="Fechar", command=janela.destroy).pack(fill="x", pady=(8, 0))

    def _mostrar_placar_comparacao(self) -> None:
        if self.fechando or not self.estado_comparacao:
            return
        janela = tk.Toplevel(self.root)
        janela.title("Placar · SEM × COM")
        janela.geometry("820x450")
        janela.minsize(760, 420)
        janela.configure(bg=CORES["fundo"])
        janela.transient(self.root)
        janela.grab_set()
        painel = ttk.Frame(janela, style="Panel.TFrame", padding=22)
        painel.pack(fill="both", expand=True, padx=16, pady=16)
        ttk.Label(painel, text="MESMO CENÁRIO · DOIS RESULTADOS", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            painel,
            text=f"Seed {self.seed_atual} · {self.num_medicos} médicos · {self.num_pacientes} pacientes",
            font=("Segoe UI Semibold", 14),
        ).pack(anchor="w", pady=(5, 18))

        colunas = ttk.Frame(painel, style="Panel.TFrame")
        colunas.pack(fill="both", expand=True)
        colunas.columnconfigure(0, weight=1)
        colunas.columnconfigure(1, weight=1)
        for coluna, modo in enumerate((False, True)):
            resultado = self.estado_comparacao[modo]["resultado"] or {}
            erro = bool(resultado.get("erro"))
            erros_modo = (
                int(resultado.get("colisoes", 0)) > 0
                or int(resultado.get("leitos_livres", 3)) != 0
                or int(resultado.get("notas_salvas", 0)) < int(resultado.get("notas_total", 0))
            )
            cor = CORES["vermelho"] if erro or erros_modo else CORES["verde"]
            quadro = tk.Frame(colunas, bg="#1c2c35", highlightthickness=1, highlightbackground=cor, padx=18, pady=16)
            quadro.grid(row=0, column=coluna, sticky="nsew", padx=(0, 8) if coluna == 0 else (8, 0))
            nome = "SEM sincronização" if not modo else "COM sincronização"
            tk.Label(quadro, text=nome, bg="#1c2c35", fg=cor, font=("Segoe UI Semibold", 16)).pack(anchor="w", pady=(0, 12))
            itens = (
                ("Colisões", resultado.get("colisoes", 0)),
                ("Leitos livres", resultado.get("leitos_livres", 3)),
                ("Notas salvas", f"{resultado.get('notas_salvas', 0)} / {resultado.get('notas_total', 0)}"),
                ("Concluídos", f"{resultado.get('concluidos', 0)} / {self.num_pacientes}"),
            )
            for rotulo, valor in itens:
                tk.Label(quadro, text=rotulo.upper(), bg="#1c2c35", fg=CORES["muted"], font=("Segoe UI Semibold", 8)).pack(anchor="w", pady=(4, 0))
                tk.Label(quadro, text=str(valor), bg="#1c2c35", fg=cor if rotulo in {"Colisões", "Leitos livres", "Notas salvas"} else CORES["texto"], font=("Segoe UI Semibold", 19)).pack(anchor="w")

        botoes = ttk.Frame(painel, style="Panel.TFrame")
        botoes.pack(fill="x", pady=(18, 0))

        def executar_modo(modo: bool) -> None:
            janela.grab_release()
            janela.destroy()
            self.comparando = False
            self.controles_comparacao.clear()
            self.modo_var.set(int(modo))
            self.iniciar()

        ttk.Button(
            botoes,
            text="Rodar novamente · SEM",
            command=lambda: executar_modo(False),
        ).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(
            botoes,
            text="Rodar novamente · COM",
            style="Accent.TButton",
            command=lambda: executar_modo(True),
        ).pack(side="left", expand=True, fill="x", padx=5)
        ttk.Button(botoes, text="Fechar", command=janela.destroy).pack(side="left", padx=(5, 0))

    def fechar(self) -> None:
        self.fechando = True
        if self.controle is not None and self.executando:
            self.controle.parar()
        for controle in self.controles_comparacao.values():
            controle.parar()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ProntoSocorroGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
