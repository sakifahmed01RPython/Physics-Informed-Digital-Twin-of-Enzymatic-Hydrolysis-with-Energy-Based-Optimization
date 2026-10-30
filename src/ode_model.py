import numpy as np
from scipy.integrate import solve_ivp

R_GAS = 8.314
T_REF_K = 323.15

DEFAULT_PARAMS = {
    "kcat_ref": 0.5,
    "Km": 2.0,
    "Ki": 5.0,
    "kd_ref": 1e-3,
    "Ea_kcat": 40000.0,
    "Ea_kd": 60000.0,
    "pH_opt": 8.0,
    "pH_width": 2.5,
    "sub_act_heads": 1.0,
}


def arrhenius_factor(T_c, Ea, T_ref_k=T_REF_K):
    return np.exp(-Ea / R_GAS * (1.0 / (T_c + 273.15) - 1.0 / T_ref_k))


def ph_factor(pH, pH_opt, pH_width):
    return np.exp(-0.5 * ((pH - pH_opt) / pH_width) ** 2)


def hydrolysis_rhs(t, y, params, T_c, pH):
    S, P, E = y
    kcat = params["kcat_ref"] * arrhenius_factor(T_c, params["Ea_kcat"]) * ph_factor(pH, params["pH_opt"], params["pH_width"])
    kd = params["kd_ref"] * arrhenius_factor(T_c, params["Ea_kd"])
    Km = params["Km"]
    Ki = params["Ki"]
    denom = Km * (1.0 + P / Ki) + S
    rate = kcat * E * S / denom
    return [-rate, rate, -kd * E]


def simulate(S0, E0, T_c, pH, t_eval, params=None):
    p = dict(DEFAULT_PARAMS)
    if params:
        p.update(params)
    y0 = (S0, 0.0, E0)
    sol = solve_ivp(
        hydrolysis_rhs,
        (t_eval[0], t_eval[-1]),
        y0,
        t_eval=t_eval,
        method="LSODA",
        args=(p, T_c, pH),
        rtol=1e-6,
        atol=1e-9,
        max_step=5.0,
    )
    S, P, E = sol.y
    dh = 100.0 * P / S0
    return S, P, E, dh


def dh_curve(S0, E0, T_c, pH, t_eval, params=None):
    return simulate(S0, E0, T_c, pH, t_eval, params=params)[3]