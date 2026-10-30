# H12 — Sampling power and correlated cluster guard

Earlier H08/H11 screening accepted five net wins and a nominal one-sided
binomial p<=0.05, with as few as 30 supported cases. However five wins from
one cluster (e.g., repeated formulations of one template) are NOT five
independent wins. H12 adds a second cluster-level sign screen: five
distinct net-positive declared clusters, positive majority over negative
clusters, and one-sided cluster-sign p<=0.05. Cluster declarations still do
not independently verify original source provenance.

Under the deliberately optimistic model of independent, identically
distributed Bernoulli wins with probability p, ZERO losses and a cutoff of
at least five wins, the exact power for n cases is:
P(K>=5) = sum_{k=5}^n C(n,k) p^k(1-p)^(n-k).
This is a deterministic conditional design calculation, not evidence that
Río has the assumed success probability. H12 computes the minimum n for
power >=0.8 and checks it with 20,000 seeded Monte Carlo draws per scenario.

Under p=0.10, the 30-case screen has about 0.17549 power and 66 independent
cases are required for >=0.8 conditional power, even with ZERO candidate
losses. Under correlated groups, a design-effect approximation
1+(m-1)rho can lower effective sample size; example n=40, group=5,
rho=0.5 gives n_eff≈13.33. That is a sensitivity hypothesis, not observed
correlation. Five discordant wins and zero losses yield 1/32 = 0.03125
conditional one-sided sign probability; this alone is not proof of general
performance, especially after selection or repeated testing.

The synthetic one-cluster attack verifies p_case=0.03125 but
p_cluster=0.5, blocking a false engineering screen. A deliberately
memorized synthetic oracle may pass both conditional screens and still
cannot establish independent provenance or authorize promotion.

Read script: python scripts/h12_power.py. No model weights changed and no
external holdout acquired. H08 issue #8 stays open.
