# 0005, trilha e ausência de retenção

Status: implementada
Requisitos do PRD cobertos: RF-18, RF-22, RNF-04, RNF-05
Capacidade do case: **6, segurança, LGPD e IA responsável**
Fatia 6 do `PRD-MVP.md`.

## O que esta fatia entrega

Cada chamada deixa uma trilha sem conteúdo, e a peça prova que não guarda nada.

## Entrada

Documento pelo endpoint existente.

## Saída

Análise no contrato existente. A trilha contém apenas metadados operacionais permitidos, e nenhum
arquivo é escrito em lugar nenhum.

## Regras

1. Toda análise registra hash, chamador autenticado (ou `local` na demonstração), horário, modelo,
   prompt, rota, confiança por campo, motivos de revisão e resultado da operação.
2. Documento, valores extraídos, evidências e mensagens de exceções externas nunca entram em log,
   métrica ou trace. Erro inesperado devolve mensagem genérica.
3. Upload e processamento não escrevem arquivos, inclusive quando a entrada é recusada. Nenhum
   adapter do serviço oferece escrita de documento ou de resultado, e uma varredura do código prova
   essa ausência.
4. A emissão de métrica é a exceção declarada da regra 3: ela é emissão e não armazenamento, porque
   nada do que sai por ali é legível de volta pelo serviço.
5. Repetir a análise com os mesmos dublês produz a mesma resposta, salvo proveniência.

## Casos do conjunto de referência que precisam passar

`atestado_01_pdf_nativo.pdf`: trilha sem nome, CPF, CID nem evidência.
Arquivo acima do limite: recusa sem arquivo temporário em disco.

## Fora desta fatia

Autorizador e implantação AWS. O retorno da revisão humana, RF-21, que saiu do MVP com o motivo
escrito em `PRD-MVP.md` §3: ele não é nenhuma das quatro capacidades do enunciado e atende uma
calibração que ainda não acontece.

## Testes que provam a fatia

- `test_analysis_emits_only_allowed_audit_metadata`
- `test_failures_do_not_leak_document_content`
- `test_upload_never_rolls_to_disk`
- `test_service_has_no_document_writing_adapter`
- `test_repeated_analysis_has_the_same_result`
- `test_http_extracts_a_certificate_with_provenance_and_knowledge`
