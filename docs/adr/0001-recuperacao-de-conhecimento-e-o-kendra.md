# ADR-0001, recuperação de conhecimento e o lugar do Kendra

Status: aceita · Setembro de 2026 · Decide por: RF-12, RNF-03

## Contexto

é obrigatório o uso do Amazon Kendra para recuperação de conhecimento, e exige que a
escolha seja justificada. Pontos importante:

1. O Kendra está em modo de manutenção e fechado para clientes novos. Um time que comece hoje pode
   simplesmente não conseguir provisionar um índice.
2. O Kendra cobra por **hora de índice provisionado**, não por consulta. Com 500 documentos por dia,
   cerca de 11 mil consultas por mês útil, o custo fixo do índice domina o custo por documento e vira a
   maior linha isolada da conta, mesmo se ninguém consultar nada.

O segundo ponto é o que muda o desenho. Numa peça que roda 11 mil vezes por mês, uma dependência que
cobra por existir é uma decisão econômica, não uma escolha de biblioteca.

## Decisão

O conhecimento é acessado **apenas** pelo port `KnowledgeRetriever`, que fala a linguagem do domínio e
devolve `KnowledgeReference` com origem, versão e trecho. Nenhuma camada acima dele sabe quem responde.

Por perfil:

| Perfil | Implementação                                                               | Quando                                           |
| ------ | --------------------------------------------------------------------------- | ------------------------------------------------ |
| `fake` | `FakeKnowledgeRetriever`, sobre o corpo sintético de normas em `knowledge/` | desenvolvimento, teste, avaliação e demonstração |
| `aws`  | `KendraRetriever`, via `Retrieve`                                           | quando existir índice provisionado, e apenas ali |

O substituto nomeado, caso o índice não possa ser criado, é o **Bedrock Knowledge Bases**: mesma
função, cobrança por uso e não por hora, e já dentro do serviço que o case obriga. A troca é a
implementação de um port com quatro campos, não uma migração.

## Consequências

- O MVP roda inteiro sem Kendra, e a demonstração não depende de um serviço fechado para clientes novos.
- A justificativa técnica do Kendra permanece honesta: `Retrieve` devolve trecho com origem e
  pontuação, que é exatamente o que RF-12 pede, e é isso que um índice bem alimentado entrega melhor
  que uma busca por palavra.
- O que o fake **não** prova é qualidade de ranqueamento. Isso só a conta de verdade prova, e está
  declarado em `stack.md`, seção 6.
- Se o custo fixo do índice inviabilizar a conta por documento, a troca já está desenhada e não custa
  contrato.

## Alternativas descartadas

**Embutir as normas no prompt.** Barato e sem dependência, mas o corpo normativo cresce, o contexto não
é elástico e a versão da norma deixa de ser rastreável. RF-12 exige devolver origem e versão.

**Busca própria sobre um índice local.** Traz para dentro da peça um acervo que não é dela, e a peça
não guarda nada. Contraria a seção 7 do PRD.
