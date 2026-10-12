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
modo, o algoritmo de escalonamento, ajuste médicos, pacientes, seed e velocidade;
pause, continue ou reinicie o cenário pelos controles à esquerda. Os botões
`SEM × COM` e `PS × RR` rodam o mesmo cenário lado a lado. Ao fim do `PS × RR`,
uma janela compara espera, retorno e resposta por gravidade e trocas de contexto,
destacando o menor valor de cada critério.

Nas opcoes 1, 2 e 3, informe a quantidade de medicos, pacientes e o algoritmo;
Enter aceita o valor sugerido. A opcao 4 executa a bateria com (2,16), (10,16),
(2,40) e (10,40) nos dois modos, usando o algoritmo atual. A opcao 5 roda o mesmo
cenario COM sincronizacao nos dois algoritmos e compara espera, retorno e resposta
por gravidade. Para repetir outro cenario, use `python main.py --seed 123`; para
comecar com Round Robin, `python main.py --algoritmo rr`. Para abrir os graficos
de Gantt, instale matplotlib e use `python main.py --gantt`.

Instalacao opcional das dependencias visuais:

```powershell
python -m pip install colorama matplotlib
```

## O que cada modo demonstra

- **Sem sincronizacao:** o contador do raio-X pode registrar colisao; a atualizacao
  de leitos separa leitura e escrita; gravadores do prontuario copiam e substituem
  a lista, podendo perder notas.
- **Com sincronizacao:** `Semaphore(1)` implementa exclusao mutua no raio-X,
  `Semaphore(3)` limita os leitos e um `Lock` protege o contador. No prontuario,
  semaforos implementam o padrao leitores/gravadores.
- A ordem de acesso e sempre raio-X, leito e prontuario. Os tres pacientes que
  precisam de UTI mantem os leitos ocupados ate o fim, para que o contador final
  sincronizado seja zero.
- Ha dois algoritmos de escalonamento (Cap. 5), sobre uma fila de prontos comum
  aos medicos (multiprocessamento simetrico). Uma `Condition` bloqueia os medicos
  ate haver paciente elegivel, sem busy waiting. Cada medico executa fatias de 0,1 s.
  - **Prioridade preemptiva (PS):** vermelho tem prioridade sobre amarelo, que tem
    prioridade sobre verde; empates seguem FCFS. Ao fim da fatia, o medico troca de
    paciente se houver alguem mais grave na fila.
  - **Round Robin (RR):** a fila de prontos e circular (FIFO) e ignora a gravidade.
    A fatia e o quantum: ao fim dele, se houver outro paciente pronto, o atual volta
    para o final da fila. Nao ha starvation, mas o vermelho espera como os demais.
- O horario `inicio` e gravado somente no primeiro atendimento, mesmo que o
  paciente seja preemptado e volte a fila.
- A bateria mostra colisoes no raio-X, leitos livres ao final, notas persistidas
  sobre o total de gravacoes e espera media em cada combinacao.

As metricas seguem as definicoes do Cap. 5 (Criterios de Scheduling):

- **Espera:** tempo total na fila de prontos. O escalonador soma cada periodo na
  fila, inclusive cada volta apos uma preempcao (como no exemplo de RR do material).
  Tempo em que o medico esta bloqueado em um semaforo nao conta como espera.
- **Resposta:** `inicio - chegada`, ate o primeiro atendimento. So difere da espera
  para pacientes que sofreram preempcao.
- **Retorno (turnaround):** `fim - chegada`.

As medias (gerais e por gravidade) consideram os pacientes concluidos e saem de
uma unica funcao (`metricas.calcular_metricas`) com a mesma formatacao (2 casas):
o painel lateral, o placar da comparacao, a janela final e o terminal mostram
sempre os mesmos valores. A carga e gerada com `random.Random(seed)`; os dois
primeiros pacientes compartilham recursos de proposito para tornar as condicoes
de corrida observaveis.

## Roteiro de apresentacao em 5 minutos

1. (0:00-0:45) Explique o mapeamento: paciente/processo, medico/CPU e recurso/secao critica.
2. (0:45-1:45) Execute a opcao 1 e mostre colisao no raio-X, contador de UTI sujeito
   a atualizacao perdida e possiveis notas sobrescritas.
3. (1:45-2:45) Execute a opcao 2 e compare os invariantes: zero colisao, tres leitos
   ocupados e todas as notas persistidas.
4. (2:45-4:00) Mostre que `Semaphore(1)` e exclusao mutua, `Semaphore(3)` e um
   semaforo de contagem, e que o prontuario permite varios leitores ou um gravador.
5. (4:00-5:00) Explique a preempcao por gravidade e as metricas de espera,
  retorno e resposta. Use a opcao 5 para comparar PS e RR. Se houver tempo,
  mostre `--gantt`.

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
  as trocas de contexto causadas pela preempcao (por gravidade ou por quantum).
- **Por que espera e resposta sao diferentes?** Resposta mede so ate o primeiro
  atendimento; espera soma todo o tempo na fila de prontos, inclusive depois de
  cada preempcao. No RR a resposta e baixa, mas a espera cresce a cada quantum.
- **PS ou RR?** O PS minimiza a espera dos vermelhos, mas pode causar starvation
  nos verdes (resolvida com aging). O RR e justo e tem resposta baixa, mas aumenta
  a espera media e o numero de trocas de contexto.