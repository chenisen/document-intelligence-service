# 0002, classificação do tipo documental

Status: implementada
Requisitos do PRD cobertos: RF-05, RF-15
Capacidade do case: **1, Classificação**
Fatia 2 do `PRD-MVP.md`.

## O que esta fatia entrega

O serviço identifica sozinho o tipo do documento, sem o chamador informar, e recusa o que está fora do
catálogo em vez de tentar extrair campos que o documento não tem.

## Entrada

`NormalizedDocument` mais o texto reconhecido ou as páginas, conforme a rota escolhida na fatia 1.

## Saída

`Classification`, com `document_type` entre `medical_certificate`, `medical_assessment_result` e
`None`, mais a confiança própria da classificação.

## Regras

1. O chamador nunca informa o tipo. Não existe campo de entrada para isso no contrato.
2. A classificação usa o `LlmPort`, com saída estruturada por schema: o modelo escolhe entre os tipos
   do registry e `unsupported`, e nada fora dessa lista é aceito.
3. Confiança da classificação abaixo de **0,80** adiciona o motivo `uncertain_classification` e manda
   o caso para revisão humana, mas **não** derruba a análise.
4. `document_type` igual a `None` devolve erro `unsupported_document_type`, com status 422, e nenhuma
   extração é tentada.
5. Documento médico legítimo fora do catálogo é recusado igual a qualquer outro: ASO, laudo e
   solicitação de exames não têm tratamento especial.
6. A classificação acontece **uma vez por documento**, não por página.

## Casos do conjunto de referência que precisam passar

| Arquivo | Esperado |
| --- | --- |
| os cinco `atestado_*` | `medical_certificate` |
| os dois `resultado_*` | `medical_assessment_result` |

**Não há documento fora do catálogo no conjunto**, e a recusa é provada sem um. O gerador produz
apenas os dois tipos do MVP, e no perfil `fake` um terceiro tipo nunca provou classificação: o
dublê devolvia `document_type: null` porque o gabarito mandava. O que aquilo provava — que o
pipeline recusa quando a classificação não reconhece o documento — está provado direto, injetando um
modelo que devolve nulo. Qualidade de classificação só a avaliação contra conta real prova.

## Fora desta fatia

Extração de campo, validação, enriquecimento e trilha.

## Testes que provam a fatia

- `test_http_refuses_a_document_outside_the_catalogue`
- `test_the_caller_cannot_inform_the_document_type`
- `test_bedrock_classifies_through_a_tool_schema_that_only_allows_known_types`
- `test_bedrock_returns_no_type_when_the_document_is_outside_the_catalogue`
- `test_the_tool_schema_offers_exactly_the_configured_types`
- `test_the_shipped_catalogue_covers_the_two_mvp_types`
- `test_upstream_errors_are_mapped_without_their_messages`
