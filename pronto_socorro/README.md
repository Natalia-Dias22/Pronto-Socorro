# Pronto-Socorro Concorrente

Trabalho Pratico 3 - Semaforos, da disciplina de Sistemas Operacionais (Inatel).
O simulador representa pacientes como processos, medicos configuraveis como CPUs
e os recursos da emergencia como secoes criticas. Os valores padrao sao 2 medicos
e 16 pacientes.

## Como executar

Requer Python 3.10 ou superior. Colorama colore o log; sem ela o programa continua
funcionando sem cores. Matplotlib e opcional e necessario somente para o Gantt.

```powershell
python main.py
```

Para abrir a interface visual feita com Tkinter (incluido no Python):

```powershell
python gui.py
```

`python main.py` continua oferecendo o menu de terminal. Na janela, escolha o
modo e a política, ajuste médicos, pacientes, seed e velocidade; pause, continue
ou reinicie o cenário pelos controles à esquerda. Use **Comparar políticas** para
executar Prioridade e SJF em sequência com o mesmo modo e seed.

Nas opcoes 1, 2 e 3, informe a quantidade de medicos e pacientes; Enter aceita o
valor sugerido. A opcao 4 executa a bateria com (2,16), (10,16), (2,40) e (10,40)
nos dois modos. Para repetir outro cenario, use `python main.py --seed 123`. Para
abrir os graficos de Gantt, instale matplotlib e use `python main.py --gantt`.

Instalacao opcional das dependencias visuais:

```powershell
python -m pip install colorama matplotlib
```

## O que cada modo demonstra

- **Sem sincronizacao:** o contador do raio-X pode registrar colisao; a atualizacao
  de leitos separa leitura e escrita; gravadores do prontuario copiam e substituem
  a lista, podendo perder notas.
- **Com sincronizacao:** `Semaphore(1)` implementa exclusao mutua no raio-X,
  `Semaphore(3)` limita os leitos. Um lock de instrumentacao separado protege
  somente a contagem de ocupantes/colisoes e nao impede colisao no modo SEM.
  No prontuario,
  semaforos implementam o padrao leitores/gravadores.
- A ordem de acesso e sempre raio-X, leito e prontuario. Os tres pacientes que
  precisam de UTI mantem os leitos ocupados ate o fim, para que o contador final
  sincronizado seja zero.
- Prioridade preemptiva atende casos graves primeiro (vermelho, amarelo, verde),
  com risco de starvation. SJF preemptivo (SRTF) escolhe o menor tempo restante,
  pode preemptar ao fim de cada fatia de 0,1 s e tende a reduzir a espera media,
  mas ignora a gravidade. Empates usam ordem de chegada. Uma `Condition` bloqueia
  os medicos ate haver paciente elegivel, sem busy waiting.
- O horario `inicio` e gravado somente no primeiro atendimento, mesmo que o
  paciente seja preemptado e volte a fila.
- A bateria mostra colisoes no raio-X, leitos livres ao final, notas persistidas
  sobre o total de gravacoes e espera media em cada combinacao. O contador final,
  o painel e a bateria leem o mesmo contador protegido da instrumentacao.

As metricas seguem o enunciado: espera e resposta sao `inicio - chegada`, e
retorno e `fim - chegada`. Sao exibidas medias gerais e por gravidade para espera,
retorno e resposta. A carga e gerada com `random.Random(seed)`; os dois primeiros
pacientes compartilham recursos de proposito para tornar as condicoes de corrida
observaveis.

## Roteiro de apresentacao em 5 minutos

1. (0:00-0:45) Explique o mapeamento: paciente/processo, medico/CPU e recurso/secao critica.
2. (0:45-1:45) Execute a opcao 1 e mostre colisao no raio-X, contador de UTI sujeito
   a atualizacao perdida e possiveis notas sobrescritas.
3. (1:45-2:45) Execute a opcao 2 e compare os invariantes: zero colisao, tres leitos
   ocupados e todas as notas persistidas.
4. (2:45-4:00) Mostre que `Semaphore(1)` e exclusao mutua, `Semaphore(3)` e um
   semaforo de contagem, e que o prontuario permite varios leitores ou um gravador.
5. (4:00-5:00) Explique a preempcao por gravidade e as metricas de espera,
  retorno e resposta. Se houver tempo, mostre `--gantt`.

## Perguntas provaveis

- **Por que aparece uma race condition?** Duas threads leem o mesmo estado antes
  de qualquer uma gravar o novo valor, entao uma atualizacao pode sobrescrever a outra.
- **Mutex e semaforo sao a mesma coisa?** Um mutex representa propriedade de
  exclusao mutua; um semaforo tambem pode contar vagas, como os tres leitos.
- **Como o codigo evita deadlock?** Os recursos sao solicitados sempre na mesma
  ordem e nao ha espera circular entre eles.
- **A secao critica garante espera limitada?** Exclusao mutua sozinha nao garante
  justica; a politica interna do semaforo pode nao ser FIFO.
- **Por que inicio e definido uma unica vez?** E o primeiro atendimento do paciente;
  isso permite medir resposta mesmo quando o processo sofre preempcao.
- **O que o Gantt acrescenta?** Exibe qual medico executou cada fatia e evidencia
  as trocas de contexto causadas pela prioridade preemptiva.