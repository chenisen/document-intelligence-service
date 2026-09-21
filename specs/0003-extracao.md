# 0003, extração estruturada com evidência

Status: implementada
Requisitos do PRD cobertos: RF-06, RF-07, RF-08, RF-09, RF-10, RF-20
Capacidade do case: **2, Extração estruturada**
Fatias 3 e 4 do `PRD-MVP.md`.

## O que esta fatia entrega

Os campos do tipo identificado, cada um com o trecho literal que o originou, a página e um grau de
confiança. Campo sem confiança suficiente volta nulo com motivo, em vez de preenchido no chute.

## Entrada

`Classification` mais o texto reconhecido e as páginas.

## Saída

`Extraction`, com um `ExtractedField` por campo do catálogo daquele tipo, conforme
`contracts/v1/openapi.yaml`.

## Regras

1. O catálogo de campos é por tipo documental e vive no contrato. Tipo novo entra como handler novo no
   registry, sem tocar em nenhuma camada.
2. Todo campo preenchido **precisa** citar evidência: o trecho literal e a página.
3. A evidência é verificada **em código** contra o texto reconhecido, com comparação insensível a
   caixa, acento e espaço repetido. Trecho que não existe derruba o campo, mesmo com confiança alta,
   e o motivo é `invalid_evidence`.
4. Campo ausente do documento volta `null` com `absent_from_document`. **Nunca inferido.** Atestado sem
   CID devolve CID nulo; resultado indeferido devolve período concedido nulo.
5. A confiança do campo é composta: a do OCR daquela página, a do modelo para aquele campo, e o
   resultado das validações. A composição é uma função pura, num lugar só.
6. Confiança abaixo do limiar devolve `null` com `confidence_below_threshold`. O limiar é **0,90 para
   campo crítico** e **0,70 para o resto**.
7. Campos críticos: `leave_period` e `crm` no atestado, `outcome` no resultado de avaliação. Neles
   vale precisão acima de recall: abster manda para revisão, errar manda a decisão para o lugar
   errado. Atestado sem CRM não identifica quem o emitiu, e por isso vai para uma pessoa.
8. O modelo nunca é chamado mais de uma vez por documento para extrair.

## Casos do conjunto de referência que precisam passar

| Arquivo | Esperado |
| --- | --- |
| `atestado_01_pdf_nativo.pdf` | oito campos preenchidos com evidência |
| `atestado_06_captura_tela.png` | `crm` e `cnes` nulos: o bloco do médico está cortado |
| `atestado_08_duas_paginas.pdf` | `cid` nulo, não inferido |
| `resultado_02_indeferido_digitalizado.jpg` | `outcome` igual a `denied`, `granted_period` nulo |
| `resultado_01_pdf_nativo.pdf` | `outcome` igual a `granted`, com `granted_period` preenchido |

## Fora desta fatia

Validação determinística, política de revisão, enriquecimento normativo e trilha.

## Testes que provam a fatia

- `test_http_extracts_a_certificate_with_provenance_and_knowledge`
- `test_http_extracts_denial_without_inventing_a_granted_period`
- `test_bedrock_extraction_carries_the_excerpt_and_the_page_of_every_value`
- `test_evidence_is_checked_on_its_page_ignoring_case_accents_and_whitespace`
- `test_evidence_on_another_or_missing_page_drops_the_field`
- `test_missing_fabricated_or_empty_folded_evidence_drops_the_field`
- `test_critical_and_regular_fields_use_their_threshold`
- `test_confidence_combines_ocr_model_and_validation`
- `test_failed_validation_abstains_with_its_own_reason`
- `test_absent_fields_stay_null_without_guessing_or_abstention`
