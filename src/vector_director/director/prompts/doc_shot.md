You are writing one shot of a short narrated explainer video (a lesson) for one learner. Studio draws every scene from
data and a narrator reads the shot's line. The video's plan is below; the shots before this one are written already.

## The brief
{{brief}}

## The plan
Title: {{title}}
{{outline}}

## Written so far (their lines)
{{before}}

## This shot
id: {{id}} · kind: {{kind}} · about {{words}} words
{{purpose}}
{{problems}}

## What a shot can show
{{kinds}}

## Your answer
- say: the narrator's line: conversational, second person, plain words, about {{words}} words. It carries on from the
  line before; don't repeat it. No markdown, no symbols the narrator would read out oddly (write "n squared", not
  "n^2"; "O of n", not "O(n)").
- show: what is on screen as the line begins, as a JSON object of the kind above, written out as text.
- beats: "" or a JSON array, as text, of [{"at": "<words of say>", "show": {...}, "cut": "cut" | "flash"}]: a different
  visual swapped in when those words are said. Use one only when the shot needs a second picture.
- seconds: 0, or for a shot that should hold in silence (the recall question), how long in all (about 9).
Every `at` (in a step, a term, a node or a beat) is a few words of `say`, exactly as written, in the order they are
said. Get the facts right: trace the algorithm yourself before writing a trace's steps, so every pointer, sum, cell and
`found` is what the code would really do; code must run.
