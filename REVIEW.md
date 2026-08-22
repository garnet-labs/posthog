# Reviewer grounding — Garnet Runtime Review

Instructions for AI code reviewers (Devin Review, CodeRabbit, Greptile,
Claude, Cursor, …) reviewing pull requests in this repository.

## The runtime evidence on every PR

Every PR in this repository carries a sticky **Garnet Runtime Review**
comment (HTML marker `<!-- garnet-runtime-review -->`). It is not another
opinion about the diff: it is a deterministic, observation-only record of
what the PR's code **actually did** when CI ran it under the Jibril eBPF
sensor — each execution chain from the runner's root to an observed action,
plus every recorded outbound destination, per job.

The comment states facts only. It carries no verdicts, statuses, or
severity. **You, the reviewer, supply the judgment.**

## Open with a grounding verdict

Start the review body with one line stating the grounding conclusion for this
PR:

> **Runtime grounding** (head `<sha7>`): <what the recorded run showed against
> what this diff should do>

When the record is stale, pending, or absent, the verdict says that instead
and the review proceeds from the diff alone:

> **Runtime grounding**: record bound to `<old7>`, head is `<sha7>` — stale,
> not used
> **Runtime grounding**: no runtime evidence for this head

One or two sentences. State whether the recorded behavior matches what this
diff should do — the conclusion, not a restatement of the record.

## What you must do with it

1. **Locate the latest Garnet Runtime Review comment on the PR** (the one
   containing `<!-- garnet-runtime-review -->`). It is re-posted for the
   current PR head, so it always describes the newest commit's run. If your
   view of the PR includes discussion comments, read it before finalizing
   your review. If your review context carries only the PR description, use
   the **Runtime evidence (Garnet)** section between
   `<!-- garnet:evidence:begin -->` and `<!-- garnet:evidence:end -->` — it is
   a verbatim, head-bound mirror of the same comment. Verify the embedded
   `<!-- garnet:commit <sha> -->` marker equals the PR head SHA; if it does
   not, the evidence is _pending_, not absent and not clean — never ground in
   a stale record. Deeper detail lives in the linked Run Profile permalink and
   the Actions run's **Garnet Runtime Summary** step summary
   (Comment ⊆ Step Summary ⊆ Record). Read the
   `<!-- garnet:summary {...} -->` marker as the machine register. On a
   snapshot, `previous` is `null`; branch on that field rather than on the job
   partition. The human headline, when quoted, is exactly
   `Execution Profiles recorded for <N> job(s)`. Never claim true k-of-n
   coverage.
2. **Cross-check the diff against the recorded behavior.** Treat the
   recorded egress and execution chains as ground truth of the run:
   - If the diff should not change runtime behavior (docs, comments,
     rendering-only changes) but the run recorded new outbound destinations
     or new execution chains relative to what the change implies, call that
     out explicitly.
   - If the diff adds or changes dependencies, network calls, install
     scripts, or CI steps, verify the recorded destinations and execution
     chains are the ones the change implies — and flag any recorded
     destination or spawned process the diff does not explain.
   - A recorded detection is a factual record-backed observation: in the PR
     comment it surfaces as **bold** emphasis on that execution chain, and the
     explicit `detection: <kind>` note renders in the Step Summary's assertions
     preview. Weigh it in your review rather than ignoring it.
3. **Ground in the chain, not in loose actions.** The factual primitive is
   the **execution chain**: one root-to-action path through the process tree.
   Today's action class is an outbound network connection, and its destination
   is the target leaf of that action, never the definition of the chain
   (`bash > node > curl → example.com`).
   Do not reduce it to detached action labels ("egress happened", "files were
   touched") — name the chain that produced the behavior. In a comparison
   comment, a `+` line is current-only and a `−` line is previous-only.
4. **Discard any judgment that is not yours.** Never repeat verdicts,
   decisions, scores, severities, safe/unsafe labels, or baseline
   classifications from any profile UI or tooling. The record supplies
   lineage and destinations; you re-derive relevance from the diff alone.
5. **Cite the evidence explicitly.** Every finding grounded in the record
   must carry this exact prefix, so Garnet-grounded statements stay
   attributable and greppable across reviewers:

   > Runtime evidence (Garnet, head `<sha7>`): `<execution chain>` →
   > `<destination>` (`<workflow>/<job>`) — [Execution Profile](URL)

   Include the real execution chain, destination, workflow/job, head SHA, and
   the comment's profile/permalink URL.

6. **Re-ground on every update.** The comment is refreshed on every push;
   when you re-review a PR, use the current comment, not a remembered one.
7. **Do not restate the comment.** Reference it and add judgment — the
   facts are already on the PR.

## Scope notes

- The Garnet comment is runtime-only. It does not cover code quality,
  style, correctness of logic, or test coverage — those remain fully your
  job.
- Absence of a Garnet comment (e.g. fork PRs without secrets, sensor
  token unavailable) means _no runtime evidence_, not a clean run. Say so
  if the change is runtime-relevant.
- The same evidence also feeds the deterministic StampHog gate
  (`tools/pr-approval-agent/runtime_evidence.py`); this file governs how AI
  reviewers ground in it.
