# Document Intelligence Service

Serviço que recebe um documento médico e devolve os dados estruturados dele, com confiança e
evidência por campo, e indica quando o caso precisa de revisão humana. Esta versão trata dois tipos
de documento: atestado médico e resultado de avaliação médica.

O serviço apenas lê e descreve o documento. Ele não aprova nem nega pedidos, não guarda o arquivo
nem o resultado e não tem interface própria: é uma API chamada por outro sistema.

## Demonstração

Contrato no Swagger, atestado em PDF nativo, captura de tela cortada, resultado indeferido, suíte e
avaliação. Perfil `fake`, com os documentos sintéticos de `samples/`.

https://github.com/user-attachments/assets/8e0a8b08-ce9b-4127-8999-bb2f6299bf0c

## Como executar

Pré-requisito: [uv](https://docs.astral.sh/uv/getting-started/installation/). Ele instala o Python
3.12 usado pelo projeto.

```bash
git clone https://github.com/chenisen/document-intelligence-service.git
cd document-intelligence-service
make install
```

`make install` instala as dependências, gera os documentos de exemplo em `samples/` e ativa um hook
que roda `make ci` antes de cada push.

| Comando | O que faz |
| --- | --- |
| `make serve` | sobe a API em http://127.0.0.1:8000, com o Swagger em `/docs` |
| `make demo` | analisa um atestado de exemplo e imprime a resposta |
| `make analisar FILE=<arquivo>` | analisa qualquer arquivo sem subir o servidor |
| `make test` | roda os testes unitários e de contrato |
| `make ci` | roda o mesmo que o CI: lint, tipos, camadas, testes, cobertura e avaliação |
| `make eval` | compara o resultado dos 7 documentos de exemplo com a baseline |

`make help` lista todos os comandos. Com a API no ar, uma chamada de exemplo:

```bash
curl -F file=@samples/atestado_01_pdf_nativo.pdf http://127.0.0.1:8000/v1/documents:analyze
```

### Perfis

O perfil padrão é `fake`. Nele, OCR, modelo e base de normas são substituídos por dublês que
respondem a partir do gabarito de `samples/`, sem conta e sem credencial.

O perfil `aws` usa Amazon Textract, Amazon Bedrock e Amazon Kendra. Para ativá-lo, defina
`DIS_PROFILE=aws`, configure as credenciais da AWS e informe `DIS_KENDRA_INDEX_ID` e
`DIS_BEDROCK_GUARDRAIL_ID`. Sem essas duas variáveis o serviço não sobe. Esse perfil está implementado
e testado com respostas gravadas, mas ainda não foi executado contra uma conta real.

## Sobre o projeto

### API

Um endpoint, `POST /v1/documents:analyze`, que recebe o campo `file` em `multipart/form-data`: PDF,
JPEG, PNG ou HEIC, com até 4 MB. A resposta traz:

- o tipo do documento, com a confiança da classificação;
- os campos extraídos, cada um com valor, confiança, o trecho do documento que o sustenta e, quando
  vazio, o motivo;
- as validações aplicadas, como coerência de datas, formato do CRM e CID na tabela de referência;
- a norma interna aplicável, com fonte e versão;
- se o caso precisa de revisão humana, e por quê;
- a proveniência: modelo, versão do prompt, motor de OCR e horário da análise.

Os erros seguem `application/problem+json`, com um código estável no campo `code`. O contrato
completo está em `contracts/v1/`.

### Como o documento é processado

1. O formato é identificado pelo conteúdo do arquivo. HEIC é convertido para JPEG e a rotação é
   corrigida.
2. Documentos ilegíveis são recusados antes de qualquer chamada paga.
3. PDF com texto é lido diretamente. Imagens e PDFs digitalizados passam pelo OCR.
4. O modelo classifica o tipo do documento e extrai os campos.
5. Um valor só é aceito se o trecho citado pelo modelo existir no texto lido. Campo sem confiança
   suficiente volta vazio, com o motivo.
6. Regras em código validam os campos, a norma interna é consultada e o serviço decide se o caso
   vai para revisão.

### Tecnologias

Python 3.12 e FastAPI, publicados como AWS Lambda com imagem de contêiner pelo Serverless Framework.
Amazon Textract para OCR, Amazon Bedrock com Claude para classificação e extração, e Amazon Kendra
para as normas internas. CI e CD no GitHub Actions.

### Estrutura

```
src/
  core/          regras de negócio, sem dependência externa
  usecases/      fluxo da análise e interfaces com os serviços externos
  adapters/      integrações com a AWS e dublês para os testes
  entrypoints/   API HTTP, linha de comando e montagem das dependências
  functions/     handler da Lambda
config/          catálogo de tipos e configuração do modelo e do guardrail
contracts/v1/    OpenAPI, schema da resposta e catálogo de erros
docs/            PRD, escopo do MVP e decisões de arquitetura
specs/           especificação de cada parte do MVP e os testes que a cobrem
evals/           baseline da avaliação e tabela de preços
samples/         gerador dos documentos de exemplo e gabarito
```

## Documentos de exemplo

Os documentos de `samples/` são sintéticos, gerados por `samples/gerar_sinteticos.py`. Nomes, CPF,
CNPJ, CRM, CNES e endereços são fictícios, e cada arquivo leva no rodapé a marca de documento de
teste, sem validade legal. Nenhum documento ou dado pessoal real foi usado neste repositório.

## Licença

MIT. Veja `LICENSE`.
