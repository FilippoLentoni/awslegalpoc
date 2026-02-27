# Deep Dive: Eval Failure Investigation

## Date: 2026-02-21
## Eval Run: `eval-20260221-201452`
## Dataset: `test_2`
## Overall Score: 75% (3/4 correct)

---

## Failing Question

**Query**: "In caso di datio in solutum avente ad oggetto un bene immobile a favore di un coniuge sposato in regime di comunione legale, l'acquisto rientra immediatamente nella comunione?"

**Domain**: Le obbligazioni | **Tipologia**: Specifica

### Expected Answer (Ground Truth)
- Property acquired through datio in solutum in satisfaction of a **personal credit** does **NOT** enter community property
- Governed by **Art. 179, lett. f) c.c.** — substitution of personal credit (surrogazione reale)
- Not by Art. 177, lett. a) c.c. (general acquisitions during marriage)
- The other spouse's participation IS required for immovable property

### Agent's Actual Answer
- Incorrectly concluded property **DOES** immediately enter community under Art. 177, lett. a) c.c.
- Treated it as a general acquisition during marriage
- Failed to recognize the Art. 179, lett. f) exception

### Judge Reasoning
"The actual output reaches the opposite legal conclusion from the expected output. This is a fundamental legal error regarding the application of art. 179, lett. f) c.c. to datio in solutum scenarios involving personal credits."

---

## Diagnostic Investigation

### 1. KB Direct Query Results

**Query 1**: "datio in solutum bene immobile comunione legale art 179 beni personali"
| # | Source | Score | Key Content |
|---|--------|-------|-------------|
| 1 | Indice - RP.docx | 0.800 | Table of contents — mentions "Surrogabilità art. 179 lett. F" |
| 2 | Capitolo 10.docx | 0.799 | Art. 178 vs 179 — business assets, not datio in solutum |
| 3 | **Capitolo 10.docx** | **0.797** | **MISLEADING CHUNK**: "beni acquistati con denaro della comunione de residuo cadono immediatamente in comunione legale ai sensi dell'art. 177 lett. a" — talks about comunione de residuo scenario, NOT personal credit |
| 4 | Capitolo 9.docx | 0.791 | Art. 179 full text — lists all lett. a-f categories of personal property |
| 5 | Capitolo 9.docx | 0.777 | **CORRECT CONTENT**: Art. 179 lett. f — surrogazione, declaration requirements, other spouse participation for immovables |

**Query 2**: "art 179 lettera f surrogazione beni personali coniuge"
| # | Source | Score | Key Content |
|---|--------|-------|-------------|
| 1 | **Capitolo 9.docx** | **0.812** | **CORRECT**: Art. 179 lett. f — full surrogazione explanation, conditions, spouse participation |
| 2 | Indice - RP.docx | 0.807 | Table of contents |
| 3 | Capitolo 9.docx | 0.801 | Prevailing doctrine supports surrogazione with personal money |
| 4 | Capitolo 9.docx | 0.800 | Permuta example of personal property substitution |
| 5 | Capitolo 9.docx | 0.791 | Cass. 24-9-2004 n. 19250 — declaration is not optional |

### 2. S3 Data Bucket Contents

20 documents in `s3://beta-awslegalpoc-kb-data/`:
- `- Indice - RP.docx` — Table of contents
- `Capitolo 1.docx` through `Capitolo 16.docx` — Regime patrimoniale chapters
- `Il contratto in generale (Diener 2021).pdf` — 22MB
- `Le obbligazioni (Nobili 2024).pdf` — 13MB
- `Successioni e donazioni (Capozzi 2023).pdf` — 50MB

### 3. Root Cause Classification

- [ ] **KB Content Gap** — RULED OUT. Art. 179 lett. f) is well-covered in Capitolo 9.docx
- [ ] **Retrieval Miss** — RULED OUT. Tested with `max_results=10` and 1024-token chunks — same failure.
- [x] **Model Reasoning Error** — CONFIRMED ROOT CAUSE. Re-tested with both larger chunks (1024) and more results (10) — same wrong conclusion. The model receives correct Art. 179, lett. f) content but still applies Art. 177, possibly misled by a chunk from Capitolo 10 about comunione de residuo.

**Key insight**: The KB contains a chunk that says the **opposite** conclusion for a **different** scenario (comunione de residuo assets → enters community). The model failed to distinguish between:
- Datio in solutum with **personal credit** → stays personal (Art. 179, lett. f)
- Acquisition with **comunione de residuo** assets → enters community (Art. 177, lett. a)

---

## Re-test Results

### Attempt 2: 2026-02-21 (eval-20260221-213935) — dataset: test_2
**Changes**: chunkMaxTokens 512→1024, max_results 5→10
**Result**: 75% (3/4) — **SAME FAILURE**. Datio in solutum question still incorrect.
**Conclusion**: Retrieval is not the problem. Model reasoning error confirmed.

### Attempt 3: 2026-02-21 (eval-20260221-220231) — dataset: test_2
**Changes**: Prompt tuning (added "Metodologia di ragionamento giuridico") + 1024 chunks + 10 results
**Result**: 50% (2/4) — **REGRESSION**. Datio in solutum still wrong + obbligazioni indivisibili regressed.
**Conclusion**: Larger chunks + more results caused regression. Prompt tuning needs testing with original retrieval settings.

### Attempt 4: 2026-02-21 (eval-20260221-231645) — dataset: test_3 (10 items)
**Changes**: Prompt tuning (kept) + REVERTED to 512 chunks + 5 results
**Result**: 70% (7/10) — **DATIO IN SOLUTUM FIXED!**
| # | Result | Question | Notes |
|---|--------|----------|-------|
| 1 | CORRECT | Portabilità del mutuo | |
| 2 | INCORRECT | Adempimento del terzo — rapporti solvens | Wrong on surrogation (Cass. SU 9946/2009) |
| 3 | INCORRECT | Mutamento soggetto — novazione soggettiva | Missed detailed accollo analysis |
| 4 | CORRECT | Natura giuridica accollo | |
| 5 | CORRECT | Tipologie di delegazione | |
| 6 | INCORRECT | Datio pro solvendo vs pro soluto | Wrong default rule — Art. 1266 instead of Art. 1198 |
| 7 | CORRECT | Debito di valuta vs valore | |
| 8 | CORRECT | Obbligazioni indivisibili | Regression recovered |
| 9 | CORRECT | Remissione vs pactum de non petendo | |
| 10 | **CORRECT** | **Datio in solutum — comunione legale** | **FIXED by prompt tuning** |

**Conclusion**: Prompt tuning ("Metodologia di ragionamento giuridico") fixed the original datio in solutum failure. Retrieval settings should stay at original values (512 chunks, 5 results). Remaining 3 failures are new questions requiring separate investigation.

---

## Remediation Summary

| Approach | Tested | Result |
|---------|--------|--------|
| Retrieval tuning (1024 chunks + 10 results) | Yes | No effect on target question, caused regression, ~4x cost increase |
| Prompt tuning alone (with original retrieval) | Yes | **FIXED target question**, no regression on previously passing items |
| Prompt tuning + retrieval tuning combined | Yes | Regression (50%) — retrieval changes hurt more than helped |

**Winning combination**: Prompt tuning + original retrieval (512 chunks, 5 results)

---

## Eval Failure Deep Dive Protocol

Reusable step-by-step process for investigating any future eval failure.

### Phase 1: Identify the Failure
1. Run eval: `python3.11 -m poetry run python scripts/run_eval.py --dataset <dataset_name>`
2. Open the CSV results file (`eval-results-*.csv`)
3. For each INCORRECT item, record:
   - The query
   - The domain and tipologia
   - The judge's reasoning (what was wrong)

### Phase 2: Inspect the Langfuse Trace
1. Open Langfuse → Datasets → select the dataset → find the run
2. Click the failing item's trace
3. Note the trace structure: `invoke_agent → execute_event_loop_cycle → chat + tool calls`
4. For each `search_knowledge_base` tool call, record:
   - **Input**: What query did the agent send to the KB?
   - **Output**: What chunks came back? (source file, relevance score, content snippet)
5. Check the final `chat` span: what reasoning did the model apply to the retrieved chunks?

### Phase 3: Direct KB Diagnostic
Query the KB directly to compare with what the agent retrieved:
```bash
aws bedrock-agent-runtime retrieve \
  --knowledge-base-id <KB_ID> \
  --retrieval-query '{"text": "<query matching the failing question>"}' \
  --retrieval-configuration '{"vectorSearchConfiguration": {"numberOfResults": 5}}' \
  --region us-east-2
```
Run 2-3 query variants (exact question, key legal terms, article numbers).

### Phase 4: Root Cause Classification
Classify into one of three categories:

| Root Cause | Symptom | Fix |
|-----------|---------|-----|
| **KB Content Gap** | Direct KB query returns no relevant chunks | Add missing documents to S3 data bucket, re-sync KB |
| **Retrieval Miss** | Content exists in KB but agent's queries don't surface it | Tune chunking (size/overlap), add metadata filters, improve tool description to guide query formulation |
| **Model Reasoning Error** | Correct chunks retrieved but model reaches wrong conclusion | Tune system prompt, add few-shot examples, consider model upgrade, or add conflicting-info handling guidance |

### Phase 5: Remediate and Re-test
1. Apply the fix (add KB content / tune prompt / adjust retrieval)
2. Re-run eval on the same dataset: `python3.11 -m poetry run python scripts/run_eval.py --dataset <dataset_name>`
3. Verify the previously failing item now passes
4. Confirm no regressions on other items
5. Document the fix in this file under a new dated section

### Phase 6: Prevent Recurrence
1. If the failure reveals a pattern (e.g., model confuses similar articles), add more test cases to the dataset covering edge cases
2. If a KB gap was found, consider what other related content might be missing
3. Update the system prompt if a reasoning pattern needs correction
4. Add the failing question to the "quick" eval dataset for CI/CD regression testing
