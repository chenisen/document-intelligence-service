# 0001, normalização e roteamento de leitura

Status: implementada
Requisitos do PRD cobertos: RF-02, RF-03, RF-04, RF-19
Capacidade do case: **leitura, antes de qualquer capacidade**
Fatia 1 do `PRD-MVP.md`.

## O que esta fatia entrega

Receber qualquer formato aceito, normalizar o arquivo e decidir a rota de leitura pelo sinal do
conteúdo, sem ainda classificar nem extrair.

## Entrada

Arquivo binário em PDF, JPEG, PNG ou HEIC. O limite de 4 MB é cobrado na borda, na fatia 0.

## Saída

`NormalizedDocument`: formato de origem, número de páginas, camada de texto válida, indício de
manuscrito, altura mínima de texto, maior lado em pixels, e a rota entre `direct_text`, `ocr`,
`multimodal` e `reject`.

## Regras

1. HEIC é convertido para JPEG antes de qualquer leitura.
2. A rotação é corrigida antes da avaliação de qualidade.
3. A camada de texto de um PDF é válida quando **toda** página extrai pelo menos **150 caracteres**.
   Por página e não por média: um PDF de duas com a segunda digitalizada passaria na média e falharia
   na leitura.
4. PDF sem camada de texto válida, e qualquer imagem, escolhe `ocr`.
5. Indício de manuscrito roteia para `multimodal` sem passar pelo OCR.
6. Depois do OCR, confiança abaixo de **80 em 100** re-roteia a página para `multimodal`. **Uma
   tentativa só**: a página foi lida duas vezes e custa duas leituras, e não existe terceira.
7. Altura de texto abaixo de **15 pixels**, ou maior lado acima de **10.000 pixels**, escolhe
   `reject` com `document_quality_too_low`, antes de qualquer chamada paga.
8. A extensão do arquivo nunca decide a rota: ela não é parâmetro da função de roteamento.
9. PDF de mais de uma página é rasterizado página a página, porque o OCR síncrono lê uma por chamada.

## Casos do conjunto de referência que precisam passar

Recusa por tipo documental é da fatia 2: aqui todo documento legível é roteado.

| Arquivo | Rota esperada |
| --- | --- |
| `atestado_01_pdf_nativo.pdf` | `direct_text`, e o OCR não é chamado |
| `atestado_02_pdf_digitalizado.pdf` | `ocr`, embora seja PDF: a extensão não decide |
| `atestado_06_captura_tela.png` | `ocr` |
| `atestado_07_foto.heic` | `ocr`, depois da conversão para JPEG |
| `atestado_08_duas_paginas.pdf` | `direct_text`, com duas páginas contadas |
| `resultado_01_pdf_nativo.pdf` | `direct_text` |
| `resultado_02_indeferido_digitalizado.jpg` | `ocr` |

Os dois primeiros provam o ponto: mesmo formato, rotas diferentes, porque decide o sinal.

Duas ausências declaradas. Arquivo acima do limite é recusado na borda pela spec 0000, com
`invalid_input`, antes de existir `NormalizedDocument`: tamanho e qualidade são erros diferentes. E a
rota `multimodal` por manuscrito está implementada e testada, mas **nenhum caminho do serviço liga
esse sinal hoje**; na prática chega-se a ela pelo re-roteamento da regra 6.

## Fora desta fatia

Classificação, extração, chamada ao modelo e ao conhecimento. Recusa por tamanho é da fatia 0, recusa
por tipo é da fatia 2.

## Testes que provam a fatia

- `test_converts_heic_to_jpeg`
- `test_fixes_rotation_before_quality_assessment`
- `test_counts_pages_of_a_multipage_pdf`
- `test_pdf_with_text_layer_chooses_direct_text`
- `test_scanned_pdf_chooses_ocr`
- `test_a_single_scanned_page_invalidates_the_whole_text_layer`
- `test_handwriting_signal_chooses_multimodal`
- `test_low_ocr_confidence_reroutes_to_multimodal_once`
- `test_file_extension_alone_does_not_decide_the_route`
- `test_rejects_below_the_minimum_text_height`
- `test_rejects_above_the_maximum_side_length`
- `test_rasterises_a_multipage_pdf_page_by_page`
- `test_a_pdf_with_a_text_layer_never_calls_the_ocr`
