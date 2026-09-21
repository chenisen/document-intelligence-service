# 0004, validação, aterramento normativo e decisão de revisão

Status: implementada
Requisitos do PRD cobertos: RF-11, RF-12, RF-13, RF-14, RF-16
Capacidade do case: **3, Validação e insights** · **4, Conhecimento**
Fatia 5 do `PRD-MVP.md`.

## O que esta fatia entrega

O que a peça conclui **sobre** o que extraiu: coerência entre campos, a norma interna aplicável com
origem e versão, e a decisão de quando o caso precisa de uma pessoa.

Insight aqui não é opinião do modelo: é regra determinística mais norma citada. Opinião clínica é
bloqueada por guardrail, porque a peça extrai e não opina.

## Entrada

`Extraction` mais o tipo documental.

## Saída

As listas `validations` e `knowledge`, e os blocos `review`, `capabilities` e `provenance`.

## Regras

1. Toda validação é **determinística e em código**. O modelo não valida nada.
2. A **regra** é código; a **tabela** que ela lê é configuração. Fim não anterior ao início é regra;
   quais códigos CID existem, quais palavras significam deferido e como se escreve um protocolo vêm
   de `config/catalog.json`. Não há `if` por tipo documental: a regra roda quando o campo que ela
   cobre pertence ao tipo.
3. Atestado: fim não anterior ao início; dias batendo com as datas; emissão não futura; CRM no
   formato `<número>/<UF>`; CID na tabela de referência.
4. Resultado de avaliação: desfecho no vocabulário configurado; período concedido ausente quando
   indeferido; protocolo no formato configurado; avaliação não posterior à emissão.
5. Validação reprovada **não** derruba a análise: vira `status: failed` e motivo
   `validation_failed:<rule>` na revisão.
6. A norma aplicável vem pelo `KnowledgeRetriever`, com origem, versão e trecho. Sem isso, um insight
   é afirmação sem fonte. Norma revogada nunca é citada.
7. Falha do enriquecimento **degrada, não falha**: a análise volta completa com
   `capabilities.knowledge_enrichment` igual a `unavailable`.
8. Revisão humana é decidida por sete gatilhos, com motivo em código estável: confiança baixa no
   campo, campo crítico ausente, evidência inválida, validação reprovada, classificação incerta,
   guardrail acionado e qualidade marginal. Os códigos são `confidence_below_threshold:<field>`,
   `critical_field_missing:<field>`, `invalid_evidence:<field>`, `validation_failed:<rule>`,
   `uncertain_classification`, `guardrail_triggered` e `marginal_quality`. Um gatilho, um teste.
9. Toda resposta carrega `provenance`: modelo, versão do prompt, motor de OCR, versão das tabelas e
   horário. A versão do prompt tem **uma** fonte: a configuração do modelo.
10. O serviço **nunca** decide nada de negócio. Não aprova, não defere, não conclui elegibilidade.

## Casos do conjunto de referência que precisam passar

| Arquivo | Esperado |
| --- | --- |
| `atestado_08_duas_paginas.pdf` | afastamento de 15 dias aciona a norma do art. 60 da Lei 8.213/91 |
| `atestado_06_captura_tela.png` | revisão exigida por `critical_field_missing` |
| `resultado_02_indeferido_digitalizado.jpg` | validação de período concedido ausente passa |
| qualquer um, com o `KnowledgeRetriever` falhando | análise completa, `knowledge_enrichment: unavailable` |

## Fora desta fatia

Detecção de indício de adulteração, que cria inferência sobre uma pessoa e não entra sem jurídico e
comitê de risco. Divergência contra histórico, que depende de campo de entrada que o contrato não tem.

## Testes que provam a fatia

- `test_valid_canonical_medical_certificate_passes_integrity_rules`
- `test_malformed_or_inconsistent_fields_fail_without_crashing`
- `test_assessment_integrity_failures_identify_the_field`
- `test_period_days_must_be_a_positive_integer`
- `test_values_outside_the_contract_vocabulary_fail_instead_of_being_repaired`
- `test_the_rules_follow_the_configured_tables_not_a_table_in_the_code`
- `test_http_extracts_a_certificate_with_provenance_and_knowledge`
- `test_kendra_returns_the_passage_with_its_source_and_version`
- `test_a_norm_without_a_recorded_version_is_reported_as_unknown`
- `test_the_aws_profile_refuses_to_start_without_a_knowledge_index`
- `test_low_field_confidence_requires_review`
- `test_missing_critical_field_requires_review`
- `test_http_sends_a_certificate_without_crm_to_review`
- `test_invalid_evidence_requires_review`
- `test_failed_validation_requires_review`
- `test_uncertain_classification_requires_review`
- `test_triggered_guardrail_requires_review`
- `test_marginal_document_quality_requires_review`
- `test_a_failing_knowledge_adapter_degrades_instead_of_failing`
- `test_a_throttled_textract_surfaces_as_the_error_it_is`
