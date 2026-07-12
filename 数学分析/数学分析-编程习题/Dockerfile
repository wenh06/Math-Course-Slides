FROM python:3.12-slim

# ── 代理设置（可选） ───────────────────────────────────────────────────────
# 若拉取基础镜像或 pip 安装受阻于网络，可传入代理地址：
#   docker build --network host \
#     --build-arg HTTP_PROXY=http://<PROXY_HOST>:<PROXY_PORT> \
#     --build-arg HTTPS_PROXY=http://<PROXY_HOST>:<PROXY_PORT> \
#     -t nbgrader-math .
# 国内 Docker Hub 不稳定时，daemon.json 中也可配置 "proxies" 一并生效。
ARG HTTP_PROXY
ARG HTTPS_PROXY

# gcc/make: 仅当需要支持 C 语言提交时才需要；纯 Python 作业可删去
# libc6-dev 提供 math.h 等标准库头文件，gcc 本身不包含它们
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libc6-dev \
        make \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    numpy \
    sympy \
    mpmath \
    nbgrader

WORKDIR /course
