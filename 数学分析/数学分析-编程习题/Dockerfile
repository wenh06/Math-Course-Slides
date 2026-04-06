FROM python:3.10-slim

# gcc/make: 仅当需要支持 C 语言提交时才需要；纯 Python 作业可删去
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        make \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    numpy \
    sympy \
    mpmath \
    nbgrader

WORKDIR /course
