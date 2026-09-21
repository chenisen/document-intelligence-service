# Regras deste repositório

Este arquivo vale para qualquer agente de codificação.

Leia o `docs/PRD.md` antes de qualquer tarefa. Nenhum código nasce sem estar amarrado a um requisito do PRD ou a uma
spec em `specs/`.

Antes de escrever código, leia também `docs/stack.md`, que diz o que já é dependência e o que foi
recusado. A unidade de trabalho é a fatia, e a fatia é a spec: não há lista de tarefas paralela ao
`specs/`. Dependência nova exige ADR.

Este arquivo é a constituição do repositório: são as regras que não mudam por tarefa.

## Cerimônia proporcional

Antes de propor qualquer coisa, classifique a mudança:

| Mudança                                                                            | O que fazer                                                     |
| ---------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| Correção de bug                                                                    | teste que reproduz a falha, depois a correção. Não escreva spec |
| Ajuste de limiar, texto ou configuração                                            | só o teste que cobre o comportamento. Não escreva spec          |
| Fatia de funcionalidade                                                            | spec em `specs/`, depois testes, depois implementação           |
| Mudança de contrato, de dependência, de camada ou qualquer coisa que guarde estado | pare e peça uma ADR antes                                       |
| Mudança de prompt ou de modelo                                                     | sem spec, mas rode a avaliação e compare com a baseline         |

Não aplique o fluxo completo a tudo. Documento demais para mudança de menos faz o time abandonar o processo.

## Ordem obrigatória para fatia de funcionalidade

1. Spec em `specs/NNNN-nome.md`, a partir de `specs/TEMPLATE.md`, em **no máximo 85 linhas**.

    O número existe porque "uma página" não é verificável e ninguém mede. Estourar o limite não é
    permissão para comprimir a tabela de casos nem a lista de testes: as duas são a superfície de
    revisão. É sinal de que a spec juntou requisitos demais, e a correção é **quebrar em duas**. O
    limite é cobrado em revisão: a suíte de testes testa o código, não o texto deste repositório.

2. Teste que falha, escrito a partir das regras numeradas da spec.
3. Implementação mais simples que faz passar.
4. Refatoração com a suíte verde.

Não pule etapa. Não escreva implementação antes do teste. Não escreva teste que já nasce passando.

A spec descreve comportamento observável. Ela não descreve nome de classe, estrutura de módulo nem
decisão técnica: isso vai para uma ADR em `docs/adr/`.

## Código óbvio

Este código é lido em voz alta: em revisão, em apresentação e por quem entra no time depois. Entre
duas soluções que funcionam, vale a que se explica em uma frase.

- port é classe base abstrata com `abc.ABC` e `@abstractmethod`, não `Protocol`
- objeto de valor é `@dataclass(frozen=True)`
- sem estado, é função, não classe
- sem metaclasse, sem decorator próprio, sem `__getattr__`, sem genérico parametrizado
- sem `async`: o pipeline é sequencial e a invocação é síncrona
- biblioteca conhecida acima de biblioteca menor, mesmo custando uma dependência a mais

Dependência que obriga a explicar o funcionamento interno dela para explicar o nosso código é a
dependência errada. Truque de linguagem que economiza cinco linhas e custa um parágrafo de explicação
é prejuízo.

## Idioma

**Código e nome de arquivo em inglês. Documentação em português.**

| O que                                                       | Idioma    |
| ----------------------------------------------------------- | --------- |
| Nome de módulo, pacote, classe, função, variável, constante | inglês    |
| Nome de arquivo de código e de teste                        | inglês    |
| Comentário, docstring e mensagem de log                     | inglês    |
| Campo do contrato, código de erro, motivo de revisão        | inglês    |
| PRD, spec, ADR, task, README e demais documentos            | português |
| Mensagem de commit e descrição de PR                        | português |

**A exceção são os nomes próprios da norma brasileira**, que não têm equivalente e não se traduzem:
`aso`, `cid`, `crm`, `cnes`, `nr7`, `cpf`, `cnpj`. `ASO` traduzido vira um documento que ninguém
reconhece, e o objetivo do nome é ser reconhecido.

Tudo o mais vai para inglês: `medical_certificate`, `leave_period`, `issue_date`, `patient_name`,
`issuing_doctor`, `confidence`, `evidence`, `abstained`.

O nome do teste descreve o comportamento do código em inglês, e nada além disso:
`test_http_extracts_the_certificate_instead_of_a_placeholder`.

O documento lido continua sendo em português, e isso não muda: o que está em inglês é o código que
o lê, não o conteúdo que ele lê. Prompt e tabela de valores válidos são conteúdo, não código.

## Camadas e dependências

```
core          regras puras. Não importa nada de fora.
usecases      casos de uso e ports. Importa core.
adapters      aws/ e fakes/. Importa usecases e core.
entrypoints   http, cli, bootstrap. Importa tudo abaixo.
functions     uma pasta por função do serverless.yml. É a camada mais externa.
```

Proibido:

- importar `boto3`, `fastapi` ou `pydantic` dentro de `core`
- importar `adapters` dentro de `usecases`
- instanciar adapter fora de `entrypoints/bootstrap.py`
- usar `boto3` fora de `adapters/aws`

O `import-linter` roda no CI e quebra a build nessas violações.

## Ambiente

Dois perfis, escolhidos em `DIS_PROFILE` pelo composition root: `fake` (memória e cassetes gravados) e
`aws` (tudo real). Detalhe em `docs/stack.md`, seção 6.

Nunca chame AWS de verdade em teste unitário. Nunca use resposta fictícia de emulador para medir
qualidade de extração: para isso existem os cassetes e a avaliação.

## Testes

Teste automatizado é parte da entrega, não um extra. Nenhuma mudança de comportamento entra sem
teste: a tabela de cerimônia proporcional diz **qual** teste cada mudança pede, nunca **se** pede.
Código sem teste não é código pela metade, é comportamento que ninguém prometeu.

A suíte testa o código. Não testa markdown, YAML nem a coerência de um documento com outro: isso é
trabalho de revisão, e teste que lê texto passa a falhar por motivo que não é defeito.

- teste unitário não faz rede e não usa credencial
- chamada a serviço da AWS é testada com resposta gravada, nunca com serviço real
- o caminho que sobe é testado pela porta que sobe: o handler do Lambda recebe evento do API
  Gateway, não uma chamada ASGI. A tradução entre os dois é código e já escondeu defeito
- modelo generativo não entra em teste unitário: use o fake do `LlmPort`
- o nome do teste diz o que o código faz, não qual requisito ele atende. Nada de `rf06` no nome:
  identificador envelhece, é renumerado e some quando o requisito muda de lugar, e o comportamento
  não. A rastreabilidade requisito → teste mora na seção **Testes que provam a fatia** da spec, que
  é onde alguém vai procurar por ela

## Armazenamento

Não existe. A peça não guarda documento, nem resultado, nem retorno de revisão, em lugar nenhum.

Não há port de armazenamento, e essa ausência é intencional. Se você sentir falta de um, pare: ou a
tarefa está pedindo algo que é do consumidor, ou precisa de uma ADR antes.

A única coisa registrada é a trilha da operação, sem conteúdo e sem valor extraído: hash do arquivo,
chamador, horário, modelo, versão do prompt, rota escolhida, confiança por campo e motivos de revisão.

Assincronia, fila e estado de job são do consumidor. O desenho de quem envolve a peça é diagrama na
apresentação, não código deste repositório.

## Domínio

A linguagem ubíqua é a do documento, expressa em inglês, conforme a seção Idioma: `medical_certificate`,
`aso`, `leave_period`, `crm`, `conclusion`, `evidence`, `confidence`. Um conceito, um nome, o mesmo em
todo lugar: contrato, domínio, teste e métrica.

Campo sem confiança suficiente volta `None` com motivo. Nunca preencha no chute. Nunca infira campo
que não está escrito no documento.

## O que não fazer

- não crie abstração para dois casos: espere o terceiro
- não adicione serviço da AWS que o PRD não lista
- não persista documento, resultado nem retorno de revisão em lugar nenhum
- não crie tabela, bucket, fila ou máquina de estados dentro do serviço
- não escreva conteúdo de documento na trilha: só hash, chamador, horário, modelo e confiança
- não escreva regra de negócio do consumidor (aprovação, contagem de prazo, elegibilidade)
- não coloque conteúdo de documento em log, métrica ou tag
