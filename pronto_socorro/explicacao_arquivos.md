# Explicação objetiva dos arquivos do projeto Pronto-Socorro Concorrente

Este projeto simula um pronto-socorro usando concorrência, escalonamento e sincronização. A ideia geral é:

- cada paciente é um "processo" que chega ao sistema
- cada médico é uma "CPU" que executa pacientes
- o escalonador decide quem entra em execução
- os recursos compartilhados (raio-X, leitos e prontuário) precisam de sincronização
- a interface gráfica acompanha o andamento em tempo real

## 1) controle.py
Arquivo principal de controle de tempo e sincronização.

Função:
- simula um relógio virtual da aplicação
- controla pausa, velocidade e parada da simulação
- bloqueia threads com `threading.Condition` para evitar race conditions

Métodos principais:
- `__init__`: inicializa estado do relógio e condições
- `_avancar_tempo`: calcula avanço do tempo simulado usando tempo real
- `tempo`: retorna o tempo simulado atual
- `velocidade`: retorna velocidade atual
- `pausada`: indica se a simulação está pausada
- `parada`: indica se a simulação foi cancelada
- `registrar_ouvinte`: inscreve callbacks para mudanças de estado
- `_notificar_ouvintes`: avisa os ouvintes
- `definir_velocidade`: altera velocidade com limite entre 0.25 e 4.0
- `definir_pausa`: ativa/desativa pausa
- `parar`: encerra a simulação
- `aguardar(duracao_simulada)`: faz uma thread esperar tempo simulado, sem busy-waiting

Em SO, esse arquivo representa a lógica de relógio e sincronização entre threads.

## 2) escalonador.py
Arquivo responsável pelo escalonamento.

Função:
- mantém a fila de pacientes
- decide quem será atendido pelo próximo médico
- aplica as DUAS políticas do projeto: Prioridade preemptiva (PS) e Round Robin (RR)
- não usa polling ativo; usa `Condition.wait()`

Métodos principais:
- `__init__`: inicializa fila, estado da simulação e ouvintes
- `_acordar`: acorda threads que estão esperando
- `_tempo_simulado`: pega o tempo em simulação
- `_anunciar_chegadas`: publica eventos de pacientes que chegaram
- `publicar_chegadas`: thread que dispara eventos de chegada dos pacientes
- `_chave`: critério de ordenação (PS: `prioridade`, `chegada`, `id`; RR: ordem de entrada na fila)
- `proximo_paciente`: escolhe o próximo paciente elegível
- `apos_fatia` (PS): troca só se houver alguém ESTRITAMENTE mais grave
- `fim_quantum` (RR): quando o quantum do médico acaba, devolve o paciente ao FIM da fila
- `concluir`: marca que um paciente acabou

Em SO, esse arquivo é a parte de scheduling: fila pronta, prioridade, preempção e decisão de quem usa a CPU.

## 3) medico.py
Arquivo que representa cada médico como uma thread.

Função:
- cada objeto `Medico` é um executor de CPU
- pega pacientes do escalonador
- execute fatias de tempo
- verifica se tem que preemptar ou concluir atendimento

Métodos principais:
- `__init__`: configura identificador, escalonador, recursos e lista de trechos
- `_assumir`: inicia/retoma o paciente e atende os recursos (raio-X, leito, prontuário)
- `_anunciar_troca`: cria o evento/log da preempção ("RR: P7 usou o quantum e voltou ao fim da fila ...")
- `run`: loop principal da thread do médico; guarda o quantum usado por ESTE médico

Fluxo do `run()`:
1. pega um paciente com `proximo_paciente()`
2. verifica se precisa iniciar atendimento
3. executa fatias de tempo com `controle.aguardar(...)`
4. reduz o `restante` do paciente pelo tempo realmente gasto
5. registra o trecho no Gantt
6. conclui o paciente, ou (PS) pergunta se há alguém mais grave, ou (RR) devolve ao fim da fila quando o quantum acaba
7. repete até não haver mais paciente

Em SO, esse arquivo modela a execução real de processos pela CPU.

## 4) recursos.py
Arquivo responsável pelos recursos compartilhados.

Função:
- controla acesso ao raio-X
- controla leitos de UTI
- controla leitura e gravação do prontuário
- dispara eventos de sincronização para a interface

Métodos principais:
- `__init__`: cria semáforos, locks e contadores
- `_log`: imprime mensagem de log
- `emitir_evento`: envia evento para callback ou terminal
- `_adquirir`: tenta adquirir semáforo com espera e notificação
- `_usar_raio_x`: reserva o raio-X
- `_usar_leito`: ocupa um leito de UTI
- `liberar_leitos_ao_parar`: libera leitos em caso de parada
- `ler_prontuario`: lê notas do prontuário com leitura compartilhada
- `gravar_prontuario`: grava nota no prontuário com escrita exclusiva
- `atender_recursos`: chama os três recursos na ordem correta

Em SO, esse arquivo representa:
- semáforos
- exclusão mútua
- leitores/escritores
- gerência de recursos compartilhados

## 5) modelos.py
Arquivo com os tipos de dados usados pelo sistema.

Estruturas principais:
- `Gravidade`: enum com `VERMELHO`, `AMARELO`, `VERDE`
- `Paciente`: dataclass que representa o paciente/processo
  - campos: `id`, `gravidade`, `duracao`, `chegada`, `restante`, `inicio`, `fim`, etc.
  - `prioridade` é calculada pela gravidade
- `TrechoGantt`: dataclass para cada intervalo de execução no gráfico de Gantt
  - campos: `medico`, `paciente_id`, `gravidade`, `inicio`, `fim`

Esses modelos são a representação do domínio da simulação.

## 6) main.py
Arquivo central de execução da simulação.

Função:
- gera os pacientes
- cria o `ControleSimulacao`, `RecursosCompartilhados` e `Escalonador`
- inicia médicos e thread de chegada
- calcula métricas finais
- se necessário, exibe Gantt

Funções principais:
- `gerar_pacientes(semente, num_pacientes, janela_chegadas)`: cria a lista de pacientes com distribuições realistas de urgência, chegada e duração
- `executar_simulacao(...)`: executa uma simulação completa
- `imprimir_placar(...)`: mostra comparação entre execuções sem e com sincronização

Esse é o arquivo de orquestração do programa.

## 7) gantt.py
Arquivo de visualização.

Função:
- desenha um gráfico de Gantt para mostrar a execução ao longo do tempo

Método principal:
- `mostrar_gantt(trechos, titulo)`: monta gráfico usando `matplotlib`

O gráfico mostra:
- eixo X: tempo simulado
- eixo Y: médicos
- barras: intervalos de atendimento
- cor: gravidade do paciente
- texto: id do paciente

Em SO, isso é a representação do escalonamento em linha do tempo.

## 8) gui.py
Arquivo da interface gráfica em Tkinter.

Função:
- mostra o cenário visualmente
- recebe eventos da simulação
- atualiza pacientes, médicos, leitos, métricas e comparações
- permite pausar, reiniciar, comparar políticas, etc.

Muitos métodos importantes:
- `__init__`: configura a janela, estados e variáveis
- `_configurar_estilos`: define tema da interface
- `_montar_janela`: monta layout da aplicação
- `_consumir_eventos`: lê fila de eventos da simulação
- `_tratar_evento`: atualiza estado para execução normal
- `_tratar_evento_comparacao`: atualiza estado para comparação de políticas
- `_animar`: redesenha a tela em movimento
- `iniciar`: inicia a simulação normal
- `iniciar_comparacao`: roda comparação entre políticas
- `_preparar_simulacao`: prepara os dados de execução

Esse arquivo é a camada visual e de coordenação do sistema. Ele não decide o escalonamento, mas sincroniza e representa o que está acontecendo.

## 9) metricas.py
Arquivo de estatísticas.

Função:
- calcula métricas de tempo de espera e retorno
- mostra desempenho por gravidade

Métodos principais:
- `calcular_metricas(pacientes)`: retorna `Metricas`
- `imprimir_metricas(metricas, titulo)`: exibe resultados no terminal

## 10) testes.py
Arquivo de testes automatizados (`python testes.py`).

Função:
- colisões no raio-X: contador x contagem por força bruta x linhas "COLISAO" do log
- Round Robin (rodízio, quantum, restante preservado, chegada sem preempção)
- Prioridade preemptiva (só interrompe quem é estritamente mais grave)
- métricas (E = retorno - duração, Resp <= E) e regressão (SEM x COM, deadlock, janela)

É a parte de validação da teoria de escalonamento.

# Resumo final

- `controle.py`: relógio e sincronização
- `escalonador.py`: scheduling
- `medico.py`: execução de processos pela CPU
- `recursos.py`: semáforos e recursos compartilhados
- `modelos.py`: dados do sistema
- `main.py`: orquestração da simulação
- `gantt.py`: visualização em Gantt
- `gui.py`: interface e monitoramento
- `metricas.py`: métricas de desempenho
- `testes.py`: testes automáticos

Se quiser, eu também posso transformar este arquivo em um resumo mais curto para apresentação oral, ou em um mapa mental da arquitetura do programa.
