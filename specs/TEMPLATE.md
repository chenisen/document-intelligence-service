# NNNN, <nome da fatia>

Status: rascunho | aprovada | implementada
Requisitos do PRD cobertos: RF-XX, RNF-XX

> Limite: 85 linhas, cobrado por teste. Estourar significa que a spec juntou requisitos demais:
> quebre em duas, em vez de comprimir a tabela de casos ou a lista de testes.
> Esta spec descreve comportamento observável. Decisão técnica vai para uma ADR.

## O que esta fatia entrega

Uma frase. O que passa a funcionar depois dela.

## Entrada

O que chega, em que formato, com que restrição.

## Saída

O que sai, com o trecho do contrato afetado.

## Regras

Lista numerada, cada regra testável de forma isolada. É esta lista que se revisa.

## Casos do conjunto de referência que precisam passar

Arquivos de `samples/` e o resultado esperado de cada um.

## Fora desta fatia

O que explicitamente não entra.

## Testes que provam a fatia

Um por regra, no formato `test_rfXX_<behavior>`, com o comportamento em inglês. É esta lista que se revisa junto com as regras.
