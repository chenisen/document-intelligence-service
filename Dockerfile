# Imagem de Lambda, e não zip: `pypdfium2` e `pillow-heif` trazem binário nativo e estouram o limite
# de camada. A imagem também remove a diferença entre o que roda local e o que roda na nuvem.
#

FROM public.ecr.aws/lambda/python:3.12-arm64

# O `uv` instala a partir do lock, então a imagem recebe exatamente as versões que a suíte viu.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR ${LAMBDA_TASK_ROOT}

# Dependências antes do código: camada que só muda quando o lock muda.
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project -o requirements.txt \
    && uv pip install --system --no-cache -r requirements.txt \
    && rm requirements.txt

# Código e o conteúdo que não é código. `samples/` fica de fora: conjunto de referência é de teste,
# e nada que roda em produção o lê.
COPY src/ ${LAMBDA_TASK_ROOT}/
COPY config/ ${LAMBDA_TASK_ROOT}/config/
COPY knowledge/ ${LAMBDA_TASK_ROOT}/knowledge/

# Sem CMD: o handler é declarado em `serverless.yml`, sob `functions.analyze.image.command`.
# Dois lugares dizendo o mesmo é um lugar a mais para divergir.
