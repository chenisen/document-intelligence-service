# MVP, recorte da primeira entrega

Versão 2.0 · Setembro de 2026 · Recorte de `PRD.md`

> Apêndice de `PRD.md`, que é a fonte. Em caso de divergência, o PRD vence.

Este documento não repete o PRD. Ele diz o que entra agora, o que fica para depois, em que ordem, e qual é a prova de que acabou. Onde cita `RF-XX` ou `RNF-XX`, o texto completo está no `PRD.md`.

---

## 1. O que o MVP entrega

Dois tipos documentais, atestado médico e resultado de avaliação médica, os quatro formatos de
arquivo publicados no contrato — PDF, JPEG, PNG e HEIC — e uma única forma de invocação: síncrona,
sem estado e sem armazenamento.

A escolha dos tipos usa três premissas a confirmar no discovery: eles seriam os dois de maior volume,
o atestado concentraria a maior ocorrência de erro humano e, juntos, cobririam cerca de 70% dos
documentos recebidos. O que o case comprova é apenas que os dois têm estruturas distintas e pertencem
à lista sugerida para a demonstração.

A assincronia saiu do escopo do produto. O motivo está na seção 3 do PRD e resume-se a isto: job e máquina de estados descrevem um fluxo, e fluxo é do consumidor. Quem precisar de assincronia envolve a peça, e o desenho de quem envolve vai para a apresentação como diagrama: é código do consumidor, e não cabe neste repositório.

Consequência direta: a política de retenção volta a ser uma frase que o teste prova, e somem do MVP o armazenamento, a fila, o orquestrador, o barramento de evento, a segunda região e o desenho de expurgo.

## 2. Requisitos dentro do MVP

**Entrada e contrato**: RF-01, RF-15, RF-16, RF-17, RF-18

**Leitura e extração**: RF-02, RF-03, RF-04, RF-05, RF-06, RF-07, RF-08, RF-09, RF-10, RF-11, RF-12, RF-19

**Revisão humana e aterramento**: RF-13, RF-14, RF-20

**Trilha**: RF-22

**Não funcionais**: RNF-04, RNF-05, RNF-06, RNF-07 e RNF-09 são **medidos no MVP**, porque teste e
contrato os provam sem conta. RNF-10, o idioma dos documentos, é propriedade do conjunto de
referência e não tem teste: todo documento dele é em português do Brasil, e não há o que medir. RNF-01, RNF-02, RNF-03, RNF-08, RNF-11 e RNF-12 entram como
**premissa de implantação**: latência, disponibilidade, custo, rede privada, vazão e região não são
verificáveis com dublê, e declarar que estão prontos seria previsão de ambiente disfarçada de entrega.

O MVP entrega o fluxo ponta a ponta das quatro capacidades do case para os dois tipos publicados:
classificação, extração, validação com decisão de revisão e recuperação de conhecimento. Também
entrega contrato, ausência de retenção, trilha e avaliação. Não entrega o produto inteiro: os quatro
tipos adicionais sugeridos pelo case, o retorno da revisão, os sinais de adulteração e a comparação
com histórico permanecem no horizonte descrito no PRD §16.

## 3. O que explicitamente não entra

| Não entra | Por quê |
| --- | --- |
| Assincronia, job, URL pré-assinada e evento | descrevem fluxo, e fluxo é do consumidor; o invólucro é diagrama na apresentação |
| Armazenamento de documento ou de resultado | sem assincronia, não existe motivo para guardar |
| Processamento em lote | mesma razão: é orquestração do lado de quem chama |
| Tipos documentais além dos dois publicados | o case exige pelo menos dois tipos distintos para a demonstração. Os outros quatro exigem evolução do contrato e casos de referência próprios |
| Cache do enriquecimento normativo | otimização sem número que a justifique ainda |
| Detecção de indício de adulteração | maior valor e maior peso legal: cria inferência sobre uma pessoa |
| Divergência frente a histórico informado | o contrato recebe apenas o arquivo; adicionar histórico muda contrato, minimização e fronteira da peça |
| Validação de CRM contra fonte externa | quebra a postura de rede sem saída para a internet e depende de contrato com o CFM |
| Painel de qualidade para o negócio | é produto separado consumindo métrica |
| Interface de usuário | contraria a restrição de desacoplamento do enunciado |
| Retorno da revisão humana, RF-21, e o `POST /v1/feedback` | ver abaixo |

### Por que o retorno da revisão saiu

RF-21 permanece no horizonte do produto, mas não integra o contrato publicado do MVP. O motivo é a
régua deste próprio documento aplicada a ele:

- **Não é nenhuma das quatro capacidades que o enunciado nomeia.** Classificação, extração, validação
  e conhecimento; retorno de revisão não é nenhuma delas.
- **Não faz parte do fluxo ponta a ponta** que o entregável 5 cobra.
- **Atende necessidade que ainda não existe.** Ele serve para calibrar limiar com o retorno da
  revisão. Sem produção, sem revisor e sem dado, é construir para um futuro que não chegou.
- **O consumidor pode emitir a métrica sozinho.** Ele já sabe o veredito. O único ganho de passar
  pela minha API era o contador cair no meu namespace, com o meu vocabulário. Isso é conveniência de
  integração, não capacidade.
- **Era o único ponto em que a peça pedia trabalho do consumidor em benefício dela**, o que é
  acoplamento na direção que a seção 3 do PRD diz não existir.

Como o endpoint não integra o contrato publicado, não há remoção nem migração a fazer. Se RF-21 for
priorizado, a adição passa primeiro por ADR, depois por spec e pelos testes de contrato previstos no
PRD.

O que fica no lugar é a informação necessária para o consumidor medir sua própria operação: confiança
por campo e motivos de revisão em código estável. Calibrar limiares com retorno estruturado continua
sendo uma hipótese futura, não uma capacidade implícita do MVP.

## 3.1 O conjunto de referência, e por que ele é pequeno

Sete documentos, dos dois tipos do MVP. Cada um prova uma coisa que nenhum outro prova, e o que saiu
era variação de formato que aumentava o peso do repositório e o tempo da suíte sem mudar asserção.

| Arquivo | O que só ele prova |
| --- | --- |
| `atestado_01_pdf_nativo.pdf` | caminho feliz, camada de texto confiável, e o OCR **não** é chamado |
| `atestado_02_pdf_digitalizado.pdf` | mesmo formato do anterior, rota OCR: a extensão não decide nada |
| `atestado_06_captura_tela.png` | extração parcial, campo ausente volta nulo, revisão por CRM ausente e por qualidade marginal |
| `atestado_07_foto.heic` | conversão HEIC para JPEG antes de qualquer medida |
| `atestado_08_duas_paginas.pdf` | rasterização página a página |
| `resultado_01_pdf_nativo.pdf` | segundo tipo, deferido, com período concedido preenchido |
| `resultado_02_indeferido_digitalizado.jpg` | segundo tipo, indeferido, período concedido nulo e não inventado |

Arquivo acima do limite não é documento do conjunto: os bytes são construídos no teste, porque o que
se prova ali é uma contagem.

**A recusa de documento fora do catálogo não tem arquivo aqui, e isso é decisão.** O gerador produz
apenas os dois tipos do MVP. No perfil `fake`, acrescentar um ASO com resposta ditada pelo gabarito
não provaria qualidade de classificação; provaria apenas que o pipeline trata classificação nula.
Esse comportamento é testado diretamente com um modelo injetado que devolve nulo, em
`test_http_refuses_a_document_outside_the_catalogue`. Qualidade de classificação só a avaliação
contra uma conta real prova.

**Sobre os nomes do conjunto.** Seis pessoas distintas em sete documentos, com equilíbrio de gênero e
**com acento**. As duas coisas foram consertadas depois de uma pergunta que eu não soube responder:
por que só havia nome de mulher. A resposta era que quatro dos sete documentos eram o mesmo documento
re-encodado, então uma pessoa aparecia quatro vezes — viés que ninguém decidiu e ninguém revisou. Hoje
só o par `01`/`02` compartilha pessoa, porque é ele que isola o formato como única variável.

O achado maior veio junto: **o corpus não tinha um único acento**, num extrator de documento
brasileiro cujo `core/policy.py` dobra acento justamente porque português tem. O caminho estava
coberto por teste unitário e nunca era exercitado ponta a ponta. Agora `Thaís Nogueira Rebouças` e
`João Vítor Sampaio Rocha` atravessam normalização, OCR, extração e verificação de evidência.

**Os documentos não são versionados.** Fonte é o gerador, `samples/gerar_sinteticos.py`, e o gabarito.
Os binários e os dublês são artefatos de build, reconstruídos com `make fixtures`. O gerador é
determinístico — duas fontes de não determinismo foram encontradas e fechadas, o `CreationDate` do
reportlab e o do Pillow — e há teste que guarda essa propriedade, porque sem ela toda chave de dublê
erraria.

## 4. Componentes no MVP

| Componente | Papel |
| --- | --- |
| Porta de entrada HTTP | recebe o arquivo e devolve o contrato |
| Função com o pipeline inteiro | normaliza, roteia, chama, verifica evidência, compõe confiança e monta a resposta |
| Textract | OCR, uma chamada por página |
| Bedrock | classificação e extração com schema, mais Guardrails. **O raciocínio sobre o documento é configuração do Bedrock**, não código daqui |
| Kendra | recuperação da norma interna aplicável. **O conhecimento é o índice**, não uma tabela em Python. Ver ADR-0001 |
| Observabilidade | trilha sem conteúdo, métrica de negócio |

A divisão que importa: **este repositório é a peça de entrada e saída**. Ele normaliza o arquivo,
escolhe a rota, invoca, verifica que a resposta está ancorada no documento, compõe a confiança e
devolve o contrato. Conhecimento e raciocínio ficam na configuração do Bedrock e no índice do Kendra,
que evoluem sem que este código mude, e que são desenhados e avaliados separadamente.

Sem bucket, sem tabela, sem fila, sem orquestrador, sem barramento. Topologia de rede, autorizador,
plano de uso e região são premissa de implantação: não estão neste repositório e nenhum teste daqui
os prova.

## 5. Fatias de entrega

Vertical, uma por vez, cada uma terminando testável.

| Nº | Fatia | Requisitos | Pronto quando |
| --- | --- | --- | --- |
| 0 | Esqueleto, contrato, limite e ambiente local | RF-01, RF-17, RNF-06, RNF-07, RNF-09 | endpoint e contrato publicados, limite cobrado e `make test` verde sem credencial |
| 1 | Normalização e roteamento, spec 0001 | RF-02, RF-03, RF-04, RF-19 | cada formato do conjunto cai na rota declarada e multipágina é lido por página |
| 2 | Classificação, spec 0002 | RF-05, RF-15 | tipos do catálogo são reconhecidos, nulo é recusado e erros mantêm código estável |
| 3 | Atestado, parte da spec 0003 | RF-06, RF-08, RF-09, RF-10, RF-20 | campos saem com evidência; ausência, limiar e evidência inválida abstêm sem chute |
| 4 | Resultado de avaliação, parte da spec 0003 | RF-07, RF-08, RF-09, RF-10, RF-20 | segundo tipo usa o mesmo fluxo e não inventa CID nem período concedido |
| 5 | Validação, conhecimento e revisão, spec 0004 | RF-11, RF-12, RF-13, RF-14, RF-16 | resposta traz validações, norma, revisão, proveniência e degradação explícita |
| 6 | Trilha e retenção, spec 0005 | RF-18, RF-22, RNF-04, RNF-05 | trilha sem conteúdo, repetição sem efeito colateral e ausência de persistência |
| 7 | Avaliação e portão no CI, spec 0006 | RF-05, RF-06, RF-07, RF-09, RF-10, RNF-04, RNF-07; PRD §6.1 e §11 | sete casos medidos e merge bloqueado quando a regressão excede o limite |
| 8 | Custo por documento na avaliação, spec 0007 | RNF-03 | a avaliação no perfil `aws` informa o custo variável médio a partir do consumo medido; no `fake`, nulo |

Fatia 0 é feita pelo time inteiro em par. Só depois dela o trabalho paraleliza.

A fatia 6 vem antes da avaliação de propósito: ausência de persistência e trilha sem conteúdo são requisito legal, e requisito legal não é o que se corta quando o prazo aperta.

## 6. Ordem de risco

O que eu atacaria primeiro se o tempo encurtar, por ordem:

1. Fatias 0 e 1, porque sem contrato e sem leitura não existe nada para demonstrar.
2. Fatias 2 e 3, que fecham o primeiro caminho ponta a ponta.
3. Fatia 6, porque sustenta a conversa de minimização e trilha.
4. Fatia 4, porque o segundo tipo distinto é critério explícito do case.
5. Fatias 5 e 7, que fecham conhecimento, degradação e medição.

Não existe corte do segundo tipo compatível com o entregável 5 do case. Se o prazo encurtar,
reduzem-se variações redundantes do corpus e acabamento do relatório, não os dois tipos, a trilha ou
a avaliação. Se alguma dessas capacidades faltar, a entrega deve ser apresentada como parcial, não
como MVP concluído.

## 7. Critério de pronto do MVP

Além dos critérios de aceite do PRD, seção 11:

- os casos do conjunto de referência rodam na avaliação, com número por campo e por formato
- nenhum adapter de escrita existe no código, provado por teste
- a trilha registra a análise sem conteúdo e sem valor extraído, provado por teste
- a demonstração roda sem nenhuma tela: Swagger, linha de comando e o relatório de avaliação
- `make test` roda em máquina limpa, sem credencial

## 8. Números que sustentam o recorte

| Número | Valor | O que ele decide |
| --- | --- | --- |
| 500 documentos por dia | premissa de dimensionamento | pouco mais de um por minuto no horário comercial; não justifica fila nem lote dentro da peça |
| 15 minutos por documento hoje | premissa para o caso de negócio | combinada ao volume, resulta em 125 horas por dia, ou 15,6 pessoas em dedicação integral |
| Dois tipos de maior volume | premissa: atestado e resultado de avaliação médica | orienta o recorte, a confirmar com distribuição real |
| Maior erro humano no atestado | premissa de priorização | justifica o limiar mais conservador e a maior atenção no conjunto de referência |
| Região não especificada no case | omissão do enunciado | `us-east-1` é decisão da ADR-0002 e exige validação regulatória e jurídica antes da implantação |

## 9. O que muda no documento de apresentação

Registrado para não passar batido: a frase "a peça não retém nada" continua valendo, e ganha uma defesa a mais. Ela não é consequência de um MVP pequeno, é consequência de manter a assincronia fora. Se perguntarem como o produto escala para arquivo grande ou para lote, a resposta é que o consumidor envolve a peça; esse invólucro aparece como diagrama na apresentação, não como implementação deste repositório.
