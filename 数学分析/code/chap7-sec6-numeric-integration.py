import numpy as np


def cotes_weights(n):
    x = np.linspace(0, 1, n + 1)
    A = np.zeros(n + 1)

    for i in range(n + 1):

        def L(t):
            val = 1.0
            for j in range(n + 1):
                if j != i:
                    val *= (t - x[j]) / (x[i] - x[j])
            return val

        ts = np.linspace(0, 1, 5001)
        A[i] = np.trapezoid([L(t) for t in ts], ts)

    return A


def newton_cotes_integrate(f, a, b, n):
    A = cotes_weights(n)
    x = np.linspace(a, b, n + 1)

    return (b - a) * np.dot(A, np.array([f(xi) for xi in x]))
