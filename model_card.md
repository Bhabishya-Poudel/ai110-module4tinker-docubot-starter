# DocuBot Model Card

This model card is a short reflection on your DocuBot system. Fill it out after you have implemented retrieval and experimented with all three modes:

1. Naive LLM over full docs  
2. Retrieval only  
3. RAG (retrieval plus LLM)

Use clear, honest descriptions. It is fine if your system is imperfect.

---

## 1. System Overview

**What is DocuBot trying to do?**  
Describe the overall goal in 2 to 3 sentences.

> _Your answer here._

**What inputs does DocuBot take?**  
For example: user question, docs in folder, environment variables.

> _Your answer here._

**What outputs does DocuBot produce?**

> _Your answer here._

---

## 2. Retrieval Design

**How does your retrieval system work?**  
Describe your choices for indexing and scoring.

- How do you turn documents into an index?
- How do you score relevance for a query?
- How do you choose top snippets?

> _Your answer here._

**What tradeoffs did you make?**  
For example: speed vs precision, simplicity vs accuracy.

> _Your answer here._

---

## 3. Use of the LLM (Gemini)

**When does DocuBot call the LLM and when does it not?**  
Briefly describe how each mode behaves.

- Naive LLM mode:
- Retrieval only mode:
- RAG mode:

> _Your answer here._

**What instructions do you give the LLM to keep it grounded?**  
Summarize the rules from your prompt. For example: only use snippets, say "I do not know" when needed, cite files.

> _Your answer here._

---

## 4. Experiments and Comparisons

All three modes were run on identical, identically worded questions (Gemini `gemini-flash-lite-latest`, docs in `docs/`).

| Query | Naive LLM (Mode 1) | Retrieval only (Mode 2) | RAG (Mode 3) | Notes |
|------|------|------|------|------|
| How do I connect to the database? | **Harmful.** Confident answer with invented `DB_HOST`/`psql` steps. Real answer is `DATABASE_URL`. | Refused. | Refused. | DATABASE.md and SETUP.md do answer this, so both refusals are false negatives. |
| Which fields are stored in the users table? | **Harmful.** Confident invented schema (`id`, `username`, `password_hash`...). | Refused. | Refused. | Naive sounds authoritative and is not grounded in the docs. |
| What does /api/projects/<project_id> return? | **Harmful.** "Typically returns" generic JSON fields. | Refused. | Refused. | The naive answer is plausible but not drawn from the docs. |
| How does a client refresh an access token? | **Harmful.** Generic OAuth `grant_type=refresh_token` flow. | Refused. | Refused. | AUTH.md says to call `/api/refresh`, so the docs do answer this. |
| Where is the auth token generated? | Asked for more context, because naive mode never receives the docs. | Returned the `TOKEN_LIFETIME_SECONDS` paragraph. Wrong paragraph. | "I do not know..." | AUTH.md says `generate_access_token` in `auth_utils.py`. The right file was found but the wrong paragraph was picked. |
| What environment variables are required for authentication? | **Harmful.** Guessed `AUTH_SECRET`, `NEXTAUTH_SECRET`. | Returned only the intro paragraphs of SETUP.md and AUTH.md. | Said it cannot list the variables, then added "I do not know..." | Retrieval found the right files but not the variable list. RAG correctly noticed the evidence was insufficient. |
| Is there any mention of payment processing? | Said no context was provided. | Refused. | Refused. | Correct refusal in modes 2 and 3. |
| How do I deploy to production? | **Harmful.** Generic deploy checklist. | Refused. | Refused. | Not in the docs, so refusing is correct. |

**Important caveat:** `naive_answer_over_full_docs` in `llm_client.py` deliberately ignores `all_text` ("We ignore all_text and send a generic prompt"). Mode 1 therefore never sees the docs. That is the intended Phase 0 baseline, but it means Mode 1 is "LLM from memory", not "LLM over the whole corpus".

**Examples of each pattern**

- *Naive generation: confident but weakly grounded.* "Which fields are stored in the users table?" Mode 1 listed a full schema with no evidence at all. "How do I connect to the database?" gave `DB_HOST`/`psql` steps that contradict the docs' `DATABASE_URL`.
- *Retrieval only: accurate but hard to read.* The snippets come back as raw Markdown paragraphs with a filename header, and the reader has to extract the answer. For "Where is the auth token generated?" the output was a single unrelated config bullet. There was no synthesis and no signal about whether the snippet was the answer.
- *RAG: clarity plus evidence.* The best RAG behavior seen was on the environment-variables question. It said which file it relied on (`AUTH.md`) and explained why the snippets were insufficient, instead of guessing as Mode 1 did. It also refused cleanly on out-of-scope questions (payments, deploy). I did not get a clean positive example where RAG answered fully and correctly. See the failure case below.
- *RAG still fails.* "Which endpoint lists all users?" The docs contain `### GET /api/users`, which returns all users for admins. Retrieval returned nothing, so RAG refused. RAG is only as good as retrieval: the LLM cannot use evidence that never reaches it.

**What patterns did you notice?**

- Naive LLM looks impressive on exactly the questions the docs would answer (schema, DB connection, refresh flow). It gives fluent, specific, wrong-for-this-project answers with no way to tell.
- Retrieval only is clearly better when you need an exact quote or a verifiable source, and when the right paragraph is retrieved. It never invents anything.
- RAG is better than both when retrieval returns relevant snippets. The LLM then adds readability, a source citation and a refusal decision. When retrieval is empty or off-target, RAG is no better than retrieval alone, and it adds an LLM call that cannot recover missing evidence.

---

## 5. Failure Cases and Guardrails

**Failure case 1: false refusal.** Question: "Which endpoint lists all users?" The system returned "I do not know based on these docs" in modes 2 and 3. API_REFERENCE.md has `### GET /api/users`. The cause is `MIN_MATCH_RATIO = 0.6` in `docubot.py`. The query words (`endpoint`, `lists`, `users`) must mostly appear verbatim in the paragraph. The doc says "Returns a list", so `lists` does not match `list`, and the endpoint paragraph never says "endpoint". It should have answered `GET /api/users` (admin only). The same exact-word problem hit the database-connection and token-refresh questions.

**Failure case 2: right file, wrong paragraph.** Question: "Where is the auth token generated?" Retrieval picked AUTH.md but returned the `TOKEN_LIFETIME_SECONDS` bullet because it shares "generated" and "token". The correct paragraph names `generate_access_token` in `auth_utils.py`. Matching is by word overlap with no stemming ("generated" vs "generation") or ranking by specificity. RAG then refused, which is safe but unhelpful.

**Failure case 3 (naive mode):** Mode 1 invented a `users` schema and a DB connection recipe with full confidence.

**When should DocuBot say "I do not know based on the docs I have"?**

- The topic is not in the docs (payment processing, production deployment).
- The retrieved snippets mention the topic but not the requested detail (the env-variable names), so answering would require guessing.
- The query has no meaningful words after stopword removal.

**What guardrails did you implement?** Stopword filtering. A minimum-match threshold of 60% of the query's meaningful words per document, and again on the chosen paragraph. A top_k limit of 3 snippets. A hard "I do not know" return when nothing passes, before any LLM call. A strict RAG prompt: use only the snippets, reply with an exact refusal string otherwise, cite files, and do not invent endpoints or config values.

**Observed trade-off:** the guardrails are tuned toward refusing. There were no hallucinations in Modes 2 and 3 across the queries run, but many answerable questions were refused. Precision is high and recall is poor.

---

## 6. Limitations and Future Improvements

**Current limitations**

1. Exact-word matching: no stemming or synonyms (`lists` != `list`, `connect` != `connection`), so answerable questions are refused.
2. Paragraph selection counts overlapping words with no weighting, so generic paragraphs can beat specific ones, and headings and intro text can outscore the real answer.
3. The 0.6 match ratio is a single global threshold that is too strict for short natural-language queries and not tuned against labelled data.
4. Mode 1 does not receive the docs at all, so it cannot be used to test "LLM with the whole corpus".

**Future improvements**

1. Add light stemming or lemmatization, and weight rarer words higher (TF-IDF or BM25). Lower the ratio threshold.
2. Split docs by heading into chunks, and boost heading matches.
3. Build a small labelled set of questions with expected source files, to measure retrieval recall before the LLM runs.

---

## 7. Responsible Use

**Where could this system cause real world harm if used carelessly?** Mode 1 can mislead developers into wrong database, auth or API usage with confident but invented details. Mode 3 can refuse correct questions, which pushes people toward asking the unconstrained LLM instead. Docs can also be out of date, and DocuBot has no notion of that.

**What instructions would you give real developers who want to use DocuBot safely?**

- Treat Mode 1 as unverified. Do not use its answers for config, auth or schema questions.
- Prefer RAG or retrieval only, and check the cited file for anything that matters.
- "I do not know" means the retrieval step found nothing, not that the docs lack the answer. Search the docs directly before concluding.
- Keep the docs current and re-test retrieval whenever they change.

---

## Mode comparison checkpoint

**Which mode was easiest to trust on one question?** On the environment-variables question, RAG. Naive guessed variable names, retrieval returned two unrelated intros, and RAG said which file it relied on and that the snippets did not contain the variable names. **What the others missed:** naive had no grounding at all, and retrieval gave no signal that its snippets were not the answer. **When an LLM needs retrieval:** to stay tied to this project's facts. **When retrieval alone is not enough:** when the evidence must be read, combined or judged sufficient. RAG also cannot fix retrieval that returns nothing, as with `GET /api/users`.
