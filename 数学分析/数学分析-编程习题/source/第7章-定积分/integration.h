/**
 * integration.h  —  数值积分 C 语言作业接口约定
 *
 * 学生需实现以下四个函数，并将实现放在 solution.c 中。
 * 编译命令（由评分脚本自动完成，无需提交 Makefile）：
 *   gcc -shared -fPIC -O2 -o solution.so solution.c -lm
 */

#ifndef INTEGRATION_H
#define INTEGRATION_H

typedef double (*func_t)(double x);

/**
 * 复化梯形公式
 * @param f   被积函数
 * @param a   积分下限
 * @param b   积分上限
 * @param m   等分数（子区间个数）
 * @return    积分近似值
 */
double composite_trapezoid(func_t f, double a, double b, int m);

/**
 * 复化 Simpson 公式
 * @param f   被积函数
 * @param a   积分下限
 * @param b   积分上限
 * @param m   等分数（每段再 2 等分做 Simpson）
 * @return    积分近似值
 */
double composite_simpson(func_t f, double a, double b, int m);

/**
 * Romberg 方法
 * @param f    被积函数
 * @param a    积分下限
 * @param b    积分上限
 * @param tol  收敛精度（对角线相邻元素之差的绝对值）
 * @return     积分近似值
 */
double romberg(func_t f, double a, double b, double tol);

/**
 * Gauss-Legendre 求积公式
 * @param f   被积函数
 * @param a   积分下限
 * @param b   积分上限
 * @param n   Gauss 点个数
 * @return    积分近似值
 */
double gauss_legendre(func_t f, double a, double b, int n);

#endif /* INTEGRATION_H */
