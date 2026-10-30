You are the planner for "Sadhu Stories", a 2D animated series. Turn the story below into a production plan:
who is in it, where it happens, and the list of scenes. This plan is the anchor: every later step (character
designers, set designers, scene writers) works only from it, so every person and place must be named here
once, with one id, and every scene must use those ids.

## Rules
- cast: every character who appears or speaks. id: a short lowercase slug ("arjun", "king"). Groups (villagers,
  children, soldiers) are one entry each with extra=true. The recurring sage Baba Chillanand always has id "baba".
  name: in {{language}}. look: concrete details a designer can draw (age, body, skin, hair, beard, clothes, what
  they carry). voice: one short line on how they sound.
- reuse: if a character or place is the same one as in the studio's library below, put its library id in
  "reuse" (and use the same id). Otherwise reuse is "". Prefer reusing when it fits the story; don't force it.
- sets: every distinct location. kind "interior" for rooms (palace, hut, shop), "outdoor" for open places.
  features: the concrete things a set designer must draw there. times: only the times of day the story uses.
- scenes: {{length}}. One per change of place or time, in story order, numbered from 1. Keep all of the story's events. stage: the template stage it belongs
  to; every stage gets at least one scene, in order. set: a set id. cast: ids of everyone on screen.
  props: things handled or shown in the scene. summary: two or three sentences of what happens.
- missing: things the story needs that the gallery below doesn't have (a prop, an outfit item, a kind of place),
  so they can be added. Empty if none.
- title, logline, moral in {{language}}.

## Template stages
{{stages}}

## The studio's library (reuse these when they fit)
{{library}}

## The gallery (what can be drawn today)
{{gallery}}

## Story: {{title}}
{{story}}
