import numpy as np
import sympy as sp


def cotes_weights(n):
    x = np.linspace(0, 1, n + 1)
    C = np.zeros(n + 1)

    for i in range(n + 1):

        def L(t):
            val = 1.0
            for j in range(n + 1):
                if j != i:
                    val *= (t - x[j]) / (x[i] - x[j])
            return val

        ts = np.linspace(0, 1, 5001)
        C[i] = np.trapezoid([L(t) for t in ts], ts)

    return C


def cotes_weights_sp(n):
    x = sp.symbols("x")
    nodes = [sp.Rational(j, n) for j in range(n + 1)]
    C = []
    for i in range(n + 1):
        L = 1
        for j in range(n + 1):
            if j != i:
                L *= (x - nodes[j]) / (nodes[i] - nodes[j])
        C.append(sp.integrate(L, (x, 0, 1)))
    return C


def newton_cotes_integrate(f, a, b, n):
    C = cotes_weights(n)
    x = np.linspace(a, b, n + 1)

    return (b - a) * np.dot(C, np.array([f(xi) for xi in x]))


def composite_newton_cotes(f, a, b, n, m):
    C = cotes_weights(n)
    h = (b - a) / m
    total = 0.0

    for k in range(m):
        left = a + k * h
        right = left + h
        x = np.linspace(left, right, n + 1)
        total += h * np.dot(C, np.array([f(xi) for xi in x]))

    return total


def composite_trapezoid(f, a, b, m):
    h = (b - a) / m
    x = np.linspace(a, b, m + 1)
    y = np.array([f(xi) for xi in x])

    return h * (0.5 * y[0] + np.sum(y[1:-1]) + 0.5 * y[-1])


def romberg(f, a, b, max_level=5):
    T = np.zeros((max_level, max_level))

    # first column: composite trapezoid with 1, 2, 4, ... subintervals
    for k in range(max_level):
        m = 2**k
        T[k, 0] = composite_trapezoid(f, a, b, m)

    # extrapolation
    for j in range(1, max_level):
        for k in range(j, max_level):
            T[k, j] = (4**j * T[k, j - 1] - T[k - 1, j - 1]) / (4**j - 1)

    return T


def romberg_adaptive(f, a, b, tol=1e-10, max_level=10):
    T = np.zeros((max_level, max_level))

    # initial trapezoid (m = 1)
    h = b - a
    T[0, 0] = 0.5 * h * (f(a) + f(b))

    for k in range(1, max_level):

        # recursive computation of composite trapezoid
        h /= 2
        m = 2 ** (k - 1)

        # new midpoints
        new_points = [a + (2 * i + 1) * h for i in range(m)]
        T[k, 0] = 0.5 * T[k - 1, 0] + h * sum(f(x) for x in new_points)

        # Romberg extrapolation
        for j in range(1, k + 1):
            T[k, j] = (4**j * T[k, j - 1] - T[k - 1, j - 1]) / (4**j - 1)

        # stopping criterion (diagonal)
        if abs(T[k, k] - T[k - 1, k - 1]) < tol:
            return T[k, k], k, T[: k + 1, : k + 1]

    # if not satisfied
    return T[max_level - 1, max_level - 1], max_level - 1, T


def np_gauss_legendre_integrate(f, a, b, n):
    x, w = np.polynomial.legendre.leggauss(n)
    xp = 0.5 * (b - a) * x + 0.5 * (b + a)
    wp = 0.5 * (b - a) * w

    return np.dot(wp, [f(xi) for xi in xp])


def custom_gauss_legendre(n):

    # construct Jacobi matrix
    beta = np.array([k / np.sqrt(4 * k * k - 1) for k in range(1, n)])
    J = np.zeros((n, n))
    for i in range(n - 1):
        J[i, i + 1] = beta[i]
        J[i + 1, i] = beta[i]

    # eigenvalue decomposition
    vals, vecs = np.linalg.eigh(J)

    # the nodes are the eigenvalues
    x = vals

    # the weights are the square of the first component of the eigenvectors, scaled by 2
    w = 2 * (vecs[0, :] ** 2)

    return x, w


def custom_gauss_legendre_integrate(f, a, b, n):
    x, w = custom_gauss_legendre(n)
    xp = 0.5 * (b - a) * x + 0.5 * (b + a)
    wp = 0.5 * (b - a) * w

    return np.dot(wp, [f(xi) for xi in xp])
