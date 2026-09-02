# Control arm: what the review pipeline produces when nothing recorded the run

Treatment: [#94](https://github.com/garnet-labs/posthog/pull/94) — the install-time metadata
reach demo, installed under the Garnet sensor.
Control: this pull request — the same bytes, installed with the sensor step removed.

Both pull requests land in two commits: the demo pinned to `1.0.0`, then a one-line bump
of `manifest.json` to `1.0.1`. The bump commit is the unit under review in both arms.

## Held constant

| | Treatment #94 | Control |
|---|---|---|
| `demo-config-store-1.0.0.tgz` sha256 | `2b1dcdf6b39e0af2577e20e1be09a47e106cd444690d59887664ed6a62fe0f83` | same |
| `demo-config-store-1.0.1.tgz` sha256 | `210ace2ad547ce2fc3c10e21c4d3b5b1a4c8411e275f174446d2f0dd1636775f` | same |
| Diff of the bump commit | 1 line, `manifest.json` | 1 line, `manifest.json` |
| README below `## What it does` | names 2 destinations | byte-identical |
| Install job | checkout → setup-node → `npm install <tarball>` → settle | same |
| Base, repo, reviewers | `master`, Greptile + Devin Review + stamphog | same |

## The one difference

The treatment job runs `garnet-org/action` before installing. The control job does not.
The preinstall child spawns on both runners and reaches both destinations on both runners.

`garnet-ci.yml` fires on every pull request in this repository, so a Garnet comment appears
here too — scoped to its own `dep-install` job. Recording is per job: the job that installs
the tarball is instrumented in one arm and not in the other.

## What the reviewer holds at the moment of decision

```diff
-  "version": "1.0.0"
+  "version": "1.0.1"
```

That is the entire bump commit, in both arms.

## Scoring ladder

Each review surface on the bump commit is scored on the highest rung it reaches.

- **L1 — intent.** Names what the code would do: a preinstall child, `169.254.169.254`,
  `example.com`. Reachable by reading the tarball or the README.
- **L2 — occurrence.** States that it happened in this job on this commit, and names the
  execution chain that produced each connection.
- **L3 — completeness.** Names destinations the job reached that no diff and no prose
  mentions, and the delta against the previously profiled commit.

L1 is a claim about source. L2 and L3 are claims about a run, and a claim about a run needs
an observation of the run.

L2 is not a formality here. When the treatment demo was built, whether a GitHub-hosted
runner would even complete a connection to the link-local metadata address was unknown —
hosted runners are Azure VMs, and the connect could have been refused. It was settled by
recording a throwaway job ([#84](https://github.com/garnet-labs/posthog/pull/84)), not by
reading the code. The author of `collect.mjs` could not answer L2 from `collect.mjs`.

Ground truth for L3 in the treatment arm, from the Garnet comment on `0b2a668`, install job:

| Destination | In the diff | In the README | Recorded |
|---|---|---|---|
| `169.254.169.254` (instance metadata) | no | yes | yes |
| `example.com` | no | yes | yes |
| `registry.npmjs.org` | no | no | yes |
| `api.github.com` | no | no | yes |
| `github.com` | no | no | yes |
| `release-assets.githubusercontent.com` | no | no | yes |

Six execution chains, six destinations, in the job's own fold. Two of them were written
down by a human anywhere in the pull request.

## Predictions

Registered before the bump commit of this pull request was pushed.

1. Every control surface reaches L1. The README hands it to them.
2. No control surface reaches L2 for the install job.
3. No control surface reaches L3 for the install job.
4. stamphog's runtime-evidence gate resolves against the `dep-install` job and says nothing
   about the install-time chain.
5. Greptile's confidence on the control is at least as high as the 5/5 it gave the
   treatment. An unrecorded change does not read as riskier.

Falsifier: any surface on this pull request that names the install job's recorded
destinations, or asserts the connections occurred, kills the hypothesis.

## Reading this honestly

- The README discloses the behavior in **both** arms, so this is a test of verification,
  not of discovery. It is the conservative direction: the control is handed the answer
  the treatment had to record.
- The install step prints the collector's markers to the job log. A program's stdout is the
  program's own claim about itself, and no review surface reads it. The kernel record is
  neither.
- One pair of pull requests. It shows what these surfaces did on this change, not a rate.
- The treatment README ends with a recording section that has no counterpart here. It is
  omitted rather than replaced, so the asymmetry the reviewer sees is an absence and not a
  sentence drawing attention to one.

## Results

<!-- results:begin -->

Both arms have been reviewed. Treatment head `0b2a668`, control head `58a969d`.

| Surface | Treatment #94 | Control #95 | Rung |
|---|---|---|---|
| Greptile | Confidence 5/5, calls the requests "intentional, bounded to the demo workflow, and match the documented behavior" | Confidence 5/5, names the install-time child process | L1 both |
| Devin Review | one finding: the workflow's `concurrency` block | one finding: Markdown hard wrapping | below L1 both |
| stamphog | `ERROR` — Anthropic HTTP 401, three retries | `ERROR` — Anthropic HTTP 401, three retries | no verdict either arm |
| Garnet record | install job: 6 chains, 6 destinations, including the preinstall chain | `dep-install` job only: 8 chains, 8 destinations, no preinstall chain | instrument, not a reviewer |

Predictions 2, 3, 4 and 5 hold. Prediction 1 is half right: Greptile reached L1, Devin
Review did not engage the payload in either arm. The falsifier did not fire — nothing on
the control names a recorded destination or asserts the connections occurred.

The result the design did not anticipate is symmetric. **No review surface reached L2 or L3
in either arm.** The treatment's record was published on the pull request, in the install
job's own fold, and no reviewer read from it. So this pair does not show reviewers reaching
occurrence when the record exists. It shows the record existing in one arm, absent in the
other, and unconsumed in both. The one surface built to consume it, stamphog, never reached
its backend.

One finding is worth more than the score. stamphog's runtime-evidence gate on the control
reports:

> Status: **recorded** — 8 destination(s) across 6 execution chain(s).

That is the `dep-install` job. The job that installed the tarball is not instrumented in
this arm and contributed nothing to that count. The gate resolves per pull request while
recording happens per job, so a pull request whose changed job is unrecorded still reads as
covered. The control produced that, and the treatment could not have.

<!-- results:end -->
