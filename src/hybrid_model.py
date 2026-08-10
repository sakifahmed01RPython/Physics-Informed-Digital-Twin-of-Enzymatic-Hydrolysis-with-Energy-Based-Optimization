import torch
import torch.nn as nn
import torchdiffeq

from src.ode_model import hydrolysis_rhs

HYBRID_ENABLED = False
HIDDEN_SIZES = [16, 16]
SEED = 42

STATE_COLS = ["S", "P", "E", "DH"]
CONDITION_COLS = ["pH", "Temp_C", "E_S_ratio"]
COMPOSITION_COLS = ["Moisture_pct", "CrudeProtein_pct", "CrudeLipid_pct", "Ash_pct",
                    "Hydroxyproline_pct", "Collagen_pct"]


class ResidualNet(nn.Module):
    def __init__(self, d_state=4, d_cond=3, d_comp=6, hidden=HIDDEN_SIZES):
        super().__init__()
        d_in = d_state + d_cond + d_comp
        layers = []
        prev = d_in
        for h in hidden:
            layers.append(nn.Linear(prev, h))
            layers.append(nn.SiLU())
            prev = h
        layers.append(nn.Linear(prev, 2))
        self.net = nn.Sequential(*layers)

    def forward(self, state, cond, comp):
        return self.net(torch.cat([state, cond, comp], dim=-1))


class HybridODE(nn.Module):
    def __init__(self, ode_params, residual_net=None):
        super().__init__()
        self.ode_params = ode_params
        self.residual_net = residual_net

    def forward(self, t, y, cond, comp):
        S, P, E = y[0], y[1], y[2]
        p = self.ode_params
        Km = p["Km"]
        Ki = p["Ki"]
        kcat = p["kcat_ref"]
        kd = p["kd_ref"]
        denom = Km * (1.0 + P / Ki) + S
        rate = kcat * E * S / denom
        dS_ode = -rate
        dP_ode = rate
        dE_ode = -kd * E
        if self.residual_net is not None:
            S0 = p.get("S0_holder", 1.0)
            state = torch.stack([S, P, E, 100.0 * P / S0], dim=-1)
            delta = self.residual_net(state, cond, comp)
            dS_ode = dS_ode + delta[..., 0]
            dP_ode = dP_ode + delta[..., 1]
        return torch.stack([dS_ode, dP_ode, dE_ode], dim=-1)


def simulate_hybrid(S0, E0, T_c, pH, e_ratio, composition, t_eval, ode_params,
                    residual_net=None, adjoint=True, method="dopri5", rtol=1e-4, atol=1e-6):
    t = torch.tensor(t_eval, dtype=torch.float64)
    y0 = torch.tensor([S0, 0.0, E0], dtype=torch.float64)
    cond = torch.tensor([pH, T_c, e_ratio], dtype=torch.float64)
    comp = torch.tensor(composition, dtype=torch.float64)
    ode = HybridODE(ode_params, residual_net)

    class FuncWrapper(nn.Module):
        def __init__(self):
            super().__init__()
            self.ode = ode

        def forward(self, tt, yy):
            return self.ode(tt, yy, cond, comp)

    func = FuncWrapper()
    if adjoint:
        sol = torchdiffeq.odeint_adjoint(func, y0, t, method=method, rtol=rtol, atol=atol)
    else:
        sol = torchdiffeq.odeint(func, y0, t, method=method, rtol=rtol, atol=atol)
    S, P, E = sol[:, 0], sol[:, 1], sol[:, 2]
    dh = 100.0 * P / S0
    return S, P, E, dh


def smoke_test():
    print("smoke test: hybrid scaffold (residual enabled), gradient flow check")
    torch.manual_seed(SEED)
    ode_params = {"kcat_ref": 6.356, "Km": 403.4, "Ki": 403.4, "kd_ref": 0.00868,
                  "Ea_kcat": 40000.0, "Ea_kd": 60000.0, "pH_opt": 8.0, "pH_width": 2.5,
                  "S0_holder": 8.7}
    net = ResidualNet().double()
    t_eval = list(range(0, 121, 20))
    comp = [55.3, 17.4, 10.1, 17.2, 0.55, 3.93]
    lossf = nn.MSELoss()
    target_dh = torch.tensor([0.0, 8.5, 13.2, 16.5, 18.2, 19.3, 20.2], dtype=torch.float64)
    for adjoint in (False, True):
        for p in net.parameters():
            p.grad = None
        S, P, E, dh = simulate_hybrid(8.7, 0.174, 55.0, 8.0, 0.02, comp, t_eval, ode_params, net, adjoint=adjoint)
        loss = lossf(dh, target_dh)
        loss.backward()
        grads = [p.grad for p in net.parameters() if p.grad is not None]
        grad_norm = sum(float(g.norm()) ** 2 for g in grads) ** 0.5
        print(f"  adjoint={adjoint}: final DH(pred)={float(dh[-1]):.2f} loss={float(loss):.4f} "
              f"grad_norm={grad_norm:.3f} finite={torch.isfinite(torch.stack([p.data.norm() for p in net.parameters()]).sum()).item()}")
    print("smoke test OK")


if __name__ == "__main__":
    smoke_test()