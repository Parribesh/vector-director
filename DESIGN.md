# The Director: how it works today

The Director turns a story idea into a production: a `project.json` that sadhu's Studio can open, edit and play.
This page describes the code as it runs now. The learning plan for the milestones is in [docs/DESIGN.md](docs/DESIGN.md).
The sister page is `DESIGN.md` in sadhu, which covers everything after this pipeline.

## The rule behind everything

**The model picks, code builds.** A model only chooses from menus made of what really exists, and its answer must fit a
schema. Code then turns the picks into characters and sets and checks every id. So whatever comes back can be drawn.

## The flow

```
Studio  --POST /breakdown-->  vd serve (port 8772)  --job id-->  Studio polls /jobs/<id>

(Story)            optional: idea -> story text, written to a template's stages
   |
Breakdown          story -> scenes: place, time, who is present, what things. No design.
   |
Casting            names -> one id each. Every name gets a home: cast, picture, held, or left out.
   |
Continuity         a read-through of the plan; may fix a scene, add a person or a place
   |
Scene writing      one call per scene, 4 at a time: narration, lines, actions
   |
Character builders one call per new character, by kind: person or animal
   |
Set builder        one call per scene at a place, in story order: first visit, then what changed
   |
Staging            one call per scene: start marks, moves, poses, camera shots
   |
Accounting         code only: every named thing, and where it ended up
   |
project.json  -->  Studio saves it, and renders and edits from there
```

## Each step

Prompts are in `src/vector_director/director/prompts/`; the steps are in `director/pipeline.py`.

| Step | In | Out | Core idea |
|---|---|---|---|
| Breakdown | story, template stages | scenes with free-text names | Say what happens, not how it looks, so later steps have one outline to agree with. |
| Casting | outline, engine's species, reusable library | cast, places, pictures, held, left out | Names become ids here, and code refuses to go on until every name has a home. |
| Continuity | whole plan | corrected scenes, new cast or places | One reader sees the whole story at once. If its answer fails the checks, the old plan stays. |
| Scene writing | story, plan, one scene | beats: narration, line, action | Scenes run in parallel. Only that scene's cast may speak. |
| Character builders | brief, what they do in the scenes | a look from the engine's menus | Written after the scenes, so a builder knows what the character must do and carry. |
| Set builder | place, scene, what must be there, catalog | a background and things at marks | Sets are per scene in story order: a return visit keeps, adds or removes, so a place stays itself. A need with no match goes on `wanted`, never a wrong substitute. |
| Staging | beats, the set, marks, poses | `staging` and `beat.stage` | Comes last because it needs the set. The model gives marks and shot names; code adds spacing, facing and who looks at the speaker. |
| Accounting | everything | a table of what became of each name | Nothing vanishes silently: on screen, held, wanted, left out or lost. |

## What every call shares (`director/llm.py`)

- **A call** is a prompt file with `{{slots}}` plus a JSON schema. Enums in the schema are the menus.
- **Check, then repair once.** `Run.checked` asks, runs a code check, and sends any errors back one time.
- **Cache.** An answer is stored by (prompt text, schema, model), so repeating a run is free. Changing a prompt changes the key.
- **Providers.** Gemini first, then OpenAI on failure.
- **Log.** Every call, with prompt and answer, goes to `runs/<project>/calls.jsonl`: the future training data.
- **A failed step** is reported and leaves a default in place, so one bad scene doesn't lose the run.

## Who it talks to

```
Director --node tools/engine_bridge.mjs--> sadhu engine   menus, build a body or animal or room, seats
Director --reads--> sadhu bible/templates, projects/      templates, and characters and sets to reuse
Director --search--> library/ (registry + CLIP vectors)   2D gallery of SVG props
Studio   --HTTP--> vd serve                               /story /breakdown /stage /dress /jobs /search /items
```

A project with `mode: "3d"` changes two things: menus are cut down to `assets3d/catalog.json`, and the set builder picks
things directly from that catalog instead of searching the 2D gallery.

## Known gaps, for discussion

- **Nothing looks at the result.** No step sees a rendered frame; M1's scorers and judge aren't connected to this pipeline.
- **Scene writers can't read each other.** They share the plan but not each other's lines, so dialogue doesn't carry across scenes.
- **The look answer isn't used in 3D.** The builder returns `body3d`, which only the 2D engine reads. 3D bodies come from casting's free-text `look`, in sadhu's `tools/make_people3d.py`.
- **Staging has a small vocabulary.** People have 4 poses (stand, namaste, bless, meditate), while sadhu's new library has 13. Positions are a grid of 2D marks and the camera has 3 shots.
- **Corrections aren't captured.** Calls are logged, but Studio edits aren't, so there are no corrected examples to learn from.
- **Repair is a single try**, and it only catches what a code check can see, not whether the story reads well.
