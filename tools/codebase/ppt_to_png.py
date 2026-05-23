#!/usr/bin/env python3
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "numpy>=2.4.4",
#     "pillow>=12.2.0",
# ]
# ///
"""
PPT to PNG Converter
Converts custom PPT binary format files to PNG images.
"""

import struct
import sys
import argparse
from pathlib import Path
from PIL import Image
import numpy as np


class PPTConverter:
    """Converter for custom PPT binary format to PNG."""
    
    TYPE_RGBA_5551 = 1
    TYPE_RGBA_4444 = 2
    TYPE_RGBA_8888 = 3
    TYPE_INDEX_4BPP = 4
    TYPE_INDEX_8BPP = 5
    
    def __init__(self, filepath, use_tiling=True, crop_to_content=True):
        self.filepath = Path(filepath)
        self.use_tiling = use_tiling
        self.crop_to_content = crop_to_content
        self.data = self._read_file()
        self.offset = 0
        
    def _read_file(self):
        """Read the entire PPT file into memory."""
        with open(self.filepath, 'rb') as f:
            return f.read()
    
    def _read_bytes(self, size):
        """Read specified number of bytes and advance offset."""
        result = self.data[self.offset:self.offset + size]
        self.offset += size
        return result
    
    def _read_short(self):
        """Read a short (2 bytes) as little-endian."""
        return struct.unpack('<H', self._read_bytes(2))[0]
    
    def _read_int(self):
        """Read an int (4 bytes) as little-endian."""
        return struct.unpack('<I', self._read_bytes(4))[0]
    
    def _read_magic(self, expected):
        """Read and verify magic bytes."""
        magic = self._read_bytes(len(expected))
        if magic != expected:
            raise ValueError(f"Invalid magic bytes. Expected {expected}, got {magic}")
        return magic
    
    def parse_header(self):
        """Parse the PPT header structure."""
        # Read magic "ppt\x00"
        self._read_magic(b'ppt\x00')
        
        # Read header fields
        gpu_width = self._read_short()
        gpu_height = self._read_short()
        img_type = self._read_short()
        count = self._read_short()
        tex_width = self._read_short()
        tex_height = self._read_short()
        content_width = self._read_short()
        content_height = self._read_short()
        reserved0 = self._read_int()
        pointer_to_palette = self._read_int()
        reserved1 = self._read_int()

        assert reserved0 == 0 and reserved1 == 0, "texture reserved are not 0"
        
        return {
            'gpu_width': gpu_width,
            'gpu_height': gpu_height,
            'type': img_type,
            'count': count,
            'tex_width': tex_width,
            'tex_height': tex_height,
            'content_width': content_width,
            'content_height': content_height,
            'reserved0': reserved0,
            'pointer_to_palette': pointer_to_palette,
            'reserved1': reserved1,
        }
    
    def parse_palette(self, palette_offset, type):
        """Parse the palette structure if present."""
        if palette_offset == 0:
            return None
        
        # Save current offset and jump to palette
        saved_offset = self.offset
        self.offset = palette_offset
        
        # Read palette header
        self._read_magic(b'ppc\x00')
        pal_type = self._read_short()

        assert pal_type == 3, "Invalid palette Storage Mode"
        pal_count = self._read_short()
        reserved0 = self._read_int()
        reserved1 = self._read_int()

        assert reserved0 == 0 and reserved1 == 0, "palette reserved are not 0"

        # Read palette data (256 colors x 4 bytes RGBA)
        palette_data = self._read_bytes(pal_count * 32)
        
        # Restore offset
        self.offset = saved_offset

        if type == self.TYPE_INDEX_8BPP:
            print(f"  Palette: 256 colors")
            palette_data += b"\x00" * ((256 * 4) - (pal_count * 32))

            # Convert to numpy array
            palette = np.frombuffer(palette_data, dtype=np.uint8).reshape(256, 4)
        else:
            print(f"  Palette: 16 colors")
            palette_data += b"\x00" * ((16 * 4) - (pal_count * 32))
            
            # Convert to numpy array
            palette = np.frombuffer(palette_data, dtype=np.uint8).reshape(16, 4)

        return palette
    
    def _detile_rgba5551(self, data, width, height):
        """Detile RGBA5551 format with 8x8 pixel tiles."""
        # RGBA5551 uses 8x8 pixel tiles
        tile_width = 8
        tile_height = 8
        bytes_per_pixel = 2

        # Create output array
        output = np.zeros((height, width, 4), dtype=np.uint8)

        # Calculate number of tiles
        tiles_x = (width + tile_width - 1) // tile_width
        tiles_y = (height + tile_height - 1) // tile_height

        offset = 0
        for ty in range(tiles_y):
            for tx in range(tiles_x):
                # Calculate tile boundaries
                x_start = tx * tile_width
                y_start = ty * tile_height
                x_end = min(x_start + tile_width, width)
                y_end = min(y_start + tile_height, height)

                # Read pixels in this tile
                for y in range(y_start, y_end):
                    for x in range(x_start, x_end):
                        # Read RGBA values
                        val = (data[offset + 1] << 8) | data[offset + 0]
                        r = ((val >>  0) & 0b11111)
                        g = ((val >>  5) & 0b11111)
                        b = ((val >> 10) & 0b11111)
                        r = (r << 3) | (r >> 2)
                        g = (g << 3) | (g >> 2)
                        b = (b << 3) | (b >> 2)
                        a = 0xFF if ((val >> 15) & 1) != 0 else 0
                        output[y, x] = [r, g, b, a]
                        offset += bytes_per_pixel

        return output

    def _detile_rgba4444(self, data, width, height):
        """Detile RGBA4444 format with 8x8 pixel tiles."""
        # RGBA4444 uses 8x8 pixel tiles
        tile_width = 8
        tile_height = 8
        bytes_per_pixel = 2

        # Create output array
        output = np.zeros((height, width, 4), dtype=np.uint8)

        # Calculate number of tiles
        tiles_x = (width + tile_width - 1) // tile_width
        tiles_y = (height + tile_height - 1) // tile_height

        offset = 0
        for ty in range(tiles_y):
            for tx in range(tiles_x):
                # Calculate tile boundaries
                x_start = tx * tile_width
                y_start = ty * tile_height
                x_end = min(x_start + tile_width, width)
                y_end = min(y_start + tile_height, height)

                # Read pixels in this tile
                for y in range(y_start, y_end):
                    for x in range(x_start, x_end):
                        # Read RGBA values
                        val = (data[offset + 1] << 8) | data[offset + 0]
                        r = (val >>  0) & 0b1111
                        g = (val >>  4) & 0b1111
                        b = (val >>  8) & 0b1111
                        a = (val >> 12) & 0b1111
                        r = (r << 4) | r
                        g = (g << 4) | g
                        b = (b << 4) | b
                        a = (a << 4) | a
                        output[y, x] = [r, g, b, a]
                        offset += bytes_per_pixel

        return output

    def _detile_rgba8888(self, data, width, height):
        """Detile RGBA8888 format with 4x8 pixel tiles."""
        # RGBA8888 uses 4x8 pixel tiles
        tile_width = 4
        tile_height = 8
        bytes_per_pixel = 4
        
        # Create output array
        output = np.zeros((height, width, 4), dtype=np.uint8)
        
        # Calculate number of tiles
        tiles_x = (width + tile_width - 1) // tile_width
        tiles_y = (height + tile_height - 1) // tile_height
        
        offset = 0
        for ty in range(tiles_y):
            for tx in range(tiles_x):
                # Calculate tile boundaries
                x_start = tx * tile_width
                y_start = ty * tile_height
                x_end = min(x_start + tile_width, width)
                y_end = min(y_start + tile_height, height)
                
                # Read pixels in this tile
                for y in range(y_start, y_end):
                    for x in range(x_start, x_end):
                        # Read RGBA values
                        r = data[offset]
                        g = data[offset + 1]
                        b = data[offset + 2]
                        a = data[offset + 3]
                        output[y, x] = [r, g, b, a]
                        offset += bytes_per_pixel
        
        return output
    
    def _detile_index4(self, data, width, height):
        """Detile INDEX4 format with 16x8 pixel tiles."""
        # INDEX4 uses 32x8 pixel tiles
        tile_width = 32
        tile_height = 8

        # Create output array
        output = np.zeros((height, width), dtype=np.uint8)

        # Calculate number of tiles
        tiles_x = (width + tile_width - 1) // tile_width
        tiles_y = (height + tile_height - 1) // tile_height

        offset = 0
        for ty in range(tiles_y):
            for tx in range(tiles_x):
                # Calculate tile boundaries
                x_start = tx * tile_width
                y_start = ty * tile_height
                x_end = min(x_start + tile_width, width)
                y_end = min(y_start + tile_height, height)

                # Read pixels in this tile
                for y in range(y_start, y_end):
                    for x in range(x_start, x_end):
                        if offset & 1:
                            output[y, x] = (data[offset // 2] >> 4) & 0xF
                        else:
                            output[y, x] = data[offset // 2] & 0xF
                        offset += 1

        return output
    
    def _detile_index8(self, data, width, height):
        """Detile INDEX8 format with 16x8 pixel tiles."""
        # INDEX8 uses 16x8 pixel tiles
        tile_width = 16
        tile_height = 8
        
        # Create output array
        output = np.zeros((height, width), dtype=np.uint8)
        
        # Calculate number of tiles
        tiles_x = (width + tile_width - 1) // tile_width
        tiles_y = (height + tile_height - 1) // tile_height
        
        offset = 0
        for ty in range(tiles_y):
            for tx in range(tiles_x):
                # Calculate tile boundaries
                x_start = tx * tile_width
                y_start = ty * tile_height
                x_end = min(x_start + tile_width, width)
                y_end = min(y_start + tile_height, height)
                
                # Read pixels in this tile
                for y in range(y_start, y_end):
                    for x in range(x_start, x_end):
                        output[y, x] = data[offset]
                        offset += 1
        
        return output
    
    def read_image_data(self, header):
        """Read the raw image data based on type."""
        # Use texture dimensions for reading full data, then crop if needed
        tex_width = header['tex_width']
        tex_height = header['tex_height']
        content_width = header['content_width']
        content_height = header['content_height']
        
        # Determine which dimensions to use for reading
        if self.crop_to_content:
            width = content_width
            height = content_height
        else:
            width = tex_width
            height = tex_height
        
        img_type = header['type']
        
        if img_type == self.TYPE_RGBA_5551:
            # RGBA 5551 - 2 bytes per pixel
            size = width * height * 2
            image_data = self._read_bytes(size)

            if self.use_tiling:
                # Tiled 8x8
                return self._detile_rgba5551(image_data, width, height)
            else:
                # Linear/raw format
                return np.frombuffer(image_data, dtype=np.uint8).reshape(
                    height, width, 2
                )
        elif img_type == self.TYPE_RGBA_4444:
            # RGBA 4444 - 2 bytes per pixel
            size = width * height * 2
            image_data = self._read_bytes(size)

            if self.use_tiling:
                # Tiled 8x8
                return self._detile_rgba4444(image_data, width, height)
            else:
                # Linear/raw format
                return np.frombuffer(image_data, dtype=np.uint8).reshape(
                    height, width, 2
                )
        elif img_type == self.TYPE_RGBA_8888:
            # RGBA 8888 - 4 bytes per pixel
            size = width * height * 4
            image_data = self._read_bytes(size)

            if self.use_tiling:
                # Tiled 4x8
                return self._detile_rgba8888(image_data, width, height)
            else:
                # Linear/raw format
                return np.frombuffer(image_data, dtype=np.uint8).reshape(
                    height, width, 4
                )

        elif img_type == self.TYPE_INDEX_4BPP:
            # Indexed 4bpp - 1 byte per 2 pixel
            size = width * height // 2
            image_data = self._read_bytes(size)

            if self.use_tiling:
                # Tiled 32x8
                return self._detile_index4(image_data, width, height)
            else:
                # Linear/raw format
                return np.frombuffer(image_data, dtype=np.uint8).reshape(height, width)

        elif img_type == self.TYPE_INDEX_8BPP:
            # Indexed 8bpp - 1 byte per pixel
            size = width * height
            image_data = self._read_bytes(size)

            if self.use_tiling:
                # Tiled 16x8
                return self._detile_index8(image_data, width, height)
            else:
                # Linear/raw format
                return np.frombuffer(image_data, dtype=np.uint8).reshape(height, width)

        else:
            raise ValueError(f"Unsupported image type: {img_type}")
    
    def convert_to_png(self, output_path=None):
        """Convert PPT file to PNG."""
        # Parse header
        header = self.parse_header()
        
        print(f"PPT Header:")
        print(f"  GPU Size: {header['gpu_width']}x{header['gpu_height']}")
        print(f"  Texture Size: {header['tex_width']}x{header['tex_height']}")
        print(f"  Content Size: {header['content_width']}x{header['content_height']}")
        
        type_str = "Unknown"
        tile_str = ""
        if header["type"] == 1:
            type_str = "RGBA 5551"
            if self.use_tiling:
                tile_str = " (8x8 tiles)"
        elif header["type"] == 2:
            type_str = "RGBA 4444"
            if self.use_tiling:
                tile_str = " (8x8 tiles)"
        elif header["type"] == 3:
            type_str = "RGBA 8888"
            if self.use_tiling:
                tile_str = " (4x8 tiles)"
        elif header["type"] == 4:
            type_str = "INDEX 4bpp"
            if self.use_tiling:
                tile_str = " (32x8 tiles)"
        elif header["type"] == 5:
            type_str = "INDEX 8bpp"
            if self.use_tiling:
                tile_str = " (16x8 tiles)"
        
        print(f"  Type: {header['type']} ({type_str}{tile_str})")
        print(f"  Tiling: {'Enabled' if self.use_tiling else 'Disabled'}")
        print(f"  Crop to Content: {'Enabled' if self.crop_to_content else 'Disabled'}")
        
        if self.crop_to_content:
            print(f"  Output Size: {header['content_width']}x{header['content_height']}")
        else:
            print(f"  Output Size: {header['tex_width']}x{header['tex_height']}")
        
        # Read image data
        image_data = self.read_image_data(header)
        
        # Handle indexed color images
        if header['type'] in (self.TYPE_INDEX_4BPP, self.TYPE_INDEX_8BPP):
            palette = self.parse_palette(header['pointer_to_palette'], header['type'])
            if palette is None:
                raise ValueError("Indexed image requires a palette, but none was found")
            
            # Apply palette to create RGBA image
            rgba_image = palette[image_data]
            image_data = rgba_image
        
        # Create PIL Image
        img = Image.fromarray(image_data, mode='RGBA')
        
        # Determine output path
        if output_path is None:
            output_path = self.filepath.with_suffix('.png')
        else:
            output_path = Path(output_path)
        
        # Save as PNG
        img.save(output_path, 'PNG')
        print(f"\nSaved to: {output_path}")
        
        return output_path


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Convert custom PPT binary format files to PNG images.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s input.ppt                    # Convert with tiling and crop to content (default)
  %(prog)s input.ppt output.png         # Specify output filename
  %(prog)s input.ppt --no-tiling        # Convert without detiling
  %(prog)s input.ppt --no-crop          # Use full texture size instead of content size
        """
    )
    
    parser.add_argument('input', help='Input PPT file')
    parser.add_argument('output', nargs='?', help='Output PNG file (default: input filename with .png extension)')
    parser.add_argument('--no-tiling', action='store_true', 
                       help='Disable tiling/detiling (read pixels in linear order)')
    parser.add_argument('--no-crop', action='store_true',
                       help='Use full texture size instead of cropping to content boundary')
    
    args = parser.parse_args()
    
    try:
        converter = PPTConverter(args.input, 
                                use_tiling=not args.no_tiling,
                                crop_to_content=not args.no_crop)
        converter.convert_to_png(args.output)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
