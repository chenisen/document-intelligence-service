# ADR-0002, região da AWS

Status: aceita · Setembro de 2026 · Decide por: RNF-08, RNF-12

## Contexto

A área informou que **não há exigência de região**. Sem exigência, não há o que otimizar: escolher
região vira decisão sem critério, e decisão sem critério é melhor tomada pelo padrão.

## Decisão

**`us-east-1`, região única, em tudo.** É a região padrão da AWS, onde o catálogo de serviços é o mais
completo e onde os três serviços que a peça chama — Bedrock, Textract e Kendra — estão disponíveis.

Não é uma otimização e não precisa ser defendida como tal. É o padrão, adotado porque nada no
problema pede outra coisa.

## Consequências

- **Existe transferência internacional de dado pessoal sensível, e ela é declarada.** A peça processa
  dado de saúde, e processar é tratar. A base legal está no art. 33 da LGPD, na hipótese de
  cumprimento de obrigação legal e regulatória do empregador, com salvaguarda contratual junto ao
  provedor. Isso entra no inventário de tratamento e no relatório de impacto dos arts. 37 e 38.
- **A regulação do Banco Central entra na conversa.** A Resolução CMN 4.893/2021 exige requisitos de
  contrato, verificação do país onde os serviços são prestados e comunicação prévia ao BCB. É
  trabalho de riscos e jurídico, e começa no discovery.
- **Registro de invocação de modelo desligado no provedor**, o que reduz o que atravessa a fronteira
  ao mínimo necessário para a resposta.
- **Nenhum dado em repouso**, em região nenhuma, porque a peça não guarda nada. É o que mantém a
  conversa restrita a tratamento transitório.
- Região única, sem réplica. Com disponibilidade de 99,5% e janela de uso comercial, documento não
  processado hoje é processado amanhã: indisponibilidade atrasa, não perde.

## Quando isso é reaberto

**Se a residência no Brasil virar exigência.** Aí a decisão deixa de ser padrão e passa a ter
critério, e duas coisas mudam: o armazenamento, quando existir, e a disponibilidade dos serviços
chamados — o Kendra, em particular, precisa ser verificado na lista de regiões antes de qualquer
promessa, e a ADR-0001 já nomeia o substituto atrás do port `KnowledgeRetriever` caso ele não esteja
onde for preciso.

Enquanto a exigência não existir, região é configuração: `${opt:region, "us-east-1"}` no
`serverless.yml`, e o padrão vale.
