# Surveys Q2 AI Planning

Hey team,

I'm going through the AI features from product teams to give you some ideas on making your product agent-friendly in Q2 and taking it further to product autonomy. Here are some ideas and suggestions from PostHog AI's perspective – feel free to ignore this if you think it's not relevant.

## Two things to invest in Q2 (in order):

1. **MCP tools** – basic atomic capabilities that let agents interact with your product. Think of these as the API surface agents can reach. Make sure yours are covered: agents should be able to read, create, and update the core entities in your product.

2. **Skills** – the most impactful thing you can do for agents right now. Skills are instructions that teach agents how to accomplish goals with your product and other products: what sequence of steps to take, what to look for, how to interpret results. Unlike docs (which assume a human clicking through UI), skills are written for agents working through APIs and limited environments.

Once you ship MCP tools and skills, your product automatically works across every AI surface we offer – PostHog AI, PostHog Code, background agents, any coding agent your customers already use (Claude Code, Cursor, etc.), and vibe-coding platforms. No extra integration work needed.

From there, the path to product autonomy is:

- **Automations & background agents (coming Q2)** – these only work well once MCP tools and skills are in place. Once they are, we can wire up recurring tasks: the agent runs on a schedule or from the UI, using your product's tools and skills to do work.
- **Signals API (coming Q3)** – your product becomes proactive. Instead of waiting for a human to ask, your product emits signals that trigger agents automatically.

If you have any questions or feedback, message #team-posthog-ai or DM me.

Below I've gone through your product areas with specific suggestions.

---

Surveys already has solid AI foundations – the MaxTools (create, edit, analyze) and the survey agent mode in PostHog AI are great. The main gaps are around MCP tooling and skills.

## MCP (Q2) – migrate to code-generated tools and fill missing capabilities

Currently all 7 survey MCP tools (create, get, getAll, update, delete, stats, global-stats) are manually implemented in `services/mcp/src/tools/surveys/`. They are not part of the code-generation pipeline that other products (feature flags, cohorts, dashboards, error tracking, etc.) already use. Migrating to YAML-driven code-generated tools means your API serializers become the source of truth, tools stay in sync automatically, and you get less code to maintain. (PostHog AI is working on this migration, but your team owns the YAML config.)

### Missing MCP capabilities

These API endpoints exist but are not exposed as MCP tools:

- `GET /surveys/responses_count` – get response counts across surveys
- `POST /surveys/{id}/summarize_responses` – AI-powered response summarization
- `POST /surveys/{id}/summary_headline` – AI-generated summary headline
- `POST /surveys/{id}/duplicate_to_projects` – duplicate a survey to other projects
- `GET /surveys/{id}/archived-response-uuids` – list archived response UUIDs
- `POST /surveys/{id}/responses/{uuid}/archive` – archive a response
- `POST /surveys/{id}/responses/{uuid}/unarchive` – unarchive a response

## SQL tables

Helps the agent to effectively search data across products.

`system.surveys` is already implemented with basic fields (id, name, type, questions, appearance, start/end date). Consider adding more fields that would be useful for agents:

- `description` – survey description for search/context
- `archived` – filter out archived surveys
- `responses_count` – quick response volume without a separate query
- `linked_flag_key` – which feature flag controls targeting

## Skills (Q2)

No survey-specific skills exist yet (only the SDK audit skill). This is the biggest gap:

- **Create a survey** – teach agents the full sequence: choosing the right question types, setting up targeting (URL rules, feature flags, user properties, wait periods), configuring appearance, and launching
- **Analyze survey results** – guidance on how agents should interpret responses: which HogQL queries to run (using `getSurveyResponse()` and `uniqueSurveySubmissionsFilter()`), how to read NPS/CSAT scores, how to segment by user properties, when to use the `summarize_responses` endpoint
- **Design a survey for a goal** – given a product question (e.g., "why are users churning?"), teach the agent to pick the right survey type, write effective questions, set appropriate targeting, and plan follow-ups
- **Instrument a survey in code** – guide agents through adding survey code to a product (posthog-js setup, custom survey rendering, capturing responses programmatically)

## Automations/Background agents (Q2)

Using PostHog AI's coding agent to automate chores:

- Monitor active surveys and report results on a schedule (daily/weekly digests)
- Auto-close surveys that have reached a target number of responses or statistical significance
- Cross-survey analysis – compare results across multiple surveys to find patterns
- Survey lifecycle management – archive stale surveys, notify when response rates drop
- Instrument surveys from the web UI or PostHog AI chat (coding agent writes the integration code)

## Signals (Q3)

How your product becomes automated and proactive:

- Survey reached target response count -> Summarize results and notify team
- NPS/CSAT score drops below threshold -> Alert and investigate contributing factors
- New open-text response patterns detected -> Cluster and surface emerging themes
- Survey response rate drops significantly -> Suggest targeting adjustments
- Survey completed -> Auto-generate follow-up survey based on findings

## Moonshot ideas

- **Continuous discovery agent**: Goal -> Survey design -> Auto-deploy -> Collect responses -> Analyze -> Generate next survey -> Repeat. An autonomous research loop where the agent runs ongoing user research without human intervention, surfacing insights and adjusting its approach based on what it learns.
- **Synthetic pre-testing**: Before launching a survey to real users, use an AI to simulate responses and predict potential issues with question wording, answer bias, or low completion rates – similar to what Roundtable (YC S23) does for market research.
- **Conversational surveys**: AI-powered follow-up questions in real time. Instead of static survey flows, the agent dynamically generates follow-up questions based on previous answers, turning surveys into mini-interviews – similar to Outset (YC S23) and Conveo (YC W24) but embedded directly in your product.
- **Insight-to-survey pipeline**: Agent notices an anomaly in Product analytics (e.g., spike in churn) -> automatically designs and deploys a targeted survey to affected users -> analyzes responses -> recommends actions. Fully autonomous from signal to insight.
