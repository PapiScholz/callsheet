# callsheet: judging what is useful

**Default to keep.** An item goes off only when the profile shows the repo has nothing for it to work on: not now, not on the roadmap, and not as part of how the user works.

## Profile: answer these before judging anything

Write down an answer to each question, with the file you got it from:

1. **What does the repo ship?** API, web page, CLI, desktop app, library, docs site? Open the entry point (`src/index.*`, `main.*`, `app/`, `public/`). A Worker or server that returns HTML has a UI.
2. **Who uses it, and through what?** Browser, phone, terminal, another service?
3. **Stack and services.** Language, framework, database, hosting, the external APIs it calls, the CI.
4. **What is next?** Read the open items in `ROADMAP`, `HANDOFF.md` and `TODO`, and any research notes that feed them. Tools needed for what is coming are useful now.
5. **How does the user work here?** Repo and global `CLAUDE.md`/`AGENTS.md`: mandatory skills or plugins, workflows (handoff, ADRs, changelog, release), and the guards they rely on.
6. **What already fails or is fragile?** Known traps in the handoff or `CLAUDE.md`. For example "the dev server leaves orphan processes" makes a cleanup skill useful.

## Verdicts

| Verdict | When | Reason must |
|---|---|---|
| keep | Any concrete use in answers 1-6, or the item is cross-cutting (planning, debugging, review, git, verification, handoff, research, docs) | Name the use |
| off | The item works on something the profile shows the repo does not have and will not have | Cite the answer that rules it out: "no Python files; roadmap has none" |
| ask | You cannot point to either | State what would make it useful |

## Rationalizations seen in baseline tests

These are the reasons agents gave when they wrongly switched useful items off:

| Excuse | Reality |
|---|---|
| "Worker/API with no UI, so the browser tooling goes" | The agent read `package.json` only. The entry point served an HTML page with a microphone. Read the entry point. |
| "Inference runs elsewhere, so the model hub connector goes" | The roadmap's next step was to run a model from that hub in the browser. Answer 4 covers what is next. |
| "Orchestration guidance not needed in a small repo" | The global `CLAUDE.md` made it mandatory before any subagent. Answer 5. |
| "Not needed" / "Rarely used; invoke manually" | That is the default state of any useful tool between uses, not a reason. Once off, the model cannot invoke it at all. |
| "Overlaps with X" | Two useful tools in one area both stay. Overlap is only a reason when one is a strict, older subset of the other and the user said so. |
| "No design work here" | A repo with a user-facing page has accessibility, usability and copy work, even without a design system. |
| "Gate for a family the repo does not use" | Greenroom gates are protected: the skills behind them are reachable only through the gate. |

## Kinds: what to read and what is usually useful

- **Plugins.** Read the plugin description and **every skill and command inside it**. The plugin goes off as a whole, so one useful skill inside keeps it. Its MCP servers often show "Needs authentication"; they cost tool names, not much more.
- **claude.ai connectors and user MCP servers.** These cost the most, because they load every tool name. Mail, calendar, drive, payments, other clouds and other infra are usually off unless the profile shows the repo touches them. Documentation connectors (library docs, model hubs, vendor docs for the repo's stack) are usually useful.
- **`.mcp.json` servers inherited from parent folders.** They often belong to a sibling project. Check what they serve.
- **User skills.** Project-specific skills of OTHER repos (their name or description names that repo, its client or its files) go off. General-process skills stay.

## Cost, so the proposal shows what each change saves

| Item | Rough cost per session |
|---|---|
| claude.ai connector or MCP server | about 10-30 tokens per tool name, plus its server instructions. Large ones (Vercel, Resend) run 2-6k |
| Plugin | its skills' names and descriptions, about 50-150 each, plus any SessionStart hook text |
| User skill | its description, about 50-200 |
| Hooks-only or LSP plugin | close to 0: never worth switching off |
