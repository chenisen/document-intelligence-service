# 0007, custo por documento na avaliação

Status: implementada
Requisitos do PRD cobertos: RNF-03
Capacidade do case: **métricas que provam que a peça funciona**

## O que esta fatia entrega

A avaliação no perfil `aws` passa a informar o custo variável médio por documento, calculado a partir
do consumo que cada chamada paga devolve e de uma tabela de preços versionada.

## Entrada

O consumo informado pelo provedor em cada chamada: tokens de entrada e de saída do modelo, e as
páginas lidas pelo OCR. A tabela `evals/prices.json`, com a fonte e a data de cada preço.

## Saída

`summary.mean_cost_usd` e `cost_components` no relatório da avaliação. O valor sai em dólar porque é
a moeda da tabela da AWS. A conversão para comparar com o teto de R$ 0,50 do RNF-03 usa a cotação do
dia da medição e não fica no relatório: câmbio congelado numa baseline envelhece e parece medição.

O contrato HTTP não muda. Tokens e custo não aparecem na resposta, na trilha nem em log.

## Regras

1. Cada chamada ao modelo carrega os tokens de entrada e de saída que o provedor informou na
   resposta, e a análise soma classificação e extração.
2. No perfil `aws`, o custo de um documento é tokens de entrada vezes o preço de entrada, mais tokens
   de saída vezes o preço de saída, mais páginas lidas pelo OCR vezes o preço por página.
3. `mean_cost_usd` é a média sobre os documentos analisados. Recusa fica fora do denominador, porque
   a recusa chega como erro e não devolve consumo.
4. Modelo sem preço na tabela interrompe a avaliação com erro que nomeia o modelo. Custo nunca vira
   zero por falta de preço.
5. No perfil `fake`, `mean_cost_usd` continua `null`: dublê não consome nada, e zero seria medição
   falsa.
6. O relatório declara em `cost_components` o que foi somado.

## Casos do conjunto de referência que precisam passar

Os sete arquivos do gabarito. No perfil `fake`, custo nulo em todos; no perfil `aws`, um custo por
documento analisado, que só uma conta real produz.

## Fora desta fatia

- Unidades de texto do guardrail, cobradas por política aplicada: medir exige o trace do Bedrock.
- Horas do índice do Kendra: custo fixo mensal, não custo por documento.
- Computação da função e transferência de rede.
- Consumo da extração bloqueada pelo guardrail e de documentos recusados, que chegam como erro.
- Portão de regressão de custo: sem baseline `aws` não há referência para comparar.
- Preço de fatura: a tabela é preço de lista, e desconto negociado não entra.

## Testes que provam a fatia

- `test_bedrock_reports_the_tokens_the_provider_counted`
- `test_the_analysis_adds_up_the_tokens_of_classification_and_extraction`
- `test_aws_evaluation_reports_the_mean_variable_cost_of_analysed_documents`
- `test_a_model_without_a_price_stops_the_evaluation`
- `test_fake_evaluation_is_explicitly_synthetic`
