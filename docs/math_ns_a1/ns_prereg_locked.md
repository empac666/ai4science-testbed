# Pre-registration LOCKED: OpenAI Navier–Stokes NL vs Lean semantic-mismatch audit

**Status:** LOCKED  
**Locked at:** 2026-10-11 20:48 Asia/Shanghai (CST, UTC+8)  
**Round label:** MATH-NS-A1  
**Draft provenance:** copied from `ns_prereg_draft.md` (SHA256 `5a2ad28e5d543e752a5427f20d14307a9a9fbee07b57ba706ee6eda20cfd6cbe`) then status flipped to LOCKED  
**Primary claim type:** Independent replication / extension of a published semantic-mismatch finding — **not** a claim that the Millennium Prize problem is solved or unsolved, and **not** a claim that OpenAI’s natural-language (NL) proof is false.

**Lock seal (materials at lock time):**

| Artifact | SHA256 |
|----------|--------|
| This locked file | see `ns_lock_seal.json` (SHA256 of full file after lock) |
| `ns_prereg_draft.md` (pre-lock) | `5a2ad28e5d543e752a5427f20d14307a9a9fbee07b57ba706ee6eda20cfd6cbe` |
| OpenAI NL PDF | `0e779481c4da40bd28d1e642e1d8ca57447d129610df28dfa5a11e9af8ae228f` |
| Bastounis et al. PDF | `3282e2c4103b955d635173749e7bf887fef7af7dd39e1abdb750b951030c538b` |
| Lean pin | `f9e8bc5b38b6e212696e8a30e3e91517af887bbd` |

---

## 0. One-sentence goal

Produce a public, pinned-commit **comparison table**: what selected NL statements claim vs what the cited Lean declarations actually prove, focusing on reproducible discrepancies already flagged by Bastounis–Circelli–Hansen (arXiv:2610.08144), without asserting that Lean compilation fails or that the Clay problem is settled.

---

## 1. Sources (pinned)

| Role | Citation / URL | Pin |
|------|----------------|-----|
| Gap paper | Bastounis, Circelli, Hansen, *Navier–Stokes lost in translation*, arXiv:2610.08144 | v1 (2026-10-06); local PDF: `/workspace/ai4s_math/Bastounis_NS_lost_in_translation.pdf` ; **SHA256** `3282e2c4103b955d635173749e7bf887fef7af7dd39e1abdb750b951030c538b` ; Ex. 3.1 ≈p.4–5; Ex. 3.3 ≈p.8–9 |
| OpenAI NL paper | *Finite time blowup for Navier–Stokes* | https://cdn.openai.com/pdf/32d9f210-8b73-45e0-91bc-82a30aef8a9a/navier-stokes.pdf ; local: `/workspace/ai4s_math/OpenAI_NS_blowup.pdf` ; **SHA256** `0e779481c4da40bd28d1e642e1d8ca57447d129610df28dfa5a11e9af8ae228f` ; (8.19) on printed p.95 (Lemma 8.6); (10.19) on printed p.123 (in Lemma 10.5 proof) |
| Lean repo | https://github.com/openai/NavierStokesAndEuler | **commit `f9e8bc5b38b6e212696e8a30e3e91517af887bbd`** (same pin as Bastounis et al.; shallow clone at `/workspace/ai4s_math/NavierStokesAndEuler`) |
| Lean toolchain | `leanprover/lean4:v4.34.0-rc2` | from repo `lean-toolchain` |
| Blog / announce | https://openai.com/index/navier-stokes-solution/ | contextual only |

**Out of scope for A1:** full Euler NL↔Lean audit; Meta textbook autoformalisation; OpenAI 722-manuscript corpus.

---

## 2. Research questions (locked wording)

**RQ1 (derivative loss).** For OpenAI NL Lemma 8.6 / eq. (8.19), does the closest Lean estimate require one extra torus derivative on the input (NL \(m+4\) vs Lean \(m+5\))?

**RQ2 (pressure-flux).** For OpenAI NL eq. (10.19) in the proof of Lemma 10.5, does the closest Lean bound differ in (a) right-hand-side dependence (\(B_R\) only vs also \(A_R\)/dissipation) and (b) proof strategy (Riesz on \(L^{3/2}\) vs Sobolev→\(L^2\) Riesz + different Hölder)?

**RQ3 (boundary).** Confirm and state clearly: Lean acceptance of a different (weaker / incomparable) formal statement does **not** certify semantic fidelity of the NL argument; conversely, a mismatch does **not** by itself prove the NL argument false.

---

## 3. Feasibility check (done before lock) — 2026-10-11

Performed on box workspace; **no full `lake build` yet**.

### 3.1 Artifact availability

- [x] Gap paper PDF downloaded and readable.
- [x] OpenAI NL PDF downloaded; text extraction confirms (8.19) and (10.19).
- [x] Lean repo cloned; `HEAD` = `f9e8bc5…` (matches Bastounis pin).
- [x] Key Lean files present: `NavierStokes/SmoothFamilyTorusInverse.lean`, `NavierStokes/ParametricTorusInverse.lean`, `NavierStokes/R3/PressureFlux.lean`.

### 3.2 Spot-check: RQ1 (m+4 vs m+5) — **CONFIRMED locally**

**NL (OpenAI PDF text extract):**
\[
\|N^{-1}F\|_{C_y^m} \le C_m \|F\|_{C_y^{m+4}}.
\]
Proof sketch quotes: *“Four more derivatives of \(F\) … leave a summable \((1+|k|)^{-3}\) bound.”*

**Lean (`SmoothFamilyTorusInverse.lean`, commit f9e8bc5):**

- `theorem norm_derivativeWord_inverse_le` (≈L1059–1080): hypotheses use `SmoothFourierData.xJet (w.length + 5) …`; bound uses `∑' k, (weight k ^ 4)⁻¹`.
- `theorem inverse_finiteJets` (≈L863–875): docstring *“Uniform full-tensor bound with five torus derivatives lost”*; statement `JetBound f S (n + 5) C → JetBound (inverse d f) S n (K * C)`.
- `ParametricTorusInverse.mixedJet_inverse_bound`: same `w.length + 5` and weight\(^4\) pattern.

**Mechanism (as in Bastounis Ex. 3.1):** NL uses Fourier weight giving \(\sum (1+|k|)^{-3}\) after \(+4\) derivatives; Lean’s `coefficient_seminorm_bound` path uses weight\(^4\) (and related \(+5\)), yielding a **weaker** (extra derivative) estimate relative to (8.19).

### 3.3 Spot-check: RQ2 (pressure-flux) — **CONFIRMED locally at statement level**

**NL (10.19) (text extract, schematic):**
\[
\Bigl|\int \pi\, w\cdot\nabla\chi_R\Bigr|
\le C_T R^{-1}\Bigl[(B_R+1)B_R^{1/2} + R^{-3/4} B_R^{3/4}\Bigr]
\quad\text{(a.e. } t\in(0,T)\text{)}.
\]
RHS depends on \(B_R\) (localized \(L^6\)), not explicitly on \(A_R\).

**Lean (`PressureFlux.lean`, `exists_uniform_actual_pressure_flux_bound`, ≈L576–598):**
\[
\bigl|\text{flux}\bigr|
\le CP\cdot\Bigl[
\bigl(\mathrm{cutoffL6}^{1/2}+1\bigr)
\bigl(\mathrm{dissipationRoot}/R + 1/R^2\bigr)
+ R^{-7/4}\,\mathrm{cutoffL6}^{3/4}
\Bigr]
\quad(\forall\, t\in(0,T)).
\]
Here `cutoffL6` ≈ \(B_R\), `dissipationRoot` ≈ \(A_R\). So Lean RHS **depends on both** localized gradient energy and \(L^6\) velocity; exponents differ (\(R^{-7/4}\) vs NL \(R^{-3/4}\) after the \(R^{-1}\) factoring).

**Strategy mismatch (to be tabulated, not re-proved):** Bastounis Ex. 3.3 lists three drivers — (1) Lean avoids \(L^{3/2}\) Riesz boundedness, uses Sobolev embedding + \(L^2\) Riesz (introduces \(A_R\)); (2) different Hölder conjugates; (3) Lean upgrades a.e.\(t\) to all \(t\) via continuity. A1 will **cite** these as claimed mechanisms and verify only the **statement surface** + named Lean lemmas on the call chain (`actual_flux_eq_canonicalCutoffFlux`, `pressurePair_decomposition`, etc.), not a full analytic re-derivation.

### 3.4 What is still open before lock

- [ ] Optional: `lake exe cache get && lake build` on a subset / Comparator challenge (heavy; may need higher `vm.max_map_count`). **Not required** for the comparison table if we only claim “what the declaration states.”
- [ ] Optional secondary mismatches: scan for other `+ 5` vs NL `+ 4` sites; Bastounis Remark 3.4 experiment link.
- [ ] Peer review of this draft (Grok / Cursor agent); **no Codex cloud**.

---

## 4. Success / failure criteria (pre-registered)

### 4.1 Unit of analysis

Each row of the public table is one **(NL locator, Lean declaration locator)** pair.

### 4.2 Classification labels (statement surface only; mutually exclusive primary label)

Score **only** the formal statement vs the NL inequality (hypotheses + conclusion + quantifiers). Proof-strategy narrative is a **non-scoring note**, citing Bastounis where used.

| Label | Definition |
|-------|------------|
| **MATCH** | Same conclusion strength and same essential hypotheses up to notational rename (including same derivative loss / same RHS dependence / same time quantifier). |
| **WEAKER** | Lean needs a strictly stronger hypothesis (e.g. extra derivative) **or** the Lean RHS adds a nonnegative term / factor that makes the bound strictly weaker under identical quantifiers (Bastounis Ex. 3.1 type). |
| **DIFFERENT** | Statement-surface check fails for reasons other than pure weakening: different exponent structure, a.e.\(t\) vs \(\forall t\), or incomparable spaces / dependence (e.g. NL depends only on \(B_R\), Lean also on \(A_R\)). Argument-path differences go in notes, not this label. |
| **UNCLEAR** | Locators ambiguous or notational gap too large; must document why. |

### 4.3 Replication success for A1

Three **outcomes** (not a soft pass):

| Outcome | Definition |
|---------|------------|
| **Confirmed** | Core D1 labelled **WEAKER** **and** core D2 labelled **DIFFERENT**, and items 1–2,4–5 below hold. Only then may public text assert a semantic mismatch (§6 mismatch sentence). |
| **Replication failure** | Either core pair labelled **MATCH**. Report as failure to replicate Bastounis on that pair (still publish the table). |
| **Inconclusive** | Either core pair **UNCLEAR**, or any other label combination. Publish table + blockers; **do not** use the §6 mismatch sentence. |

**Required for any published table** (all outcomes):

1. Table includes core D1 and D2 as **one pair each** (see §9); support declarations on separate rows.
2. For each pair: pinned commit SHA, full Lean namespace + file path, declaration name, line range, NL equation + PDF printed page, primary label from §4.2.
3. Outcome from the table above (Confirmed / Replication failure / Inconclusive).
4. Explicit disclaimer block published with the table (see §6); mismatch sentence only if **Confirmed**.
5. No claim language of the form “OpenAI’s NL proof is wrong” or “Millennium Prize solved/refuted” in report or X posts.

**Prior observation note:** The 2026-10-11 spot-checks in §3 are **not** independent of the locked prediction; they motivated this prereg. Post-lock scoring must still re-read the pinned locators and assign labels from §4.2 without changing pins.

### 4.4 Failure modes (report, do not hide)

- Cannot locate NL equation in PDF → **UNCLEAR**, stop that row.
- Lean declaration renamed after f9e8bc5 → stay on pin; do not silently move.
- Full build fails → note environment; do **not** treat as evidence of mathematical error.

---

## 5. Methods (what we will / will not do)

### Will do

1. Side-by-side extract of NL text for (8.19), (10.19) and surrounding proof sentences.
2. Quote Lean theorem signatures and key hypotheses/conclusions with permalinks to `f9e8bc5`.
3. Fill comparison table; add 0–3 **exploratory** secondary rows only if discovered by keyword search (`+ 5`, `weight k ^ 4`, `Riesz`, `cutoffL6`) **after** core rows are locked — exploratory rows marked `exploratory: true` and excluded from pass/fail.
4. Optional light call-graph: list lemmas used by the two core theorems (names only).
5. Draft EN/ZH X thread summarizing the table + disclaimers.

### Will not do

- Re-prove or refute finite-time blow-up.
- Modify Lean sources or claim a “fixed” formalization.
- Use Codex cloud agents.
- Attribute personal hardware / SST identifiers in public text.
- Treat ChatGPT screenshots in Bastounis as primary evidence (secondary color only).

### Tooling preference

- Grok CLI: `~/.grok/bin/grok -p` for draft critique / table wording.
- Cursor agent CLI: `/home/box/.local/bin/agent` for local edits if needed.
- Skip agy if geo-blocked.
- No Codex cloud.

---

## 6. Required public disclaimer (must appear with table and posts)

Always publish:

> We do **not** claim that OpenAI’s natural-language Navier–Stokes argument is incorrect, nor that the Clay Millennium problem is resolved or refuted. Lean compilation (if performed) shows only that **formal** statements are accepted; it does not by itself certify the **NL** proof.

**Additionally, only if outcome = Confirmed:**

> At commit `f9e8bc5`, the core pairs D1 and D2 do not semantically match the cited NL estimates (extra derivative loss; different pressure-flux bound/dependence).

---

## 7. Deliverables

| Artifact | Path (planned) |
|----------|----------------|
| This prereg (locked copy) | `/workspace/ai4s_math/ns_prereg_locked.md` (after review) |
| Comparison table | `/workspace/ai4s_math/ns_comparison_table.md` (+ CSV optional) |
| Work notes / quotes | `/workspace/ai4s_math/ns_audit_notes.md` |
| X draft EN/ZH | `/workspace/ai4s_math/ns_x_draft.md` |
| Local mirrors | PDFs + repo already under `/workspace/ai4s_math/` |

---

## 8. Timeline (target)

| Day | Task |
|-----|------|
| D0 (today) | Feasibility + this draft |
| D1 | Grok/Cursor review of prereg → lock |
| D1–D2 | Fill core table rows with permalinks; secondary scan |
| D2–D3 | Optional Comparator/`lake build` subset if machine allows |
| D3–D4 | Public note + EN/ZH X drafts (manual post if laptop offline) |

---

## 9. Key discrepancy checklist (seed for the table)

**Core pairs (required):**

| ID | NL locator | Lean locator (commit `f9e8bc5`) | Expected label | Spot-check 2026-10-11 |
|----|------------|----------------------------------|----------------|------------------------|
| **D1** | Lemma 8.6, eq. (8.19), OpenAI PDF **p.95**: \(\|N^{-1}F\|_{C_y^m}\le C_m\|F\|_{C_y^{m+4}}\). Bastounis Ex. 3.1 (≈p.4–5). | `NavierStokes.SmoothFamilyTorusInverse.norm_derivativeWord_inverse_le` in `NavierStokes/SmoothFamilyTorusInverse.lean` **L1059–1080** (`xJet (w.length + 5)`; weight\(^4\)) | WEAKER | Prior observation: matches |
| **D2** | Lemma 10.5 proof, eq. (10.19), OpenAI PDF **p.123**: flux \(\lesssim R^{-1}[(B_R+1)B_R^{1/2}+R^{-3/4}B_R^{3/4}]\) a.e. \(t\). Bastounis Ex. 3.3 (≈p.8–9). | `NavierStokesR3.PressureFlux.exists_uniform_actual_pressure_flux_bound` in `NavierStokes/R3/PressureFlux.lean` **L576–598** | DIFFERENT | Prior observation: matches |

**Support / definition rows (not scored for Confirmed):**

| ID | Role | Locator |
|----|------|---------|
| S1 | Same derivative-loss family as D1 | `inverse_finiteJets` L863–875 (`SmoothFamilyTorusInverse.lean`); docstring “five torus derivatives lost” |
| S2 | Same family | `NavierStokes.ParametricTorusInverse.mixedJet_inverse_bound` L654+ ; also `SmoothFamilyTorusInverse.mixedJet_inverse_bound` L1082+ |
| S3 | Lean flux support for D2 | `exists_uniform_canonicalCutoffFlux_bound` L546–572 |
| S4 | Lean defs ≈ \(A_R\), \(B_R\) | `dissipationRoot` L47, `cutoffL6` L50 in `NavierStokes/R3/ComparisonSetup.lean` |
| S5 | NL defs | OpenAI PDF near Lemma 10.5: \(A_R=(\int\chi_R\|\nabla w\|^2)^{1/2}\), \(B_R=\|\varphi_R^4 w\|_{L^6}\) (≈p.121–123) |

**Exploratory (excluded from Confirmed/failure):**

| ID | NL locator | Lean locator | Note |
|----|------------|--------------|------|
| D3* | Same family as D1 elsewhere | Other `JetBound … (n + 5)` / `xJet (… + 5)` sites | Pending keyword scan |
| D4* | Lemma 10.5 strategy text | Call-chain lemma **names** only | Non-scoring notes |

\*Exploratory; not required for A1 **Confirmed**.

---

## 10. Review log

| When | Who | Outcome |
|------|-----|---------|
| 2026-10-11 | Executor (feasibility) | Draft written; D1/D2 spot-checks pass |
| 2026-10-11 | Grok CLI (`grok -p`) | Critiqued §4.2–4.3 + locators; edits applied (3-outcome rule, statement-only labels, one-pair D1/D2, PDF pages + SHA256, def lines) |
| 2026-10-11 20:48 CST | Lock | Status → LOCKED; materials sealed |

---

## 11. Post-lock actions

1. ~~Lock this file~~ **done** → `ns_prereg_locked.md`.
2. Fill `ns_comparison.md` for core D1–D2 (and support rows).
3. Optional subset `lake build` — skip if Lean/elan unavailable.
4. Push lock + table to public branch under empac666 (Chinese commit message).
5. Keep 薄肌 / other media tracks out of this workstream.
