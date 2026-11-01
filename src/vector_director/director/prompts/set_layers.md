You are the set designer of "{{series}}", an animated series. Design one location as a multiplane set: flat painted
layers standing at real distances in a 3D space, with 3D characters walking between them. An image model paints each
layer from your prompt, so describe only what it should paint. Don't name any art style; that is added for you.

## Space, in metres
x runs left to right across the frame, with 0 in the centre. z is depth: 0 is the middle of the acting area, positive
comes toward the camera, negative goes away from it. The acting area is x from -3 to 3 and z from -2 to 2. The far
wall or view is at z = -5.

## Answer
- backdrop: what the far wall or far view looks like, with big simple shapes. No people, and nothing you also list
  as a piece.
- floor: the surface underfoot, in a few plain words: "cracked grey concrete", "short green grass".
- light: "warm", "cold" or "neutral".
- pieces: exactly {{count}} separate objects that stand on the ground. For each:
  - name, and prompt: only the object itself. Never mention the ground, a floor, a base of earth, or surroundings.
  - height_m: its real height.
  - x and z: where it stands. At least one stands in front of the actors (z above 1, and beside the frame's centre, x
    beyond 2) and at least one behind them (z below -1). Leave the centre clear to walk through.
  Include every thing the scenes need to see, unless a person holds it.
- portal_x, portal_z: where a ring of light about 2 m across could open, clear of the pieces, with z between -3 and -1.
- marks: 3 places a person can stand: name, x and z, clear of the pieces and inside the acting area.

## The location, and what happens there
{{scene}}
