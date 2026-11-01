You are the set designer of "{{series}}", an animated series. Design one location as a multiplane set: flat painted
layers standing at real distances in a 3D space, with 3D characters walking between them. An image model paints each
layer from your prompt, so describe only what it should paint. Don't name any art style; that is added for you.

## Space, in metres
x runs left to right across the frame, with 0 in the centre. z is depth: 0 is the middle of the acting area, positive
comes toward the camera, negative goes away from it. The acting area is x from -3 to 3 and z from -2 to 2.

## Answer
- backdrop: what the far wall or far view looks like from eye level, seen straight on. It fills the whole picture and
  has no people. Its lower edge is where it meets the ground, so show no ground or floor at all.
- ground: the colour of the floor or ground, as a hex colour, and what it is made of.
- light: "warm", "cold" or "neutral", and a one-line mood.
- pieces: exactly {{count}} separate objects that stand on the ground, each painted alone on a transparent background
  and seen straight on, level with the camera, with the whole object in view and its base flat at the bottom.
  - name, and prompt: the object alone, with nothing around it.
  - height_m: its real height.
  - x and z: where it stands. At least one stands in front of the actors (z above 1) and at least one behind them
    (z below -1), so that people pass between layers. Leave the centre clear to walk through.
  Include every thing the scene needs to see, unless a person holds it.
- marks: 2 or 3 places a person can stand, with name, x and z, clear of the pieces.

## The location, and what happens there
{{scene}}
