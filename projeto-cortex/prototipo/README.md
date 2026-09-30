# Projeto Córtex · protótipo em simulação

O cérebro do robô das etapas 1 a 4, rodando como programa. Cada módulo usa o código
do atlas (`DIE-TH`, `LIM-AM`, `CB-00`...), e toda comunicação passa por um barramento
de mensagens no formato do protocolo da Etapa 4. O robô vive numa sala simulada de
8 m × 6 m, vista de cima.

Python puro, sem dependências. Precisa de Python 3.10 ou mais novo.

## Como rodar

```bash
cd projeto-cortex/prototipo

# roda os 7 cenários, imprime as mensagens e grava viewer/trilhas.js
python -m cortex.simulador

# só alguns cenários
python -m cortex.simulador pare perigo

# testes automáticos (20)
python -m unittest discover -s tests -t . -v
```

Para ver as simulações, abra `viewer/index.html` no navegador depois de rodar o simulador.

## O que está em cada arquivo

| Arquivo | O que é |
|---|---|
| `spec/cortex.json` | A especificação completa exportada do atlas (etapas 1 a 4): módulos, comandos, parâmetros, regras e cenários. O cérebro é montado a partir dela. |
| `cortex/bus.py` | O barramento: entrega por horário e prioridade (P0 primeiro), descarta mensagens vencidas (`ttl_ms`) e registra tudo (R8). |
| `cortex/parametros.py` | A neuroquímica: faixas, quem pode alterar cada parâmetro, recompensa bloqueada (R5), supressão que expira (R7), alerta que volta ao repouso. |
| `cortex/modulos.py` | Os módulos com comportamento. Os 19 módulos restantes existem no barramento como módulos passivos. |
| `cortex/mundo.py` | A sala: robô com rodas e garra, copos, base de recarga, pessoas, bateria. As rodas têm um desvio de 0,12 rad que o cerebelo precisa aprender. |
| `cortex/cerebro.py` | Monta tudo e roda o relógio em passos de 5 ms. Câmera a 30 quadros por segundo, propriocepção a 100 Hz. |
| `cortex/simulador.py` | Os 7 cenários e a gravação das trilhas para o visualizador. |
| `tests/test_cerebro.py` | Um teste por cenário e por regra. |
| `viewer/` | Visualizador web que reproduz as trilhas. |

## Módulos implementados (21 de 40)

Percepção: `CTX-A1`, `CTX-WE`, `DIE-TH`, `CTX-OC`, `CTX-TE`, `CTX-PA`, `CTX-S1`.
Valor e segurança: `LIM-AM`, `BG-NA`, `MB-SN`, `LIM-HC`.
Deliberação: `CTX-PF`, `CTX-BR`.
Controle motor: `BG-00`, `CTX-M1`, `CB-00`, `SC-00`.
Corpo: `DIE-HY`, `END-HP`, `END-PN`, `BS-PO`.

## O que os testes comprovam

| Cenário ou regra | Resultado medido na simulação |
|---|---|
| Pegar o copo | O primeiro movimento sai 0,24 s depois de o robô ouvir; o copo está na garra em 6,8 s. |
| Cerebelo | Aprende o desvio das rodas (0,120 rad; o real é 0,12) e o erro de direção cai de 0,028 para 0,008 rad. |
| Pare! | Os motores travam 15 ms depois do grito, cerca de 200 ms antes de a frase ser entendida. |
| Pessoa se aproximando | O freio sai 5 ms depois da detecção. Perto de pessoas, a velocidade nunca passa de 0,5 m/s. |
| Bateria | Abaixo de 15%, a recarga vence a tarefa; o robô chega à base, entra em repouso e consolida a memória. |
| R1 | “Empurre a Ana” é vetado; nenhum motor recebe comando. |
| R2 | Só o dono libera a parada; o planejador tenta e é recusado. |
| R3 | Um comando de 5 m/s sai como 1 m/s. |
| R4 | Só o córtex motor move a base; comandos de outros módulos são recusados. |
| R5 | Dono, planejador e engenharia não conseguem alterar a recompensa. |
| R6 | Comando com confiança baixa: o robô pergunta em vez de agir. |
| R7 | A supressão de alarme volta a zero sozinha em 60 s. |
| R8 | Intenção, risco, veto e fala ficam no registro. |
| R9 | Pessoa sem consentimento não é reconhecida pelo nome. |

## Limites deste protótipo

- A compreensão de linguagem é por palavras-chave, não um modelo de linguagem. Só os comandos dos cenários são entendidos.
- A visão recebe a posição real dos objetos com um pouco de ruído. Não há processamento de imagem.
- O mundo é 2D, com física simplificada (sem colisão com objetos, sem braço articulado).
- 19 dos 40 módulos ainda são passivos.

## Caminho para o ROS 2

A estrutura foi pensada para migrar sem reescrever a lógica:

- Cada módulo vira um nó ROS 2 com o mesmo código (`cortex_die_th`, `cortex_lim_am`...).
- Cada mensagem vira um tópico `/cortex/<para>/<sinal>`, com uma mensagem ROS de campos iguais ao protocolo (`de`, `tipo`, `prioridade`, `dados`, `peso`, `ttl_ms`).
- As prioridades viram perfis de QoS: P0 e P1 confiáveis e com prazo; fluxos de sensor com melhor esforço.
- `SC-00`, `BS-BU` e as regras R2 e R3 saem do computador principal e vão para um microcontrolador separado.
- O `mundo.py` é substituído por um simulador físico (Gazebo ou Isaac Sim) e, depois, pelo robô real.
