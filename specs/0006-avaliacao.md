# 0006, avaliação e portão de regressão

Status: implementada
Requisitos do PRD cobertos: RF-05, RF-06, RF-07, RF-09, RF-10, RNF-04, RNF-07; §6.1 e §11
Capacidade do case: **métricas que provam que a peça funciona**
Fatia 7 do `PRD-MVP.md`.

## O que esta fatia entrega

Execução dos dezessete casos com métricas por campo e formato, relatório HTML e comparação contra
baseline compatível, sem confundir stubs do conjunto de referência com qualidade real do modelo.

## Entrada

Arquivos e gabarito de `samples/`, perfil explícito e baseline opcional da mesma modalidade.

## Saída

Resumo numérico JSON, relatório HTML e código de saída diferente de zero quando houver regressão.
Artefatos de avaliação não contêm documento, evidência nem valores esperados ou extraídos.

## Regras

1. Todos os casos são executados;
   classificação e recusas são medidas separadamente, e taxa sem denominador é `null`, não 1,0.
   Erro inesperado prejudica as métricas.
2. Precisão, recall, F1, acurácia e abstenção são calculados por campo e formato. Valor errado conta
   como falso positivo e, se havia valor esperado, falso negativo. Nulo esperado não infla F1;
   campo omitido não equivale a nulo correto. Abstenção é medida pelo indicador explícito.
3. O gabarito português é convertido para o vocabulário do contrato, inclusive períodos e CRM.
   A comparação de texto ignora somente caixa, acento e espaços; não adivinha valores ausentes.
4. O perfil fake é rotulado como regressão sintética de integração, sem prova de qualidade, custo ou
   latência AWS. Modelo e versão de prompt são identificados; custo não medido permanece nulo.
5. Queda superior a 2 pontos percentuais em precisão, recall, F1 ou acurácia, ou aumento superior a
   2 pontos em abstenção, omissão ou revisão, reprova a comparação. Exatos 2 pontos são aceitos.
6. Baselines incompatíveis, casos ou campos perdidos, mudança de formato ou conjunto de referência
   e perda de métrica reprovam; números fake e AWS nunca são comparados como equivalentes.
7. JSON e HTML contêm apenas métricas e metadados de avaliação, incluindo nomes dos arquivos;
   texto exibido no HTML é escapado e nenhum valor extraído ou evidência é persistido.

## Casos do conjunto de referência que precisam passar

Os sete arquivos do gabarito, dos dois tipos do MVP.

## Fora desta fatia

Chamadas reais AWS durante testes, gravação de dublês, preço estimado apresentado como medição e
comprovação de metas estatísticas com respostas geradas do próprio gabarito.

## Testes que provam a fatia

- `test_evaluation_counts_classification_and_refusals`
- `test_evaluation_scores_fields_and_formats_without_null_inflation`
- `test_evaluation_translates_golden_fields_to_contract_values`
- `test_fake_evaluation_is_explicitly_synthetic`
- `test_regression_gate_handles_metric_direction_and_two_point_boundary`
- `test_regression_gate_rejects_lost_cases_fields_formats_and_modalities`
- `test_evaluation_reports_never_include_extracted_values`
