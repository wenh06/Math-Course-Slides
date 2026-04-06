/**
 * solution.c  —  数值积分作业（C 语言版）参考答案
 *
 * 对应 Python 参考实现：source/第7章-定积分/第6节-定积分的数值计算.ipynb
 */

#include <math.h>
#include <stdlib.h>
#include "integration.h"

/* ── 复化梯形公式 ────────────────────────────────────────────────────────── */
double composite_trapezoid(func_t f, double a, double b, int m) {
    double h   = (b - a) / m;
    double sum = 0.5 * (f(a) + f(b));
    for (int i = 1; i < m; i++)
        sum += f(a + i * h);
    return h * sum;
}

/* ── 复化 Simpson 公式 ───────────────────────────────────────────────────── */
double composite_simpson(func_t f, double a, double b, int m) {
    int    n   = m * 2;          /* 将 [a,b] 2m 等分 */
    double h   = (b - a) / n;
    double sum = f(a) + f(b);
    for (int i = 1; i < n; i++) {
        double x = a + i * h;
        sum += (i % 2 == 1) ? 4.0 * f(x) : 2.0 * f(x);
    }
    return h / 3.0 * sum;
}

/* ── Romberg 方法 ────────────────────────────────────────────────────────── */
double romberg(func_t f, double a, double b, double tol) {
#define MAX_LEVEL 10
    double T[MAX_LEVEL][MAX_LEVEL] = {{0.0}};

    /* 第0行：1个子区间的梯形公式 */
    double h  = b - a;
    T[0][0]   = 0.5 * h * (f(a) + f(b));

    for (int k = 1; k < MAX_LEVEL; k++) {
        /* 递推求复化梯形：仅对上一步的新中点求值 */
        h *= 0.5;
        int    m      = 1 << (k - 1);   /* 2^(k-1) 个新中点 */
        double midsum = 0.0;
        for (int i = 0; i < m; i++)
            midsum += f(a + (2 * i + 1) * h);
        T[k][0] = 0.5 * T[k-1][0] + h * midsum;

        /* Richardson 外推（Romberg 加速） */
        for (int j = 1; j <= k; j++) {
            double p = pow(4.0, j);
            T[k][j]  = (p * T[k][j-1] - T[k-1][j-1]) / (p - 1.0);
        }

        /* 停止准则：对角线相邻元素之差 */
        if (fabs(T[k][k] - T[k-1][k-1]) < tol)
            return T[k][k];
    }
    return T[MAX_LEVEL-1][MAX_LEVEL-1];
#undef MAX_LEVEL
}

/* ── Gauss-Legendre 求积公式 ─────────────────────────────────────────────── */

/*
 * 用 Newton 法计算 n 点 Gauss-Legendre 节点和权重（[-1,1] 上）。
 *
 * 算法：
 *   1. 利用对称性，只需求正半轴上的 m = ⌈n/2⌉ 个根。
 *   2. 初始猜测：Legendre 多项式第 i+1 个根的渐近公式
 *        xi ≈ cos(π*(i+0.75)/(n+0.5))
 *   3. Newton 迭代：P_n(x) / P_n'(x)，利用递推关系
 *        P_n(x) = ((2n-1)*x*P_{n-1}(x) - (n-1)*P_{n-2}(x)) / n
 *        P_n'(x) = n*(P_{n-1}(x) - x*P_n(x)) / (1-x²)
 *   4. 权重：w_i = 2 / ((1-xi²) * (P_n'(xi))²)
 */
static void gl_nodes_weights(int n, double *x, double *w) {
    int m = (n + 1) / 2;
    for (int i = 0; i < m; i++) {
        /* 初始猜测（正半轴方向由大到小） */
        double xi = cos(M_PI * (i + 0.75) / (n + 0.5));
        double p0, p1, p2, dp, dx;

        /* Newton 迭代 */
        for (int iter = 0; iter < 100; iter++) {
            p0 = 1.0;
            p1 = xi;
            for (int j = 2; j <= n; j++) {
                p2 = ((2*j - 1) * xi * p1 - (j-1) * p0) / j;
                p0 = p1;
                p1 = p2;
            }
            /* p1 = P_n(xi), p0 = P_{n-1}(xi) */
            dp = n * (p0 - xi * p1) / (1.0 - xi * xi);
            dx = p1 / dp;
            xi -= dx;
            if (fabs(dx) < 1e-15) break;
        }

        /* 对称放置节点 */
        x[i]       = -xi;
        x[n-1-i]   =  xi;
        /* 权重公式 */
        w[i] = w[n-1-i] = 2.0 / ((1.0 - xi * xi) * dp * dp);
    }
}

double gauss_legendre(func_t f, double a, double b, int n) {
    double *x = (double *)malloc(n * sizeof(double));
    double *w = (double *)malloc(n * sizeof(double));
    gl_nodes_weights(n, x, w);

    double c1 = 0.5 * (b - a);   /* 区间变换：[-1,1] → [a,b] */
    double c2 = 0.5 * (b + a);
    double result = 0.0;
    for (int i = 0; i < n; i++)
        result += w[i] * f(c1 * x[i] + c2);

    free(x);
    free(w);
    return c1 * result;
}
