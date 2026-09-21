# Case Técnico, Tech Lead: Peça de Interpretação de Documentos Médicos

Processo Seletivo · Tech Lead · Plataforma de Inteligência Documental

|                      |                        |
| -------------------- | ---------------------- |
| Apresentação pessoal | 15 min                 |
| Case e perguntas     | 1h15                   |
| Linguagem            | Python                 |
| Nuvem                | AWS (Bedrock · Kendra) |

---

## 01 · Contexto

### Por que esse desafio existe

Processos de afastamento e licença médica dependem do recebimento e da leitura de um volume relevante de documentos todos os meses: atestados, laudos, relatórios médicos, exames ocupacionais, requerimentos e comprovantes previdenciários. Esses documentos chegam em formatos radicalmente heterogêneos: PDFs nativos, fotos tiradas de celular, digitalizações tortas, textos manuscritos e capturas de tela.

Cenários tradicionais resolvem isso com OCR baseado em regras rígidas, complementado por conferência manual. O resultado é conhecido: baixa cobertura de tipos documentais, retrabalho, erro humano em campos críticos e uma janela de risco que só é percebida depois do fato.

> **O problema a resolver:** não queremos mais um OCR acoplado a uma tela. Queremos uma **peça técnica desacoplada e reutilizável por toda a jornada**, capaz de interpretar qualquer tipo de documento médico e devolver **dados estruturados e insights confiáveis**, com nível de confiança explícito e rastreabilidade completa.

---

## 02 · Desafio

### O que você deve projetar e construir

Projete e implemente o **Document Intelligence Service**: um componente independente, com contrato próprio, consumível por múltiplos produtos e fluxos sem nenhum acoplamento a tela, banco de dados ou processo específico.

| Capacidade                  | O que é                                                                                                                                                                           |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1. Classificação**        | Identificar automaticamente o tipo do documento recebido, sem que o chamador precise informá-lo.                                                                                  |
| **2. Extração estruturada** | Devolver um payload tipado (datas, período de afastamento, códigos de diagnóstico, identificação do profissional emissor, números de protocolo) com score de confiança por campo. |
| **3. Validação e insights** | Coerência entre campos, plausibilidade do conteúdo, sinais de adulteração e divergências frente ao histórico informado.                                                           |
| **4. Conhecimento**         | Ancorar a interpretação em uma base de conhecimento corporativa (regras de negócio, normas internas, tabelas de referência).                                                      |

### Restrições obrigatórias

- **Linguagem:** Python. Testes automatizados são parte da entrega, não um extra.
- **Nuvem:** AWS. O uso de **Amazon Bedrock** (interpretação e raciocínio sobre o documento) e **Amazon Kendra** (recuperação de conhecimento) é obrigatório e deve ser _justificado_. Demais serviços são de escolha livre, e cada decisão precisa de defesa técnica.
- **Desacoplamento:** a peça não pode conhecer o sistema consumidor, o fluxo de negócio nem a interface que a chama. Contrato de entrada e saída estável e versionado.
- **Dado sensível:** você está lidando com dado de saúde. LGPD, minimização, segregação de acesso e política de retenção precisam estar desenhados, não citados en passant.

---

## 03 · Entregáveis

### O que esperamos ver na apresentação

| Entregável                              | Descrição                                                                                                                                                                                                                             |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1. Visão de produto e problema**      | Como você enxerga o problema, quais hipóteses assumiu, o que está dentro e fora do escopo do MVP e por quê. Quais métricas provam que a peça funciona.                                                                                |
| **2. Arquitetura da solução**           | Diagrama de componentes e de fluxo (síncrono e assíncrono), decisões e trade-offs explícitos, pontos de falha e estratégia de resiliência. Onde entra cada serviço e por quê.                                                         |
| **3. Contrato da peça**                 | Especificação de entrada e saída (API ou SDK), modelo de erros, idempotência, versionamento e estratégia de evolução sem quebrar consumidores.                                                                                        |
| **4. Ciclo completo de SDLC**           | Da ideia à operação: discovery técnico, definição de pronto, branching, code review, testes (unitário, integração, contrato e avaliação do modelo), CI/CD, estratégia de ambientes, rollout, rollback, observabilidade e sustentação. |
| **5. MVP funcional**                    | Código executável em Python que demonstre o fluxo ponta a ponta com pelo menos **dois tipos documentais distintos**. Mocks e stubs para os serviços de nuvem são permitidos: avaliamos o design do código, não o acesso a uma conta.  |
| **6. Segurança, LGPD e IA responsável** | Tratamento de dado sensível de saúde, guardrails do modelo, mitigação de alucinação, quando o humano entra no fluxo e como isso é comprovado para auditoria.                                                                          |
| **7. Liderança técnica**                | Como você quebraria isso em histórias, sequenciaria as entregas, distribuiria entre perfis de senioridade distintos, mediria progresso e conduziria as decisões técnicas com o time e com os stakeholders de negócio.                 |

---

## 04 · Escopo sugerido

### Tipos documentais para a demonstração

Escolha ao menos dois tipos com estruturas realmente diferentes entre si. A graça do desafio está justamente em lidar com a heterogeneidade.

- Atestado médico
- Laudo ou relatório médico
- Exame ocupacional (apto / inapto)
- Requerimento de benefício previdenciário
- Resultado de avaliação médica (deferido / indeferido)
- Receituário

> **Sobre os dados:** utilize exclusivamente documentos **sintéticos ou públicos** gerados por você. Não utilize nenhum documento real de terceiros e não é necessário, nem esperado, acesso a qualquer dado corporativo.

---

## 05 · Formato do encontro

### 1h30 no total

| Tempo      | Etapa                          | Conteúdo                                                                                                                         |
| ---------- | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| 15 minutos | **Apresentação pessoal**       | Sua trajetória, os desafios técnicos mais relevantes que você já liderou, como você atua como liderança técnica e o que te move. |
| 45 minutos | **Apresentação do case**       | Contexto, arquitetura, SDLC e demonstração do MVP funcional, com o código aberto na tela.                                        |
| 30 minutos | **Perguntas e aprofundamento** | Discussão técnica aberta, cenários alternativos e decisões sob restrição.                                                        |

### Como entregar

- Apresentação em **PDF ou PPT**, sem limite de slides, mas priorizando densidade sobre volume.
- Código do MVP em **repositório público** (GitHub ou GitLab) ou arquivo compactado, com `README` explicando como executar.
- Envio até **24h antes** do horário agendado.
- Trazer o ambiente pronto para rodar a demo ao vivo, ou uma gravação curta, caso prefira eliminar o risco de ambiente.

---

## 06 · Recado final

### O que este case realmente avalia

Este é um desafio deliberadamente amplo e ambíguo, porque é exatamente assim que os problemas chegam para uma liderança técnica. Não esperamos que você resolva tudo em 45 minutos. Esperamos ver **como você pensa, onde você corta escopo, o que você prioriza e como você defende as suas escolhas**.

Se algum ponto do enunciado parecer aberto demais, essa é a intenção: tome a decisão, registre a premissa e siga em frente.

---

_Case Técnico, Liderança Técnica · Plataforma de Inteligência Documental. Em caso de dúvida sobre o enunciado, escreva para o contato do processo seletivo; perguntar é bem-visto._
