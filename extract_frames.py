# code used from https://github.com/dobrokot/clip_to_psd

import re
import io
import os
import sqlite3
import logging
import zlib
from collections import namedtuple
from functools import cmp_to_key
from argparse import Namespace
from io import BytesIO
from PIL import Image
from types import SimpleNamespace  # for a lightweight Namespace replacement

BlockDataBeginChunk = 'BlockDataBeginChunk'.encode('UTF-16BE')
BlockDataEndChunk = 'BlockDataEndChunk'.encode('UTF-16BE')
BlockStatus = 'BlockStatus'.encode('UTF-16BE')
BlockCheckSum = 'BlockCheckSum'.encode('UTF-16BE')
ChunkInfo = namedtuple("ChunkInfo", ("layer_str", "chunk_info_filename", "bitmap_blocks"))

def sort_tuples_with_nones(tuples):
    def cmp_tuples_with_none(aa, bb):
        assert len(aa) == len(bb)
        for a, b in zip(aa, bb):
            if a != b:
                if a == None:
                    return -1
                if b == None:
                    return 1
                return (-1 if (a < b) else +1)
        return 0 # equal tuples
    return sorted(tuples, key = cmp_to_key(cmp_tuples_with_none))


def read_csp_int_maybe(f):
    t = f.read(4)
    if len(t) != 4:
        return None
    return int.from_bytes(t, 'big')

def read_csp_unicode_str(f):
    str_size = read_csp_int_maybe(f)
    if str_size == None:
        return None
    string_data = f.read(2 * str_size)
    return string_data.decode('UTF-16-BE')

def parse_offscreen_attributes_sql_value(offscreen_attribute):
    b_io = io.BytesIO(offscreen_attribute)
    def get_next_int(): return int.from_bytes(b_io.read(4), 'big')
    def check_read_str(s):
        s2 = read_csp_unicode_str(b_io)
        assert s2 == s

    header_size = get_next_int()
    assert header_size == 16, (header_size, repr(offscreen_attribute))
    info_section_size = get_next_int()
    assert info_section_size == 102
    extra_info_section_size = get_next_int()
    assert extra_info_section_size in (42, 58), (extra_info_section_size, repr(offscreen_attribute))
    get_next_int()

    check_read_str("Parameter")
    bitmap_width = get_next_int()
    bitmap_height = get_next_int()
    block_grid_width = get_next_int()
    block_grid_height = get_next_int()

    attributes_arrays = [get_next_int() for _i in range(16)]

    check_read_str("InitColor")
    get_next_int()
    default_fill_black_white = get_next_int()
    get_next_int()
    get_next_int()

    get_next_int()

    init_color = [0] * 4
    if (extra_info_section_size == 58):
        init_color = [min(255, get_next_int() // (256**3)) for _i in range(4)]

    return [
        bitmap_width, bitmap_height,
        block_grid_width, block_grid_height,
        default_fill_black_white,
        attributes_arrays,
        init_color
    ]

def decode_to_img(offscreen_attribute, bitmap_blocks): 
    from PIL import Image

    parsed_offscreen_attributes = parse_offscreen_attributes_sql_value(offscreen_attribute)
    bitmap_width, bitmap_height, block_grid_width, block_grid_height, default_fill_black_white, pixel_packing_params, _init_color = parsed_offscreen_attributes

    first_packing_channel_count = pixel_packing_params[1]
    second_packing_channel_count = pixel_packing_params[2]
    packing_type = (first_packing_channel_count, second_packing_channel_count)
    channel_count_sum = sum(packing_type)
    assert packing_type == (1, 4) or (channel_count_sum == 1), packing_type
    assert block_grid_width * block_grid_height == len(bitmap_blocks)

    if packing_type == (1, 4):
        default_fill = (255,255,255,255) if default_fill_black_white else (0,0,0,0)
        img = Image.new("RGBA", (bitmap_width, bitmap_height), default_fill)
    else:
        assert channel_count_sum == 1
        default_fill = 255 if default_fill_black_white else 0
        img = Image.new("L", (bitmap_width, bitmap_height), default_fill)

    for i in range(block_grid_height):
        for j in range(block_grid_width):
            block = bitmap_blocks[i*block_grid_width + j]
            if block:
                try:
                    pixel_data_bytes = zlib.decompress(block)
                except:
                    if not cmd_args.ignore_zlib_errors:
                        logging.error("can't unpack block data with zlib, --ignore-zlib-errors can be used to ignore errors")
                        raise
                    else:
                        logging.debug("can't unpack block data with zlib")
                    continue
                pixel_data = memoryview(pixel_data_bytes)
                k = 256*256
                if packing_type == (1, 4):
                    if len(pixel_data) != 5*k:
                        logging.error("invalid pixel count for 4-channel block, expected 5*256*256, got %s", len(pixel_data))
                        continue
                    block_img_alpha = Image.frombuffer("L", (256, 256), pixel_data[0:k], 'raw')
                    block_img_rgbx = Image.frombuffer("RGBA", (256, 256), pixel_data[k:5*k], 'raw')
                    b,g,r, _ = block_img_rgbx.split()
                    a, = block_img_alpha.split()
                    block_result_img = Image.merge("RGBA", (r,g,b,a))
                else:
                    if len(pixel_data) != k:
                        logging.error("invalid pixel count for 1-channel block, expected 256*256, got %s", len(pixel_data))
                        continue
                    # this branch won't run until masks be saved as png
                    block_result_img = Image.frombuffer("L", (256, 256), pixel_data[0:k], 'raw')
                img.paste(block_result_img, (256*j, 256*i))
    return img

def decode_layer_to_png(offscreen_attribute, bitmap_blocks):
    img = decode_to_img(offscreen_attribute, bitmap_blocks)
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='png', compress_level=1)
    return img_byte_arr.getvalue()

def save_layers_as_png(chunks, out_dir, sqlite_info):
    #ComicFrameLineMipmap LayerLayerMaskMipmap LayerRenderMipmap ResizableOriginalMipmap TimeLineOriginalMaskMipmap TimeLineOriginalMipmap"
    mipmapinfo_dict = { m.MainId:m for m in sqlite_info.mipmapinfo_sqlite_info }
    mipmap_dict     = { m.MainId:m for m in sqlite_info.mipmap_sqlite_info }
    offscreen_dict  = { m.MainId:m for m in sqlite_info.offscreen_chunks_sqlite_info }

    referenced_chunks_data = {}

    for l in sqlite_info.layer_sqlite_info:
        mipmap_id = l.LayerRenderMipmap
        if mipmap_id != None:
            external_block_row = offscreen_dict[mipmapinfo_dict[mipmap_dict[mipmap_id].BaseMipmapInfo].Offscreen]
            external_id = external_block_row.BlockData
            chunk_info = chunks.get(external_id)
            if chunk_info != None:
                #c.layer_name
                referenced_chunks_data[external_id] = (external_block_row.Attribute, chunk_info)
                #offscreen_chunks_sqlite_info.setdefault(external_id, []).append(l.MainId)

    for external_id, (offscreen_attribute, chunk_info) in sorted(referenced_chunks_data.items()):
        png_data = decode_layer_to_png(offscreen_attribute, chunk_info.bitmap_blocks)
        chunk_info_filename = chunks[external_id].chunk_info_filename
        assert chunk_info_filename.endswith('.png')
        logging.info(os.path.join(out_dir, chunk_info_filename))
        with open(os.path.join(out_dir, chunk_info_filename), 'wb') as f:
            f.write(png_data)
            
def parse_chunk_with_blocks(d):
    ii = 0
    block_count1 = 0
    bitmap_blocks = []
    while ii < len(d):
        if d[ii:ii+4+len(BlockStatus)] == b'\0\0\0\x0b' + BlockStatus:
            status_count = int.from_bytes(d[ii+26+4:ii+30+4], 'big')
            if block_count1 != status_count:
                logging.warning("mismatch in block count in layer blocks parsing, %s != %s", block_count1, status_count)
            block_size = status_count * 4 + 12 + (len(BlockStatus)+4)
        elif d[ii:ii+4+len(BlockCheckSum)] == b'\0\0\0\x0d' + BlockCheckSum:
            block_size = 4+len(BlockCheckSum) + 12 + block_count1*4
        elif d[ii+8:ii+8+len(BlockDataBeginChunk)] == BlockDataBeginChunk:
            block_size = int.from_bytes(d[ii:ii+4], 'big')
            expected = b'\0\0\0\x11' + BlockDataEndChunk
            read_data = d[ii+block_size-(4+len(BlockDataEndChunk)):ii+block_size]
            if read_data != expected:
                logging.error("can't parse bitmap chunk, %s != %s", repr(bytes(read_data)), repr(expected))
                return None

            block = d[ii+8+len(BlockDataBeginChunk):ii+block_size-(4+len(BlockDataEndChunk))]
            # 1) first int32 of block contains index of subblock,
            # 2,3,4) then 3 of some unknown in32 parameters,
            # 5) then 0 for empty block or 1 if present.
            # If present, then:
            # 6) size of subblock data in big endian plus 4,
            # 7) then size of subblock in little endian.
            # After these 4*7 bytes actual compressed data follows.

            has_data = int.from_bytes(block[4*4:4*5], 'big')
            if not (0 <= has_data <= 1):
                logging.error("can't parse bitmap chunk (invalid block format, a), %s", repr(has_data))
                return None
            if has_data:
                subblock_len = int.from_bytes(block[5*4:6*4], 'big')
                if not (len(block)  == subblock_len + 4*6):
                    logging.error("can't parse bitmap chunk (invalid block format, b), %s", repr((len(block), subblock_len + 5*6)))
                    return None
                    
                subblock_data = block[7*4:]
                bitmap_blocks.append(subblock_data)
            else:
                bitmap_blocks.append(None)

            block_count1 += 1
        else:
            logging.error("can't recognize %s when parsing subblocks in bitmap layer at %s", repr(d[ii:ii+50]), ii)
            return None

        ii += block_size
    if len(d) != ii:
        logging.warning("invalid last block size, overflow %s by %s", len(d), ii)
    return bitmap_blocks

def extract_csp_chunks_data(file_chunks_list, out_dir, chunk_to_layers, layer_names):
    if out_dir:
        for f in os.listdir(out_dir):
            if f.startswith('chunk_'):
                os.unlink(os.path.join(out_dir, f))

    chunks = {}

    for chunk_name, chunk_data_memory_view, chunk_offset in file_chunks_list:
        chunk_data_size = len(chunk_data_memory_view)
        if chunk_name == b'Exta':
            chunk_name_length = int.from_bytes(chunk_data_memory_view[:+8], 'big')
            if not chunk_name_length == 40:
                logging.warning("warning, unusual chunk name length=%s, usualy it's 40", chunk_name_length)
            chunk_id = bytes(chunk_data_memory_view[8:8+chunk_name_length])
            if chunk_id[0:8] != b'extrnlid':
                logging.warning('%s', f"warning, unusual chunk name, expected name starting with 'extrnlid' {repr(chunk_id)}")

            logging.debug('%s '*7, chunk_name.decode('ascii'), 'chunk_data_size:', chunk_data_size, 'offset:', chunk_offset, 'id:', chunk_id.decode('ascii'))
            chunk_size2 = int.from_bytes(chunk_data_memory_view[chunk_name_length+8:chunk_name_length+8+8], 'big')
            if not(chunk_data_size == chunk_size2 + 16 + chunk_name_length ):
                logging.warning('%s', f"warning, unusual second chunk size value, expected ({chunk_data_size=}) = ({chunk_size2=}) + 16 + ({chunk_name_length=}) ")
            
            chunk_binary_data = chunk_data_memory_view[chunk_name_length+8+8:]

            bitmap_blocks = None
            if chunk_binary_data[8:8+len(BlockDataBeginChunk)] == BlockDataBeginChunk:
                bitmap_blocks = parse_chunk_with_blocks(chunk_binary_data)
                if bitmap_blocks == None:
                    logging.error("can't parse bitmap id=%s block at %s", repr(chunk_id), chunk_offset)
                    continue
                    
                ext='png'
            else:
                ext = 'bin'

            # vector data export is not implemented, so disable it's extraction
            #elif 'vector' in chunk_main_types:
            #    chunk_txt_info = io.StringIO()
            #    k = 22*4
            #    for i in range(1 + (len(chunk_binary_data)-1) // k):
            #        print(chunk_binary_data[i*k:(i+1)*k].hex(' ', 4), file=chunk_txt_info)
            #    chunk_output_data = chunk_txt_info.getvalue().encode('UTF-8')

            if not re.match(b'^[a-zA-Z0-9_-]+$', chunk_id):
                logging.warning("unusual chunk_id=%s", repr(chunk_id))

            layer_num_str = '_'.join(f'{id:03d}' for id in chunk_to_layers.get(chunk_id, []))
            def make_layer_name_for_file(id):
                layer_name = layer_names.get(id, f'no-name-{id}').strip()
                if not layer_name:
                    layer_name = '{empty}'
                layer_name_sanitized = re.sub(r'''[\0-\x1f'"/\\:*?<>| ]''', '_', layer_name)[0:80]
                return layer_name_sanitized

            layer_name_str = ','.join(make_layer_name_for_file(id) for id in chunk_to_layers.get(chunk_id, []))
            layer_name_str = '[' + layer_name_str + ']'

            chunk_info_filename = f'chunk_{layer_num_str}_{chunk_id.decode("ascii")}_{layer_name_str}.{ext}'
            # side effect - save non-bitmape binary data chunks information
            if chunk_binary_data != None and out_dir and not bitmap_blocks:
                with open(os.path.join(out_dir, chunk_info_filename), 'wb') as f:
                    f.write(chunk_binary_data)

            chunks[chunk_id] = ChunkInfo(layer_name_str, chunk_info_filename, bitmap_blocks)
        else:
            logging.debug('%s '*5, chunk_name.decode('ascii'), 'chunk_data_size:', chunk_data_size, 'offset:', chunk_offset)

    return chunks

def execute_query_global(conn, query, namedtuple_name = "X"):
    cursor = conn.cursor()
    cursor.execute(query)
    # get column names (nameduple forbids underscore '_' at start of name).
    column_names = [description[0].removeprefix('_') for description in cursor.description]
    table_row_tuple_type = namedtuple(namedtuple_name, column_names)
    # Fetch all results and convert them to named tuples

    results = [table_row_tuple_type(*row) for row in cursor.fetchall()]
    return sort_tuples_with_nones(results)# easier to keep stability in stdout and reduce diff clutter

def get_database_columns(conn):
    tables = one_column(execute_query_global(conn, "SELECT name FROM sqlite_schema WHERE type == 'table' ORDER BY name"))

    table_columns = {}
    for t in tables:
        if not re.match('^[a-zA-Z0-9_.]+$', t):
            continue
        table_columns[t] = one_column(execute_query_global(conn, f"SELECT name FROM pragma_table_info('{t}')  WHERE type <> '' order by name"))

    return table_columns

def one_column(rows):
    assert all(len(row) == 1 for row in rows)
    return [row[0] for row in rows]

def get_sql_data_layer_chunks():
    db_path = os.path.join(cmd_args.sqlite_file)

    query_offscreen_chunks = 'SELECT MainId, LayerId, BlockData, Attribute from Offscreen;'  # LayerId is used to have layer id for layer chunk types I have no interest (thumbs, smaller mipmaps)
    # it's easier to SELECT */getattr than to try to deal with non-existing columns with exactly same result.
    # "FilterLayerInfo" is optional, maybe some other fields are optional too.
    #layer_attributes = 'MainId, CanvasId, LayerName, LayerType, LayerComposite, LayerOpacity, LayerClip, FilterLayerInfo,
    #    LayerLayerMaskMipmap, LayerRenderMipmap,
    #    LayerVisibility, LayerLock,  LayerMasking,
    #    LayerOffsetX, LayerOffsetY, LayerRenderOffscrOffsetX, LayerRenderOffscrOffsetY,
    #    LayerMaskOffsetX, LayerMaskOffsetY, LayerMaskOffscrOffsetX, LayerMaskOffscrOffsetY,
    #    LayerSelect, LayerFirstChildIndex, LayerNextIndex'.replace(',', ' ').split()
    #
    #    table_columns_lowercase = { key.lower() : [c.lower() for c in val] for key, val in table_columns }
    #    layer_existing_columns = table_columns_lowercase['layer']
    #    layer_sql_query_columns = ','.join( x if x.lower() in layer_extra_section else 'NULL' for layer_attributes )
    #    query_layer = f'SELECT {layer_sqlite_info} FROM Layer'
    query_layer = 'SELECT * FROM Layer;'

    query_mipmap = 'SELECT MainId, BaseMipmapInfo from Mipmap'
    query_mipmap_info = 'SELECT MainId, Offscreen from MipmapInfo' # there is NextIndex to get mipmap chain information, but lower mipmpas are not needed for export.
    query_vector_chunks = 'SELECT MainId, VectorData, LayerId from VectorObjectList'

    with sqlite3.connect(db_path) as conn:
        table_columns = get_database_columns(conn)

        def execute_query(conn, query, namedtuple_name,  optional_table = None):
            if optional_table:
                if optional_table not in table_columns:
                    return []
            return execute_query_global(conn,  query, namedtuple_name)

        offscreen_chunks_sqlite_info = execute_query(conn, query_offscreen_chunks, 'OffscreenChunksTuple')
        layer_sqlite_info = execute_query(conn, query_layer, 'LayerTuple')
        mipmap_sqlite_info = execute_query(conn, query_mipmap, 'MipmapChainHeader')
        mipmapinfo_sqlite_info = execute_query(conn, query_mipmap_info, 'MipmapLevelInfo')
        vector_info = execute_query(conn, query_vector_chunks, 'VectorChunkTuple', optional_table = "VectorObjectList")
        #dump_database_chunk_links_structure_info(conn)

        #pylint: disable=too-many-instance-attributes
        class SqliteInfo:
            def __init__(self):
                self.offscreen_chunks_sqlite_info = offscreen_chunks_sqlite_info
                self.layer_sqlite_info = layer_sqlite_info
                self.mipmap_sqlite_info = mipmap_sqlite_info
                self.mipmapinfo_sqlite_info = mipmapinfo_sqlite_info
                self.vector_info = vector_info
                self.canvas_preview_data = one_column(execute_query_global(conn, 'SELECT ImageData FROM CanvasPreview'))
                self.root_folder = one_column(execute_query_global(conn, 'SELECT CanvasRootFolder FROM Canvas'))[0]
                self.width, self.height, self.dpi = execute_query_global(conn, 'SELECT CanvasWidth, CanvasHeight, CanvasResolution from Canvas')[0]
        result = SqliteInfo()
    conn.close()
    return result

def iterate_file_chunks(data, filename):
    file_header_size = 24
    file_header = data[0:file_header_size]
    if not(b'CSFCHUNK' == file_header[0:8]):
        raise ValueError(f"can't recognize Clip Studio file '{filename}', {repr(data[0:30])}")
    chunk_offset = file_header_size
    t = data[file_header_size:file_header_size+4] 
    if not (t == b'CHNK'):
        raise ValueError(f"can't find first chunk in Clip Studio file after header, '{filename}', {repr(t)}")

    file_chunks_list = []

    while chunk_offset < len(data):
        t = data[chunk_offset:chunk_offset+4] 
        if not (t == b'CHNK'):
            raise ValueError(f"can't find next chunk in Clip Studio file after header, '{filename}', {repr(t)}")
        chunk_header = data[chunk_offset:chunk_offset+4*4]
        chunk_name = chunk_header[4:8]
        zero1 = chunk_header[8:12]
        size_bin = chunk_header[12:16]
        if zero1 != b'\0'*4: 
            logging.warning('interesting, not zero %s %s %s', repr(chunk_name), filename, repr(zero1))
        chunk_data_size = int.from_bytes(size_bin, 'big')

        chunk_data_memory_view = memoryview(data)[chunk_offset+16:chunk_offset+16+chunk_data_size]
        file_chunks_list.append( (chunk_name, chunk_data_memory_view, chunk_offset) )

        chunk_offset += 16 + chunk_data_size

    return file_chunks_list

def extract_csp(filename, output_dir=None):
    with open(filename, 'rb') as f:
        data = f.read()

    file_chunks_list = iterate_file_chunks(data, filename)
    for chunk_name, chunk_data_memory_view, _chunk_offset in file_chunks_list:
        if chunk_name == b'SQLi':
            logging.info('writing .clip sqlite database at "%s"', cmd_args.sqlite_file)
            with open(cmd_args.sqlite_file, 'wb') as f:
                f.write(chunk_data_memory_view)

    sqlite_info = get_sql_data_layer_chunks()

    id2layer = { l.MainId:l for l in sqlite_info.layer_sqlite_info }
    layer_ordered = [ ]
    def print_layer_folders(folder_id, depth):
        folder = id2layer[folder_id]
        current_id = folder.LayerFirstChildIndex
        while current_id:
            l = id2layer[current_id]
            is_subfolder = l.LayerFolder != 0
            logging.info('%s %s', (depth*4)*' ' + ('*' if is_subfolder else ' '), l.LayerName)
            if is_subfolder:
                layer_ordered.append(('lt_folder_start', None))
                print_layer_folders(current_id, depth + 1)
                layer_ordered.append(('lt_folder_end', l))
            else:
                layer_ordered.append(('lt_bitmap', l))
            current_id = l.LayerNextIndex

    if cmd_args.output_psd or cmd_args.output_dir:
        logging.info('Layers names in tree:')
        print_layer_folders(sqlite_info.root_folder, 0)

    chunk_to_layers = {}
    for ofs in sqlite_info.offscreen_chunks_sqlite_info:
        chunk_to_layers.setdefault(ofs.BlockData, set()).add(ofs.LayerId)
    for v in sqlite_info.vector_info:
        chunk_to_layers.setdefault(v.VectorData, set()).add(v.LayerId)
    for k, v in chunk_to_layers.items():
        chunk_to_layers[k] = sorted(v)
    layer_names = {}
    for layer in sqlite_info.layer_sqlite_info:
        layer_names[layer.MainId] = layer.LayerName

    chunks = extract_csp_chunks_data(file_chunks_list, output_dir, chunk_to_layers, layer_names)
    
    if cmd_args.output_dir:
        save_layers_as_png(chunks, output_dir, sqlite_info)
        #TODO: json with layer structure?..

# Initialize global variable for the command line result object
cmd_args = None

import tempfile
from types import SimpleNamespace

def extract_layers(clip_file, output_dir=None):
    """
    Extract layers from a .clip file into PNGs.
    If output_dir is None, uses a temporary folder.
    Returns:
        output_dir (str): folder containing PNGs
        temp_dir (TemporaryDirectory or None): keep alive while using PNGs
    """
    temp_dir_created = False
    if output_dir is None:
        temp_dir = tempfile.TemporaryDirectory()
        output_dir = temp_dir.name
        temp_dir_created = True
    else:
        os.makedirs(output_dir, exist_ok=True)

    # --- Initialize cmd_args for extract_csp ---
    global cmd_args
    cmd_args = SimpleNamespace(
        sqlite_file=f"{output_dir}/temp.sqlite",  # temporary sqlite file
        output_dir=output_dir,
        output_psd=False,
        ignore_zlib_errors=True
    )

    # Main extraction
    extract_csp(clip_file, output_dir=output_dir)

    return output_dir, temp_dir if temp_dir_created else None



extract_layers("fox.clip")