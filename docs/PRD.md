# Document Intelligence Service, PRD

Serviço que interpreta documentos médicos e devolve dados estruturados com confiança e evidência por campo.

**Este documento é a fonte de requisitos do repositório.** O enunciado externo continua sendo
`case.md`; este PRD registra o recorte adotado para atendê-lo. Todo o resto é apêndice: detalha,
não redefine. Em caso de divergência interna, o PRD vence, e o apêndice é que está errado.

Nenhuma linha de código nasce sem estar amarrada a um requisito daqui ou a uma spec em `specs/`.

| Apêndice     | O que ele acrescenta, e não repete                                                    |
| ------------ | ------------------------------------------------------------------------------------- |
| `PRD-MVP.md` | o recorte da primeira entrega: o que entra agora, o que fica, e a prova de que acabou |
| `adr/`       | as decisões irreversíveis, com a alternativa descartada em cada uma                   |
| `specs/`     | comportamento observável por fatia, com regras numeradas e os testes que as provam    |

Três números deste documento são amarrados ao código por teste, porque foram os que divergiram:
o limite de 4 MB, o alvo de p95 e a região. Divergir deles quebra a build, não a revisão.

---

## 1. Objetivo

Receber um documento médico em PDF, JPEG, PNG ou HEIC e, quando ele pertencer ao catálogo
publicado, devolver o tipo e os campos correspondentes, cada campo com o trecho que o originou e um
grau de confiança, além da indicação de quando o caso precisa de revisão humana. A primeira versão
publicada cobre dois tipos; os demais tipos sugeridos pelo case são horizonte de evolução.

## 2. Não-objetivos

O serviço não decide nada de negócio. Não aprova, não defere, não conclui elegibilidade e não conhece o fluxo que o chama. Não tem interface de usuário. Não armazena documento nem resultado. Não é fonte de consulta histórica. Não detecta reenvio de documento, porque isso depende de histórico do processo, e o processo é do consumidor.

E o mais importante para entender o desenho: **o serviço não é assíncrono, e isso é decisão, não limitação.**

## 2.1 O que as premissas de dimensionamento decidem

O case não informa volume, tempo manual, distribuição entre tipos, consumidor inicial nem região.
Os números da seção 4.1 são premissas do projeto, a validar no discovery. Esta seção diz o que
cada uma **decide**, porque premissa que não muda decisão é enfeite de slide.

| Número                                                    | O que ele decide                                                                                                                                                      |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 500 documentos por dia                                    | sem fila, sem lote, sem orquestrador e sem provisionamento. É pouco mais de um por minuto no horário comercial: uma invocação síncrona por documento resolve, e sobra |
| 15 minutos por documento hoje                             | é a linha de base do ganho, e é de onde sai o caso de negócio                                                                                                         |
| Atestado é o de maior volume **e** o de maior erro humano | ele entra primeiro, na fatia 3, e é ele que recebe o limiar mais conservador                                                                                          |
| Consumidor inicial, RH e saúde                            | autorizador por consumidor dentro de um público só. Não é peça multi-inquilino do banco inteiro                                                                       |
| Região não especificada no case                          | fica o padrão adotado, `us-east-1`: ADR-0002                                                                                                                         |
| Normas internas existem, mas não foram fornecidas         | presumidas, com corpo sintético em `knowledge/`, marcado como fictício                                                                                                |

### O caso de negócio, em uma conta

500 documentos por dia a 15 minutos cada são **125 horas de leitura manual por dia**, cerca de 15
pessoas em dedicação integral apenas conferindo documento. A meta de p95 em 25 segundos não é uma
otimização de 10%: é outra ordem de grandeza.

O ganho real, porém, não é o tempo. É o atestado ser, ao mesmo tempo, o tipo de maior volume e o de
maior erro humano em campo crítico. Errar o período de afastamento manda a decisão para o lugar
errado, e é por isso que a peça prefere abster a chutar.

### O que o volume permite não construir

Cerca de 21 documentos por hora em média. Mesmo com o pico presumido de três vezes isso, a invocação síncrona
aguenta. Isso sustenta com número, e não com opinião, a ausência de fila, de lote, de orquestrador e
de qualquer provisionamento antecipado.

O mesmo volume é o que torna o Kendra caro: ele cobra por hora de índice provisionado, não por
consulta. A cerca de 11 mil consultas por mês útil, o custo fixo do índice domina o custo por
documento e vira a maior linha isolada da conta. Está na ADR-0001.

## 3. A peça é uma função, a assincronia é do consumidor

Uma análise não tem estado. Entra um documento, sai uma descrição dele. Não existe nada entre uma chamada e outra que o serviço precise lembrar.

No momento em que a peça passa a expor job, URL pré-assinada e máquina de estados, ela deixa de ser uma função e vira um sistema com ciclo de vida. Com isso vêm quatro coisas que não são dela:

| O que viria junto                                                  | De quem é de verdade                                             |
| ------------------------------------------------------------------ | ---------------------------------------------------------------- |
| Estado de job, consulta de andamento, expiração                    | do fluxo que chamou, que é quem sabe o que fazer enquanto espera |
| Armazenamento do documento e do resultado                          | de quem é dono do registro, e isso é o consumidor                |
| Contrato de evento e quem assina o quê                             | do barramento da organização, não de uma peça de interpretação   |
| Prazo de retenção, expurgo e direitos do titular sobre esse acervo | de quem decidiu guardar                                          |

A restrição do enunciado é que a peça não conheça o sistema consumidor, o fluxo de negócio nem a interface que a chama. Um job é exatamente o desenho de um fluxo. Então assincronia fica fora, e quem precisa dela envolve a peça.

Envolver é barato e não exige nada do serviço: o consumidor recebe o arquivo do jeito dele, guarda onde quiser, chama a peça de dentro de uma fila, de uma máquina de estados ou de uma invocação assíncrona de função, e publica o evento que o barramento dele espera. O desenho de quem envolve está na apresentação como diagrama, e não neste repositório: é código do consumidor.

O ganho não é só conceitual. Sem armazenamento, a política de retenção do serviço cabe em uma frase verificável em teste: ele não retém. Sem isso, seriam necessários prazo, expurgo com evidência, chave por finalidade, direitos do titular sobre o acervo, residência de dado e plano de incidente sobre um acervo de dado de saúde que não precisava existir.

### O que eu assumo em troca

Duas consequências, ditas antes que perguntem.

**O tamanho do arquivo é limitado e o limite está no contrato.** Com invocação síncrona de função atrás de porta de entrada HTTP, o corpo prático fica em torno de 4 MB. Foto de celular de doze megapixels pode passar disso. A resposta é de duas partes: o contrato declara o limite e devolve erro específico acima dele, e o consumidor, que já tem o arquivo na mão, reduz antes de chamar. Se um dia o limite virar problema real, trocar a computação por container atrás de balanceador pode levantar o teto sem mudar o modelo da resposta, mas o limite publicado ainda precisa ser atualizado no contrato. O limite é consequência do tempo de execução escolhido, não do desenho.

**A latência é a que é.** O serviço declara o alvo, p50 de 8 segundos e p95 de 25. Documento que passe disso é problema de quem não quer esperar, e a solução é envolver a peça, não mudá-la.

## 4. Escopo do produto

### 4.1 Os números do problema

Premissas adotadas para tornar as decisões verificáveis. O case não fornece esses números; todos
precisam ser confirmados com a área antes de virarem compromisso de produção.

| Dado                                     | Valor                                                                    | Origem                                                            |
| ---------------------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------- |
| Volume                                   | 500 documentos por dia, cerca de 11 mil por mês útil                     | premissa de dimensionamento                                       |
| Tempo médio de análise e leitura hoje    | 15 minutos por documento                                                 | premissa para o caso de negócio                                 |
| Esforço humano equivalente               | 125 horas por dia, ou 15,6 pessoas em dedicação integral                 | calculado a partir das duas premissas acima                       |
| Tipos de maior volume                    | atestado médico e resultado de avaliação médica (deferido ou indeferido) | premissa para o recorte do MVP                                   |
| Tipo com maior ocorrência de erro humano | atestado médico                                                          | premissa para priorização                                    |
| Consumidor inicial                       | uso interno, comunidade de RH e saúde                                    | premissa de público                                            |
| Região da AWS                            | nenhuma região foi especificada no case                                  | omissão do enunciado; decisão registrada na ADR-0002            |
| Regras de negócio e normas internas      | a capacidade é exigida, mas o conteúdo corporativo não foi fornecido       | corpo sintético em `knowledge/`, marcado como fictício            |
| Distribuição entre os tipos              | 45% atestado, 25% resultado de avaliação, 30% os demais                  | premissa a confirmar com uma amostra representativa              |
| Pico                                     | até três vezes o volume médio na virada do mês                       | premissa de dimensionamento                                       |

Duas leituras que esses números permitem, e que eu levaria para a conversa antes de falar de arquitetura.

**O problema é de esforço, não de escala.** Quinze minutos por documento vezes 500 por dia dá 125 horas de trabalho humano por dia, equivalente a quase dezesseis pessoas em dedicação integral. É aí que está o valor, e não em performance.

**A escala é pequena, e isso decide arquitetura.** Quinhentos documentos por dia concentrados em oito horas dão pouco mais de um por minuto, e três por minuto num pico de três vezes. Nesse volume, fila, lote e qualquer discussão de dimensionamento são solução para problema que não existe. É o número que sustenta a decisão de manter a peça síncrona e sem estado.

### 4.2 Tipos documentais

O case sugere seis tipos para a demonstração e exige pelo menos dois estruturalmente diferentes.
A primeira versão publica dois no contrato. A escolha usa como premissa que eles são os dois de
maior volume e que o atestado concentra a maior ocorrência de erro humano; isso precisa ser validado
com dados reais.

| Tipo                          | Por que ele                                                                                                | Estrutura                                                                                                  |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Atestado médico               | por premissa, maior volume e maior erro humano; cobre texto corrido e campo numérico crítico                 | texto corrido curto, com campo numérico crítico (período de afastamento)                                   |
| Resultado de avaliação médica | por premissa, segundo maior volume; cobre protocolo e desfecho em vocabulário controlado                         | formulário de decisão, com veredito categórico (deferido ou indeferido), fundamentação e período concedido |

Os dois são estruturalmente opostos de propósito: um exige entender texto corrido, o outro exige ler campo categórico, protocolo e período em formulário. Se o mesmo desenho atende os dois sem que um vire exceção do outro, o registry por tipo está provado.

O ASO, atestado de saúde ocupacional, não está configurado nem integra o conjunto de referência. O
pipeline de recusa é testado com uma classificação nula injetada; isso prova o comportamento do serviço,
não a qualidade de classificação de um terceiro tipo. Publicar um tipo novo exige evoluir o contrato,
o enum de domínio e o catálogo, conforme a seção 9.

Uma observação sobre o resultado de avaliação médica que vale dizer em voz alta: ele traz "deferido" ou "indeferido" escrito no papel, que é um veredito de negócio. Extrair esse campo é ler o que está no documento, e isso a peça faz. Decidir o desfecho é outra coisa, e isso não é dela. A regra continua valendo: eu devolvo o que o documento diz, com evidência, e não o que deve acontecer por causa dele.

### 4.3 Formatos de arquivo

Formatos de arquivo aceitos: PDF, JPEG, PNG e HEIC. PDF nativo, PDF digitalizado, captura de tela e
foto são apresentações desses formatos, não formatos adicionais. Conteúdo manuscrito também não é
formato: a regra de roteamento o aceita como sinal, mas o pipeline atual não o detecta automaticamente;
na prática, a rota multimodal é acionada quando a confiança do OCR fica abaixo do limiar. A qualidade
é medida por formato, e o conjunto de referência atual não comprova qualidade em manuscrito.

## 5. Requisitos funcionais

Os requisitos do MVP são testáveis, e as specs nomeiam os testes que os cobrem. RF-21 pertence ao
horizonte do produto e só ganhará spec e testes quando for priorizado.

### Entrada e contrato

| ID    | Requisito                                                                                                        | Como se prova                                                                             |
| ----- | ---------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| RF-01 | Aceitar documento por `POST /v1/documents:analyze` em `multipart/form-data`, até o limite de RNF-06              | teste de contrato com os arquivos do conjunto de referência                               |
| RF-15 | Devolver erro em `application/problem+json` com código estável, conforme o catálogo do contrato                  | teste de contrato por código de erro                                                      |
| RF-16 | Degradar de forma explícita, indicando em `capabilities` o que ficou indisponível                                | teste unitário com adapter que falha                                                      |
| RF-17 | Recusar arquivo acima do limite com `invalid_input`, informando o limite no corpo do erro                        | teste de contrato com os bytes construídos: o que se prova é uma contagem                 |
| RF-18 | Ser seguro para repetição: reenviar não cria recurso nem persiste conteúdo. A resposta do modelo generativo pode variar | teste com dublês determinísticos compara duas respostas e verifica ausência de efeito colateral; produção não promete igualdade |

### Leitura e extração

| ID    | Requisito                                                                                                                                                                                     | Como se prova                                      |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| RF-02 | Normalizar o arquivo antes de qualquer decisão: converter HEIC para JPEG, corrigir rotação, contar páginas, detectar camada de texto                                                          | teste unitário por formato, sem rede               |
| RF-03 | Escolher a rota de leitura pelo sinal encontrado na normalização, nunca pela extensão do arquivo                                                                                              | teste unitário que injeta sinais e verifica a rota |
| RF-04 | Recusar antes de qualquer chamada paga documento abaixo da qualidade mínima                                                                                                                   | teste unitário com imagem degradada                |
| RF-05 | Classificar entre `medical_certificate`, `medical_assessment_result` e fora do escopo, com confiança própria                                                                                         | avaliação no conjunto de referência                |
| RF-06 | Extrair do atestado `patient_name`, `patient_document`, `leave_period`, `cid`, `doctor_name`, `crm`, `cnes` e `issue_date`                                                                            | avaliação por campo                                |
| RF-07 | Extrair do resultado `protocol_number`, `requester_name`, `requester_document`, `assessment_type`, `assessment_date`, `outcome`, `granted_period`, `doctor_name`, `crm`, `issue_date` e `cid`           | avaliação por campo                                |
| RF-08 | Devolver, por campo, o trecho literal do texto reconhecido que o originou, com a página                                                                                                       | teste unitário da verificação de evidência         |
| RF-09 | Devolver `null` com `abstained: true` e motivo quando a confiança não atingir o limiar                                                                                                        | teste unitário e caso do conjunto de referência    |
| RF-10 | Não inferir campo ausente: atestado sem CID devolve `cid` nulo; resultado sem CID devolve `cid` nulo; resultado indeferido devolve `granted_period` nulo                                             | casos correspondentes do conjunto de referência     |
| RF-11 | Validar de forma determinística as regras de integridade do documento, incluindo desfecho dentro do vocabulário controlado                                                                    | testes unitários de domínio, um por regra          |
| RF-12 | Consultar a norma interna aplicável e devolver a referência com origem e versão                                                                                                               | teste com adapter fake e um de integração          |
| RF-19 | Rasterizar PDF de mais de uma página no próprio processo e ler página a página                                                                                                                | caso `atestado_08_duas_paginas.pdf`                |

### Revisão humana e aterramento

| ID    | Requisito                                                                                                                                                                                                | Como se prova                                                                                      |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| RF-13 | Decidir revisão humana pela confiança composta, com motivos em código estável, conforme o catálogo de gatilhos da spec 0004                                                                                | teste unitário da política, um por gatilho                                                         |
| RF-14 | Devolver proveniência: id do modelo, versão do prompt, motor de OCR, versão das tabelas e horário                                                                                                        | teste de contrato                                                                                  |
| RF-20 | Rejeitar o campo cujo trecho citado não for encontrado no texto de origem, mesmo com confiança alta                                                                                                      | teste unitário com resposta de modelo contendo evidência inexistente                               |
| RF-21 | Aceitar o retorno da revisão humana e emitir apenas contador agregado por campo e veredito, sem identificar a análise e sem receber valor corrigido. **Fora do MVP e do contrato atual**; exige ADR e spec antes de entrar | futuramente, teste de contrato que rejeite valor de campo e teste que prove ausência de persistência |

### Trilha, sem conteúdo

| ID    | Requisito                                                                                                                                                                        | Como se prova                                                                  |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| RF-22 | Registrar cada análise sem nenhum conteúdo: hash SHA-256 do arquivo, chamador, horário, id do modelo, versão do prompt, rota escolhida, confiança por campo e motivos de revisão | teste que verifica o registro e que ele não contém conteúdo nem valor extraído |

## 6. Requisitos não funcionais

| ID     | Requisito                                                                | Meta                                                                                                                                                                                     |
| ------ | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| RNF-01 | Latência fim a fim                                                       | p50 de 8 s, p95 de 25 s, medidos em homologação antes de virar acordo. A linha de base manual é de 15 minutos                                                                            |
| RNF-02 | Disponibilidade do endpoint                                              | 99,5% no mês. A janela de uso é comercial, e documento não processado hoje é processado amanhã: indisponibilidade atrasa, não perde                                                      |
| RNF-03 | Custo por documento                                                      | teto de **R$ 0,50 por documento**, somando OCR, modelo e recuperação de norma. A 500 por dia, é cerca de R$ 5,5 mil por mês útil. Premissa a calibrar na primeira avaliação, não medição |
| RNF-11 | Vazão                                                                    | premissa de 500 documentos por dia, com pico de três vezes a média horária. Sem fila e sem provisionamento: é o que uma invocação síncrona por documento atende                               |
| RNF-04 | Nenhum dado sensível em log, métrica, trace ou tag                       | teste que processa documento com CPF e CID e falha se aparecer                                                                                                                           |
| RNF-05 | Nenhuma persistência de documento, de resultado ou de retorno de revisão | ausência de adapter de escrita no código, e teste que falha se um existir                                                                                                                |
| RNF-06 | Tamanho máximo do arquivo                                                | 4 MB, com erro explícito acima disso                                                                                                                                                     |
| RNF-07 | Suíte completa roda sem credencial AWS                                   | `make test` verde em máquina limpa                                                                                                                                                       |
| RNF-08 | Rede privada, sem saída para a internet                                  | premissa de implantação: nenhum teste daqui a prova, e o código não tem cliente HTTP próprio                                                                                             |
| RNF-12 | Região                                                                   | `us-east-1`, região única adotada na ADR-0002 porque o case não especifica uma. Premissa de implantação, sujeita à validação regulatória e de disponibilidade dos serviços                 |
| RNF-09 | Contrato versionado e estável                                            | teste que falha se o schema publicado regredir                                                                                                                                           |
| RNF-10 | Idioma dos documentos                                                    | português do Brasil                                                                                                                                                                      |

## 6.1 Métricas que provam que a peça funciona

O case pergunta isso de forma direta, e a resposta não pode ser "os testes passam".

| Métrica                   | Alvo inicial                                            | Por que ela                                                                  |
| ------------------------- | ------------------------------------------------------- | ---------------------------------------------------------------------------- |
| F1 por campo crítico      | ≥ 0,95 em período de afastamento e em veredito          | são os dois campos onde errar manda a decisão para o lugar errado            |
| F1 nos demais campos      | ≥ 0,90                                                  | qualidade geral da extração                                                  |
| Taxa de abstenção         | ≤ 15% dos campos, caindo com a calibração do limiar     | abstenção alta demais devolve o trabalho para a pessoa; baixa demais é chute |
| Taxa de revisão humana    | ≤ 30% dos documentos no primeiro trimestre              | é a métrica que o negócio sente, e é a que justifica o investimento          |
| Precisão da classificação | ≥ 0,98, com recusa correta do que está fora do catálogo | classificar errado contamina tudo depois                                     |
| Tempo por documento       | p95 ≤ 25 s, contra 15 minutos manuais                   | o ganho declarado                                                            |
| Custo por documento       | ≤ R$ 0,50                                               | o teto que mantém o caso de negócio de pé                                    |

Todos os alvos são premissa registrada, não medição. A primeira avaliação no conjunto de referência
vira a linha de base, e a partir dela o portão de merge bloqueia regressão acima de 2 pontos.

Uma métrica que **não** entra: taxa de acerto do negócio. Aprovar ou negar afastamento é decisão do
consumidor, e medir isso aqui seria assumir responsabilidade que o contrato recusa.

## 7. Retenção

A peça não retém. É uma frase, e ela é verificável em teste.

| O que                | Onde fica                                                               |
| -------------------- | ----------------------------------------------------------------------- |
| Documento original   | em lugar nenhum; chega na chamada, é processado em memória e descartado |
| Resultado da análise | só na resposta; quem guarda o registro é o consumidor, dono do fluxo    |
| Retorno de revisão   | não entra no MVP; se RF-21 for priorizado, vira somente métrica agregada |
| Trilha de operação   | registro sem conteúdo, com hash do arquivo, para apoiar o art. 37 da LGPD |

Isso é a leitura mais forte possível do princípio da minimização, e ela responde a restrição de dado sensível do enunciado sem precisar desenhar ciclo de expurgo, chave por finalidade e prazo de descarte para um dado que nunca existiu em disco.

Três perguntas que a decisão levanta, com a resposta pronta:

- **E se alguém contestar a análise daqui a seis meses?** O registro está no sistema consumidor, que é quem tomou a decisão. Do lado da peça ficam o hash, o id do modelo e a versão do prompt, que permitem identificar a execução e tentar refazê-la com o mesmo arquivo. Como o modelo generativo não é determinístico, isso permite auditoria e comparação, não garante reprodução idêntica. Evidência, confiança e revisão humana apoiam a análise jurídica do art. 20; não demonstram conformidade sozinhas.
- **E se o consumidor não guardar?** É cláusula de contrato: a v1 documenta que a resposta é o registro e que a peça não é fonte de consulta histórica.
- **Como detectar o mesmo atestado enviado duas vezes?** Não detecto. Devolvo o hash do arquivo na resposta para que o consumidor, que tem o histórico, compare. Duplicidade é propriedade do histórico, e o histórico não é meu.

## 8. Configuração do modelo

Modelo, prompts, parâmetros de inferência e versão do guardrail têm uma única fonte em
`config/bedrock.json`. A política aplicada pelo Bedrock tem uma única fonte em
`config/guardrails.json`. Esses arquivos explicam as escolhas que configuram; este PRD não as repete.

Garantias que dependem do serviço, e não do provedor — evidência, validação, confiança, abstenção,
revisão, proveniência e trilha sem conteúdo — permanecem nos requisitos acima e nas specs que os
implementam.

## 9. Contrato

Fonte da verdade em `contracts/v1/`, com `openapi.yaml` e `analysis_result.schema.json`. Escrito antes do código; os modelos internos derivam dele.

Regra de mudança: campo opcional novo na saída é minor. O schema atual fecha `document_type` em
dois valores, portanto tipo documental novo muda o enum publicado e exige nova versão major. Campo
obrigatório novo na entrada, campo removido, renomeado ou com tipo trocado também exigem versão major.
Prompt, modelo e limiar são invisíveis no contrato, embora mudanças neles passem pela avaliação.

O contrato não tem, de propósito: veredito de negócio, identificador de pessoa ou de processo, status de workflow, nome de sistema ou de área, e nenhuma regra de RH embutida. Se amanhã o consumidor deixar de ser RH e passar a ser sinistro, o contrato não muda.

## 10. Restrições técnicas declaradas

| Restrição                                                                                             | Consequência no código                                                                                                                                                                                                                                                        |
| ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A invocação síncrona da função aceita 6 MB de payload, e o corpo binário é codificado antes de chegar | teto de 4 MB, validado na borda antes de qualquer processamento                                                                                                                                                                                                               |
| A porta de entrada corta a integração antes do pior caso das dependências somadas                     | tempo limite da função alinhado ao da porta, em `serverless.yml`. **Pendência declarada**: um prazo por requisição, para a função desistir antes da porta, ainda exige ADR antes da implantação                                         |
| A operação síncrona do OCR lê uma página de PDF por vez, e a assíncrona exigiria armazenamento        | páginas são rasterizadas no processo e enviadas uma a uma                                                                                                                                                                                                                     |
| O Textract não aceita HEIC                                                                            | conversão para JPEG no processo, dependência empacotada na imagem                                                                                                                                                                                                             |
| A checagem contextual de aterramento do Guardrails cobre inglês, francês e espanhol                   | verificação de evidência implementada em código                                                                                                                                                                                                                               |
| Kendra está fechado para clientes novos e cobra por hora de índice provisionado, não por consulta     | acesso só pelo port `KnowledgeRetriever`. A cerca de 11 mil consultas por mês útil o custo fixo domina a conta, e o substituto está nomeado em `docs/adr/0001-recuperacao-de-conhecimento-e-o-kendra.md`                                                                      |
| O case não especifica região                                                                         | `us-east-1`, decidido em `docs/adr/0002-regiao-da-aws.md`. Isso implica transferência internacional de dado sensível e exige validação do encarregado e do jurídico antes da implantação, inclusive quanto à LGPD, à Resolução CD/ANPD 19/2024 e à Resolução CMN 4.893/2021, alterada pela 5.274/2025 |

## 11. Critérios de aceite

Portões automáticos, não checklist de revisor.

- testes unitários, de contrato e de integração passando
- cobertura do núcleo acima de 90%, sem meta para adapters
- `ruff` e verificador de tipos sem erro
- `import-linter` sem violação de camada
- avaliação sem regressão além de 2 pontos contra a baseline congelada em `evals/baseline.json`, cobrada no CI
- teste de vazamento de dado sensível em log passando
- teste que prova ausência de persistência passando
- custo médio por documento dentro do teto

## 12. Arquitetura e regras de dependência

Clean Architecture com ports e adapters. As dependências apontam para dentro.

```
src/                 não é pacote: é a raiz de código, e os pacotes de topo ficam dentro dela
  core/              regras, objetos de valor e políticas. Não importa nada de fora.
  usecases/          casos de uso e ports. Importa core.
  adapters/          aws/ e fakes/. Importa usecases e core.
  entrypoints/       http, cli e composition root. Importa tudo abaixo.
  functions/         uma pasta por função do serverless.yml. Camada mais externa.
```

Ports: `OcrPort`, `LlmPort`, `KnowledgeRetriever`, `MetricsPort`, `Clock`. `LlmPort` é um só, com duas operações, classificar e extrair: é o mesmo modelo, o mesmo guardrail e o mesmo dublê, e separar em dois ports duplicaria o adapter sem separar nada.

O catálogo não é port: é configuração lida no composition root e entregue ao domínio como dado,
em `config/catalog.json`. Campos, limiares, termos e tabelas dos tipos já publicados mudam por
configuração; o nome de um tipo novo não, porque também pertence ao contrato e ao enum de domínio.

Não existe port de armazenamento, e essa ausência é intencional: não há onde escrever. O composition root escolhe o conjunto de adapters por perfil, em `DIS_PROFILE`, com `fake` para dublês locais e `aws` para serviços reais. A diferença entre os perfis e o que cada nível de teste prova está nas seções **Estado** e **Como rodar** do `README.md`.

Componentes na nuvem: porta de entrada HTTP, uma função com o pipeline inteiro, OCR, modelo e recuperação de norma, mais observabilidade. Sem armazenamento, sem fila, sem orquestrador e sem barramento de evento. Sem dado em repouso não existe acervo do serviço, mas o tratamento transitório fora do país ainda é transferência internacional. A ADR-0002 registra a escolha técnica; o mecanismo jurídico aplicável precisa ser validado pelo encarregado e pelo jurídico antes da implantação.

**Onde mora o quê.** Este repositório é a peça de entrada e saída: recebe o arquivo, normaliza, escolhe a rota, invoca, verifica que cada valor está ancorado no documento, compõe a confiança e devolve o contrato. O conhecimento do domínio médico e o raciocínio sobre o documento não moram aqui: moram na configuração do Bedrock, que é o prompt e o schema de saída, e no índice do Kendra, que é a norma interna. Os dois evoluem sem que este código mude, e são desenhados e avaliados por conta própria. O que este repositório garante são os testes e o contrato; topologia de rede, autorizador, plano de uso e região são premissa de implantação e nenhum teste daqui as prova.

Regras cobradas pelo `import-linter` no CI:

1. `core` não importa `usecases`, `adapters`, `entrypoints`, `boto3`, `fastapi` nem `pydantic`.
2. `usecases` não importa `adapters` nem `entrypoints`.
3. `adapters` não importa `entrypoints`.
4. `boto3` só existe em `adapters/aws`.

## 13. Princípios, e o que cada um proíbe aqui

**Clean Architecture.** Proíbe import de infraestrutura no domínio. Se um teste de domínio precisar de mock de AWS, o desenho está errado.

**SOLID.** Pesa mais a inversão de dependência, que sustenta os ports, e a responsabilidade única,
que mantém a política de confiança separada da extração. Aberto e fechado aparece no pipeline:
publicar tipo documental novo exige versão de contrato, enum e catálogo, mas não reorganiza as
camadas nem altera o fluxo comum. Tabelas e regras declarativas de tipos já publicados continuam
sendo configuração.

**Núcleo funcional, e não DDD tático.** A linguagem ubíqua é a do documento, escrita em inglês conforme a seção Idioma de `AGENTS.md`; nome próprio de norma brasileira não se traduz. Objetos de valor onde eles cabem: `Confidence`, que recusa 7,2 no construtor, e `Evidence`, que recusa texto vazio e página zero.

Não há entidade, agregado nem repositório, e a ausência dos três é consequência, não lacuna: os três pressupõem estado, e este serviço não tem nenhum. Agregado existe para proteger invariante quando algo muda; aqui nada muda. Repositório recupera e persiste; aqui não há onde escrever, e essa ausência **é** a política de retenção.

Há uma segunda razão, mais específica, para período, CRM e CID **não** serem objetos de valor: eles são lidos do documento, e malformado é o caso normal — o papel tem erro de digitação, o OCR lê torto. Objeto de valor valida no construtor e levanta exceção, o que colidiria de frente com a regra 5 da `specs/0004`: validação reprovada não derruba a análise, vira motivo de revisão. `Confidence` e `Evidence` podem validar assim porque vêm do que nós computamos, onde malformado significa adapter quebrado.

A parte do DDD que mais rende aqui é a estratégica, e o PRD inteiro é feito dela: o contexto delimitado. Recusar `expected_type` na entrada, recusar devolver veredito e recusar guardar histórico são três defesas da mesma fronteira.

**DRY.** Proíbe duplicar regra de negócio. Não proíbe duplicar estrutura entre dois handlers.

**YAGNI.** Proíbe construir para o volume, o tipo ou o fluxo que ainda não existe. É ele que sustenta a decisão da seção 3.

Quando DRY e YAGNI brigam neste projeto, YAGNI ganha: com dois tipos documentais, a abstração certa aparece no terceiro, não no segundo.

## 14. Processo: SDD e TDD

### Nível de SDD adotado

Este projeto adota **spec-anchored**: a spec permanece no repositório e guia a evolução e a manutenção da fatia. Não adotamos spec-first, que descarta a spec, nem spec-as-source, em que ninguém edita o código gerado. Spec-as-source repete a rigidez do desenvolvimento dirigido por modelo e soma a ela o não determinismo do modelo de linguagem.

### Cerimônia proporcional

| Tipo de mudança                                  | O que exige                                                  |
| ------------------------------------------------ | ------------------------------------------------------------ |
| Correção de bug                                  | teste que reproduz a falha, depois a correção. Sem spec      |
| Ajuste de limiar, texto ou configuração          | o teste que cobre o comportamento. Sem spec                  |
| Fatia de funcionalidade                          | spec curta, testes a partir dela, implementação, refatoração |
| Decisão que muda contrato, dependência ou camada | ADR antes da spec                                            |
| Mudança de prompt ou de modelo                   | sem spec, com avaliação obrigatória contra a baseline        |

### O que a spec contém

Comportamento observável: entrada, saída, regras numeradas, casos do conjunto de referência que precisam passar, e o que está fora. Não contém desenho interno nem decisão técnica, que vão para a ADR. **Limite: 85 linhas**, conforme `AGENTS.md`.

### Ciclo

1. Spec em `specs/NNNN-nome.md`, a partir de `specs/TEMPLATE.md`.
2. Teste que falha, escrito a partir das regras numeradas.
3. Implementação mais simples que faz passar.
4. Refatoração com a suíte verde.
5. Revisão humana, obrigatória inclusive para código gerado por agente.

Quem escreve a spec é o desenvolvedor que vai implementar. Quem revisa responde pelo código.

### Constituição

As regras que não mudam por tarefa ficam em `AGENTS.md`. Constituição escrita é sugestão; o que vale é a cobrada, então as mesmas regras existem como `import-linter`, teste de contrato e portão de avaliação.

### Como se revisa

Revisa-se a lista de regras numeradas e a lista de nomes de teste, não a prosa. O nome do teste descreve o comportamento do código, em inglês, sem o identificador do requisito: o teste pertence ao código que ele exercita, e sobrevive à renumeração de um requisito. A ponte requisito → teste é a seção **Testes que provam a fatia** de cada spec.

### Limite conhecido

Mesmo com spec detalhada, duas execuções do agente produzem código diferente. Por isso a avaliação é portão de merge e a suíte é o contrato real entre a spec e o que roda.

Referência: memo de Birgitta Böckeler sobre ferramentas de SDD, série Exploring Gen AI, em martinfowler.com.

## 15. Riscos

| Risco                                         | Mitigação                                                                  |
| --------------------------------------------- | -------------------------------------------------------------------------- |
| Kendra fechado para clientes novos            | port isolando a troca, ADR com substituto                                  |
| Qualidade baixa em foto e manuscrito          | rota multimodal, abstenção com motivo, medição por formato                 |
| Arquivo acima do limite em foto de celular    | erro explícito com o limite no corpo, e o consumidor reduz antes de chamar |
| Documento que exceda o tempo de resposta      | alvo declarado no contrato; quem não quer esperar envolve a peça           |
| Custo acima do previsto                       | roteamento por sinal, teto no portão de avaliação                          |
| Mudança silenciosa de comportamento do modelo | id de modelo fixado e avaliação diária contra a baseline                   |
| Dado sensível em log                          | mascaramento na origem e teste que falha se vazar                          |

## 16. Fora do MVP e horizonte do produto

Ficam fora do produto por pertencerem ao consumidor: assincronia, fila, estado de job, armazenamento
do documento e do resultado e processamento em lote. O invólucro assíncrono aparece como diagrama na
apresentação, não como código deste repositório.

Ficam no horizonte do produto, mas fora do MVP: os quatro tipos adicionais sugeridos pelo case, o
retorno agregado de revisão de RF-21, cache do enriquecimento normativo, validação de CRM contra fonte
externa e painel de qualidade para o negócio. Tipo novo exige evolução do contrato; fonte externa ou
novo endpoint exige ADR antes da spec.

O case também cita sinais de adulteração e divergências frente a histórico informado. Nenhuma das duas
capacidades é prometida pelo contrato atual. Histórico exigiria nova entrada e uma decisão explícita
sobre minimização; adulteração cria inferência sobre uma pessoa. Ambas exigem ADR, avaliação jurídica
e revisão humana antes de virarem requisito funcional.

Também fica fora, como otimização e não como funcionalidade: substituir a classificação do tipo documental por um classificador customizado do Amazon Comprehend, treinado com os documentos já rotulados pela revisão humana. O gatilho é volume de rótulo, não disponibilidade do serviço.

A detecção de adulteração é a de maior valor e a de maior peso legal: cria inferência sobre uma pessoa, muda a finalidade do tratamento e encosta no art. 20 da LGPD. Ela não entra sem jurídico e comitê de risco na mesa, com revisão humana obrigatória e nenhuma ação automática sobre a pessoa.

## 17. Glossário

**Conjunto de referência com gabarito** (golden set): documentos de teste acompanhados do JSON com a resposta correta.

**Precisão**: dos campos preenchidos, quantos estavam certos. **Recall**: dos campos existentes, quantos foram preenchidos certo. **F1**: média harmônica dos dois.

**Abstenção**: devolver o campo como nulo por falta de confiança, em vez de preencher no chute.

**Evidência**: o trecho literal do texto reconhecido que originou um campo, verificado em código.

**Port e adapter**: a interface que o domínio conhece, e a implementação concreta fora dele.

**ASO**: Atestado de Saúde Ocupacional, conteúdo definido pela NR-7, item 7.5.19.1. É um dos tipos sugeridos pelo case, mas não está configurado nem presente no conjunto de referência do MVP.
