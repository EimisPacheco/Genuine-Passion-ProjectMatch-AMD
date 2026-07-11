# OpenUI generation prompts

These are the exact natural-language prompts we fed to **OpenUI**
(github.com/wandb/openui — run locally or at openui.fly.dev) to generate the
recruiter dashboard's presentational components. OpenUI emits HTML/Tailwind,
which we exported to React + TypeScript and saved under
`frontend/components/openui/`. To reproduce or iterate, paste a prompt into
OpenUI, pick **React + Tailwind** export, and drop the result into that folder.

Target: **"Best Use of OpenUI."**

Theme passed to every prompt:
> Dark slate theme (slate-950 background, slate-200 text), sky-400 accent,
> rounded-xl cards with slate-800 borders. Modern, dense, recruiter-tool feel.

---

## 1. ScoreBar
> A labeled horizontal score bar. Props: `label` (string) and `value` (0–1
> float). Show the label on the left and the percentage on the right in small
> muted text, with a thin rounded track below filled to `value` in the sky
> accent color. Tailwind + React + TypeScript.

→ `components/openui/ScoreBar.tsx`

## 2. CandidateCard
> A ranked candidate card. Props: rank, name, headline, overall match percent,
> a `selected` boolean (show a "selected" pill when true), a recommendation
> string, and four labeled score bars (project similarity, genuine passion,
> domain, evidence quality). Big match percentage on the right. A "Details →"
> button. Dim the card to 70% opacity when not selected. Tailwind + React + TS.

→ `components/openui/CandidateCard.tsx`

## 3. EvidenceCard
> A clickable evidence card that links out to a source URL. Show a small
> uppercase source chip (e.g. GITHUB), the date, a confidence percentage on the
> right, a bold title, a 3-line-clamped description, and the URL in small accent
> text. Hover highlights the border. Tailwind + React + TS.

→ `components/openui/EvidenceCard.tsx`

## 4. AgentProgressList
> A live agent progress list. Each row: a status dot (amber=running, green=ok,
> red=error, sky=done), a monospaced agent name, and a detail string. Plus a top
> progress bar showing percent complete. Tailwind + React + TS.

→ `components/openui/AgentProgressList.tsx`
