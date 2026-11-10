# Echoes

Echoes are the souls that roam the school. Each one is a flat 2D picture standing in the 3D world, and each has its own abilities, route limits, and jumpscare video.

## Adding an Echo

Add one `register(EchoSpec(...))` call to `chubaka/echoes/roster.py`:

```python
register(EchoSpec(
    id="olha",
    name="Ольга",
    start="room_14",
    ai=5.0,
    traits=(FlashlightShy(steps=3, stun=5.0), Footsteps()),
    jumpscare=JumpscareSpec(video="video/jumpscares/olha.lyv", duration=1.5),
))
```

Put the picture at `chubaka/assets/echoes/olha/sprite.png`. A transparent PNG works best, with the feet at the bottom edge. Without a file the game draws a placeholder silhouette chosen with `shape`, `color`, and `eyes`.

| `EchoSpec` field | Meaning |
| --- | --- |
| `start` | Node id where the Echo begins |
| `ai`, `ai_per_night` | Activity from 0 to 20, raised every night |
| `interval` | Seconds between movement attempts |
| `walk_speed`, `retreat_speed` | Metres per second |
| `directness` | Chance to step toward the door instead of wandering |
| `habitats` | Optional list of nodes the Echo may use, empty means everywhere |
| `door_threshold`, `door_wait`, `give_up` | How open the door must be, how long it must stay open before the attack, and when the Echo gives up |
| `height`, `columns` | Sprite height in metres and horizontal detail of the mesh |
| `sprite` | Optional custom path under `chubaka/assets` |

## Abilities

An ability is a `Trait` subclass in `chubaka/echoes/traits.py`. Override only the hooks you need:

| Hook | When |
| --- | --- |
| `update(echo, ctx, dt)` | Every frame |
| `can_move(echo, ctx)` | Return `False` to hold the Echo still |
| `move_chance(echo, ctx, chance)` | Change the chance of moving |
| `on_lit(echo, ctx, dt)` | Every frame while the flashlight shines on the Echo |
| `on_arrive(echo, ctx)` | After it reaches a node |
| `door_pressure(echo, ctx)` | Multiplier for the attack timer |
| `can_attack(echo, ctx)` | Return `False` to delay the attack |
| `visible_on_camera`, `visible_to_player` | Hide the picture in some situations |

`ctx` offers `lit(echo)`, `seen_by_player(echo)`, `on_camera(echo)`, `watched(echo)`, `distance_to_player(echo)`, `play(name, volume)`, and the player data in `ctx.view`. An Echo has `flee(steps, stun)`, `retreat()`, `jump_to(node)`, and `speed_scale`.

Ready traits: `FlashlightShy`, `CameraFreeze`, `LightEater`, `Stalker`, `DoorBreaker`, `Sprinter`, `Footsteps`, `Unrecorded`, `Shadowed`, `Patient`.

## Jumpscare video

`JumpscareSpec.video` is a `.lyv` file relative to `chubaka/assets`. Create it with the tools in `tools/`. When the file is missing the game shows the Echo picture growing and shaking for `duration` seconds, so a new Echo works before its video exists. After the scare the game over screen offers a retry.

## Sprites in the engine

`lysyk/engine/sprite.py` adds 2D pictures to the 3D world:

```python
sprite = Sprite.from_png(path, height=1.8, columns=48)
board = Billboard(sprite, position=(x, 0.0, z))
world.add(board.object)
board.face(camera_position)
```

Transparent pixels are cut out, equal neighbouring pixels are merged into one rectangle, and the result is a normal mesh, so the picture is lit by the scene lights and hidden by walls. `Sprite` also accepts a list of images for frame animation with `Billboard.set_frame`.
