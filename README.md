# asepriteio

A Python library that provides basic functions to read / write Aseprite format files.

## Usage

  `aseprite.read_aseprite_file(path)`

Reads in the Aseprite file at the specified path and returns a dictionary representing the sprite data (see below).

  `aseprite.write_aseprite_file(path, sprite)`

Writes the sprite structure to the Aseprite file at the specified path.

## Sprite format

The sprite data is represented as a dictionary of dictionarys / lists as follows:

```
 sprite
 	name
	speed
  indexed
 	palette
 		array of rgb
	trans
	tags
		name
		from
		to
		loop_dir
	layers
		name
 		opacity
 		flags
 	frames
 		duration
 		cels
 			layer
 			x, y, w, h
 			pixels
```
