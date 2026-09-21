# Índice de normas: o que entra, como entra e quem responde por ele

Este diretório é o corpus ingerido no índice do Kendra. Ele atende a capacidade **Conhecimento**:
ancorar a interpretação do documento na norma interna da instituição.

A configuração do índice está em `config/kendra.json`. O corpus está em `normas.json`. As duas
coisas são operadas por gente diferente, e essa separação é o ponto: **a área publica norma sem
passar por release deste serviço.**

---

## 1. A regra de decisão: o que parece conhecimento e não é

Quatro coisas disputam o mesmo espaço num serviço destes, e misturá-las é como ele apodrece. O
critério é uma pergunta só: **o que acontece se isso não for encontrado na hora da chamada?**

| Tipo | Mora em | Se não for encontrado |
| --- | --- | --- |
| **Norma interna** — prazo, exigência, quando pedir segunda via | índice do Kendra | a análise sai sem a referência, marcada `knowledge_enrichment: degraded`. Aceitável: é enriquecimento |
| **Tabela de valores válidos** — códigos CID, vocabulário de desfecho, formato de protocolo | `config/catalog.json` | a validação não roda. **Inaceitável**: por isso é configuração carregada, não recuperação |
| **Restrição de comportamento** — não opinar, não discriminar, não decidir | `config/guardrails.json` e o prompt | a restrição **desaparece em silêncio**. Inaceitável, e é o erro mais caro da lista |
| **Regra de negócio do processo** — quem aprova, contagem de prazo, elegibilidade | fora da peça, no consumidor | não é nosso |

Recuperação é **melhor esforço**: se a consulta não casar, o trecho não vem. Isso é tolerável para
uma norma citada como referência e intolerável para qualquer coisa que precise valer **sempre**.

É por isso que a regra de ética **não entra aqui**. "Não distinguir por gênero, idade ou condição de
saúde" tem de valer em toda chamada, inclusive naquela em que a busca por similaridade não achou
nada. Uma restrição que depende de busca vetorial é uma restrição que falha sem avisar, e falha
justamente no caso estranho, que é onde ela mais importa.

---

## 2. O corpus

`normas.json`, onze trechos, em quatro famílias e uma tabela de referência.

| Família | Cobre | Dono |
| --- | --- | --- |
| `NI-RH-014` | afastamento, prazo do INSS a partir do 16º dia, registro em prontuário | Saúde Ocupacional |
| `NI-RH-009` | **revogada**, versão anterior da NI-RH-014, com regra diferente | Saúde Ocupacional |
| `NI-SO-001` | PCMSO, tipos de exame da NR-7, retorno ao trabalho | Saúde e Segurança do Trabalho |
| `NI-RH-021` | conduta na análise de atestado: o que se confere, e o que vai para pessoa | Gestão de Pessoas |
| `NI-RH-022` | conduta na análise de resultado: a área não revisa mérito clínico | Gestão de Pessoas |
| `NI-SAU-007` | recurso de resultado indeferido, contagem do período concedido | Saúde Ocupacional |
| `TAB-CID10` | referência de capítulo do CID-10 | Saúde Ocupacional |

Cada entrada carrega `owner`, `version`, `effective_from`, `status`, `category`, `uri` e `review_by`.
**Norma sem `owner` não é ingerida**: sem dono não há quem responda pela citação que sai na resposta.

---

## 3. Como o corpus vira índice

A área publica no bucket. Cada norma são dois objetos:

```
s3://<bucket>/normas/NI-RH-014/2026-04.pdf              o documento
s3://<bucket>/metadata/normas/NI-RH-014/2026-04.pdf.metadata.json   os atributos
```

O sidecar é o que o Kendra lê para popular os atributos do índice:

```json
{
  "DocumentId": "NI-RH-014-01",
  "Title": "Norma interna de afastamento, NI-RH-014",
  "ContentType": "PDF",
  "Attributes": {
    "status": "vigente",
    "norm_id": "NI-RH-014",
    "owner": "Gerência de Saúde Ocupacional",
    "effective_from": "2026-04-01T00:00:00Z",
    "version": "2026-04",
    "category": "afastamento"
  }
}
```

Os nomes desses atributos são mapeados em `config/kendra.json`, em `data_source.FieldMappings`.
`version` cai em `_version`, que é o atributo reservado que o `KendraRetriever` lê para citar a
versão. Sem ele a resposta ainda traz a origem, e a versão sai como `unknown` em vez de ser chutada.

A sincronização é diária, às 06h UTC. Publicação urgente dispara `StartDataSourceSyncJob` à mão:
existe o caminho rápido, ele só não é o padrão.

---

## 4. Revogar uma norma

**Duas coisas, nunca uma:**

1. republicar o sidecar com `"status": "revogada"`;
2. remover o documento de `normas/`.

A remoção só vale na próxima sincronização. Entre a revogação e a sincronização existe uma janela,
e é nela que uma norma superada fundamentaria uma decisão sobre o afastamento de alguém. Quem fecha
essa janela é o `AttributeFilter` de `config/kendra.json`, que exclui `status != vigente` **na
consulta**, e não na ingestão.

A `NI-RH-009` fica no corpus revogada de propósito: é ela que torna essa regra testável.

---

## 5. Ciclo de revisão

Toda norma tem `review_by`, um ano após a publicação. Passado o prazo sem republicação, a área é
notificada e **a norma continua vigente**. Expirar automaticamente deixaria a análise sem fundamento
por esquecimento de calendário, o que é pior do que citar norma com um ano.

Norma com `effective_from` no futuro ainda não vale. Enquanto a publicação for sempre com vigência
imediata isso não é filtrado; no dia em que houver publicação antecipada, entra um
`LessThanOrEquals` sobre `effective_from` em `config/kendra.json` e a regra passa a valer sem
release.

---

## 6. Como isso vira resposta

A consulta parte dos `knowledge_terms` configurados por tipo documental em `config/catalog.json` e
é completada pelo que o documento diz: o CID, o desfecho, a duração do período. Um afastamento de
vinte dias alcança a norma do 16º dia; um resultado indeferido alcança a norma de recurso. **O
chamador nunca precisa saber disso** — quem tem a regra é o índice.

A resposta devolve `knowledge[]` com origem, versão e trecho. Sem os três, um insight é afirmação
sem fonte, e afirmação sem fonte não sobrevive a uma auditoria.

---

## 7. Procedência do conteúdo

O conteúdo é próprio da instituição. A estrutura segue o que uma norma de saúde e medicina
ocupacional de organização pública brasileira cobre. Nenhum texto normativo de terceiro é
reproduzido: citação de norma externa entra por referência, com origem e data.
