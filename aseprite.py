# Copyright 2022 Joe Trewin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# Aseprite file reader/writer
# Sprite format:
#
# sprite
# 	name
#	speed
#   indexed
# 	palette
# 		array of rgb
#	trans
#	tags
#		name
#		from
#		to
#		loop_dir
#	layers
#		name
# 		opacity
# 		flags
# 	frames
# 		duration
# 		cels
# 			layer
# 			x, y, w, h
# 			pixels

import os
import sys
import io
import argparse
import struct
import pprint
import zlib

LAYER = 0x2004
CEL = 0x2005
TAGS = 0x2018
PALETTE = 0x2019
USER = 0x2020
SLICE = 0x2022

def read_aseprite_file(path):
	sprite = {}

	with open(path, mode='rb') as file:
		data = file.read()
		header = struct.unpack("=IHHHHHIHIIB3BHBB", data[:36])

		size = header[0]
		frames = header[2]
		width = header[3]
		height = header[4]
		cdepth = header[5]
		flags = header[6]
		speed = header[7]
		transp = header[10]
		cols = header[14]
		pix_w = header[15]
		pix_h = header[16]

		# print("{}x{}, {} frames, {} cols, {} transparent [{} bytes]".format(width, height, frames, cols, transp, size))

		sprite['name'] = os.path.splitext(os.path.basename(path))[0]
		sprite['w'] = width
		sprite['h'] = height
		sprite['trans'] = transp
		sprite['frames'] = []
		sprite['layers'] = []
		sprite['speed'] = speed
		sprite['indexed'] = (cdepth == 8)
			
		# frames

		ptr = 128
		for frame_i in range(0, frames):
			fheader = struct.unpack("IHHHBBI", data[ptr:ptr+16])
			frame_size = fheader[0]
			magic = fheader[1]
			old_chunks = fheader[2]
			duration = fheader[3]
			chunks = fheader[4]
			if chunks == 0:
				chunks = old_chunks

			# print(" frame {} [{}]: {} chunks - duration: {}ms".format(frame_i, frame_size, chunks, duration))
			assert(magic == 0xF1FA)

			frame = {
				'duration': duration,
				'cels': []
			}

			ptr += 16

			# chunks

			for chunk in range(0, chunks):
				(chunk_size, chunk_type) = struct.unpack("=IH", data[ptr:ptr+6])

				next_chunk = ptr + chunk_size
				ptr += 6

				if chunk_type == PALETTE:
					sprite['palette'] = []

					(pal_size, first, last) = struct.unpack("III", data[ptr:ptr+12])
					# print("   palette: [{}] {} -> {}".format(pal_size, first, last))
					ptr += 12 + 8	# 8 bytes unused
					for pe in range(0, pal_size):
						entry = struct.unpack("HBBBB", data[ptr:ptr+6])
						# print("       ({}, {}, {}, {})".format(entry[1], entry[2], entry[3], entry[4]))
						sprite['palette'].append(entry[1:])
						ptr += 6
				
				elif chunk_type == LAYER:
					(lay_flags, lay_type, child_level, _skip, _skip, blend_mode, opacity, _skip, _skip, _skip, name_size) = struct.unpack("HHHHHHB3BH", data[ptr:ptr+18])
					ptr += 18

					name = ''
					if name_size > 0:
						name = data[ptr:ptr+name_size].decode("utf-8")

					# print("   layer: {}".format(name))

					sprite['layers'].append({
						'flags': lay_flags,
						'type': lay_type,
						'child_level': child_level,
						'blend_mode': blend_mode,
						'opacity': opacity,
						'name': name
					})

					ptr += name_size

				elif chunk_type == TAGS:
					(tag_count) = struct.unpack('H', data[ptr:ptr+2])[0]
					# print("   tags: {}".format(tag_count))

					sprite['tags'] = []

					ptr += 2 + 8
					for tag in range(0, tag_count):
						(from_frame, to_frame, loop_dir) = struct.unpack('=HHB', data[ptr:ptr+5])
						ptr += 5 + 12
						(name_size) = struct.unpack('H', data[ptr:ptr+2])[0]
						ptr += 2
						tag_name = ''
						if name_size > 0:
							tag_name = data[ptr:ptr+name_size].decode("utf-8")
						# print("     {} {} -> {}".format(tag_name, from_frame, to_frame))
						ptr += name_size

						sprite['tags'].append({
							'name': tag_name,
							'from': from_frame,
							'to': to_frame,
							'loop_dir': loop_dir
						})

				elif chunk_type == CEL:
					(layer, x, y, opacity, cel_type) = struct.unpack("=HhhBH", data[ptr:ptr+9])
					ptr += 9 + 7   # skip 7 future byes
					pixels = None

					cel = {
						'layer': layer,
						'x': x,
						'y': y,
						'opacity': opacity
					}

					if cel_type == 0:
						(w, h) = struct.unpack("HH", data[ptr:ptr+4])
						ptr += 4
						# print("   cel: layer {} ({},{}) ({}, {}) opacity {}".format(layer, x, y, w, h, opacity))
						pixels = data[ptr:next_chunk]
						cel['w'] = w
						cel['h'] = h
						cel['pixels'] = pixels

					elif cel_type == 1:
						(frame_pos) = struct.unpack("H", data[ptr:ptr+2])[0]
						# print("   cel: layer {} LINKED - {} ({},{}) opacity {}".format(layer, frame_pos, x, y, opacity))
						ptr += 2
						cel['linked'] = frame_pos

					elif cel_type == 2:
						(w, h) = struct.unpack("HH", data[ptr:ptr+4])
						ptr += 4
						# print("   cel: layer {} ({},{}) ({}, {}) opacity {}".format(layer, x, y, w, h, opacity))
						pixels = zlib.decompress(data[ptr:next_chunk])
						cel['w'] = w
						cel['h'] = h
						cel['pixels'] = pixels

					# if pixels:
					# 	dump_pixels(pixels, w, h, transp)

					frame['cels'].append(cel)

				ptr = next_chunk
		
			sprite['frames'].append(frame)

	return sprite

def dump_pixels(pixels, w, h, transp):
	i = 0
	palette = ' .\'`^",:;Il!i><#'
	for py in range(0, h):
		print("      ", end='')
		for px in range(0, w):
			if pixels[i] == transp:
				print('.' * 2, end='')
			else:
				print(palette[pixels[i]] * 2, end='')
			i += 1
		print("")

def write_aseprite_file(path, sprite):
	data = bytearray(b'\x00') * 1024 * 100		# FIXME: bad - should extend array, but lazy with zero bytes
	ptr = 4		# patch data size at the end

	# header
	if sprite['indexed']:
		cdepth = 8
	else:
		cdepth = 32

	struct.pack_into('=HHHHHIHIIBBBBHBB', data, ptr, 0xA5E0, len(sprite['frames']), sprite['w'], sprite['h'], cdepth, 1, sprite['speed'], 0, 0, sprite['trans'], 0, 0, 0, len(sprite['palette']), 0, 0)
	ptr += 124

	# frames
	first_frame = True
	for frame in sprite['frames']:
		frame_size_ptr = ptr
		ptr += 4

		struct.pack_into('=HHHBBI', data, ptr, 0xF1FA, 0, frame['duration'], 0, 0, 0)
		chunk_count = 0
		chunk_count_ptr = ptr + 2
		ptr += 12
		
		if first_frame:
			# palette
			if sprite['indexed']:
				chunk_size_ptr = ptr
				ptr += 4
				struct.pack_into('=HIII', data, ptr, 0x2019, len(sprite['palette']), 0, len(sprite['palette']) - 1)
				ptr += 14 + 8

				for p in sprite['palette']:
					struct.pack_into('=HBBBB', data, ptr, 0, p[0], p[1], p[2], 255)
					ptr += 6

				struct.pack_into('=I', data, chunk_size_ptr, ptr - chunk_size_ptr)
				chunk_count += 1

			# tags

			if 'tags' in sprite:
				chunk_size_ptr = ptr
				ptr += 4
				struct.pack_into('=HH', data, ptr, 0x2018, len(sprite['tags']))
				ptr += 4 + 8
				
				for t in sprite['tags']:
					struct.pack_into('=HHB', data, ptr, t['from'], t['to'], t['loop_dir'])
					ptr += 5 + 8 + 3 + 1
					struct.pack_into('=H', data, ptr, len(t['name']))
					ptr += 2
					data[ptr:ptr+len(t['name'])] = bytearray(t['name'], 'utf-8')
					ptr += len(t['name'])

				struct.pack_into('=I', data, chunk_size_ptr, ptr - chunk_size_ptr)
				chunk_count += 1

			if 'layers' in sprite:
				for layer in sprite['layers']:
					chunk_size_ptr = ptr
					ptr += 4
					struct.pack_into('=H', data, ptr, 0x2004)
					ptr += 2
					
					struct.pack_into('=HHHHHHB', data, ptr, layer['flags'], layer['type'], layer['child_level'], 0, 0, layer['blend_mode'], layer['opacity'])
					ptr += 13 + 3
					struct.pack_into('=H', data, ptr, len(layer['name']))
					ptr += 2
					data[ptr:ptr+len(layer['name'])] = bytearray(layer['name'], 'utf-8')
					ptr += len(layer['name'])

					struct.pack_into('=I', data, chunk_size_ptr, ptr - chunk_size_ptr)
					chunk_count += 1

		# cels

		for cel in frame['cels']:
			chunk_size_ptr = ptr
			ptr += 4

			if 'linked' in cel:
				cel_type = 1
			else:
				cel_type = 2
			struct.pack_into('=HHhhBH', data, ptr, 0x2005, cel['layer'], cel['x'], cel['y'], cel['opacity'], cel_type)
			ptr += 11 + 7
			
			if cel_type == 1:
				struct.pack_into('=H', data, ptr, cel['linked'])
				ptr += 2
			else:
				struct.pack_into('=HH', data, ptr, cel['w'], cel['h'])
				ptr += 4
				compressed = zlib.compress(cel['pixels'])
				data[ptr:ptr+len(compressed)] = compressed
				ptr += len(compressed)

			struct.pack_into('=I', data, chunk_size_ptr, ptr - chunk_size_ptr)
			chunk_count += 1

		# patch counts
		struct.pack_into('=H', data, chunk_count_ptr, chunk_count)
		struct.pack_into('=I', data, frame_size_ptr, ptr - frame_size_ptr)

		first_frame = False

	# patch data size
	struct.pack_into('=I', data, 0, ptr)

	file = open(path, 'wb')
	file.write(data[:ptr]);
	file.close()

