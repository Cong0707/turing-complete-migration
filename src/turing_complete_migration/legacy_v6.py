"""Direct conversion between the 0.x version-6 and current version-15 formats.

The legacy component enum was replaced without an on-disk migration table.
Consequently, current builds interpret version-6 component numbers using the
new enum and abort parsing as soon as a legacy custom component is reached.
This module parses the old enum explicitly and writes a complete version-15
container that no longer depends on the game's broken version-6 loader.

The binary layouts are derived from Stuffe/save_monger, which is published as
CC0. Its bundled SuperSnappy implementation is MIT licensed. No upstream code
is copied verbatim; the format is reimplemented with Python's struct module.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
import struct

from .snappy import compress_raw, decompress_raw


LEGACY_VERSION = 6
CURRENT_VERSION = 15
DIRECT_ENUM_VERSIONS = {7, 9, 10}
SUPPORTED_INPUT_VERSIONS = {LEGACY_VERSION, *DIRECT_ENUM_VERSIONS, CURRENT_VERSION}
CUSTOM_OFFSET = (15, 15)
TELEPORT_WIRE = 0x20

DIRECTIONS = (
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
    (0, -1),
    (1, -1),
)


class SaveFormatError(ValueError):
    """Raised when a circuit is malformed or uses an unsupported feature."""


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def _take(self, size: int) -> bytes:
        end = self.offset + size
        if size < 0 or end > len(self.data):
            raise SaveFormatError(
                f"truncated payload at offset {self.offset}: need {size} byte(s)"
            )
        result = self.data[self.offset:end]
        self.offset = end
        return result

    def unpack(self, fmt: str):
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self._take(size))[0]

    def u8(self) -> int:
        return self.unpack("<B")

    def bool(self) -> bool:
        return self.u8() != 0

    def i16(self) -> int:
        return self.unpack("<h")

    def u16(self) -> int:
        return self.unpack("<H")

    def u32(self) -> int:
        return self.unpack("<I")

    def i64(self) -> int:
        return self.unpack("<q")

    def u64(self) -> int:
        return self.unpack("<Q")

    def point(self) -> tuple[int, int]:
        return (self.i16(), self.i16())

    def string(self) -> str:
        data = self._take(self.u16())
        # save_monger stores Nim strings as raw bytes. Most game strings are
        # UTF-8, but legacy program metadata can contain arbitrary bytes.
        # surrogateescape keeps such strings byte-for-byte reversible.
        return data.decode("utf-8", errors="surrogateescape")

    def bytes_u16(self) -> bytes:
        return self._take(self.u16())

    def int_sequence(self) -> list[int]:
        return [self.i64() for _ in range(self.u16())]

    def finish(self) -> None:
        if self.offset != len(self.data):
            raise SaveFormatError(
                f"{len(self.data) - self.offset} trailing byte(s) after circuit payload"
            )


class _Writer:
    def __init__(self):
        self.data = bytearray()

    def add(self, fmt: str, value: int) -> None:
        self.data.extend(struct.pack(fmt, value))

    def u8(self, value: int) -> None:
        self.add("<B", value)

    def bool(self, value: bool) -> None:
        self.u8(1 if value else 0)

    def i16(self, value: int) -> None:
        self.add("<h", value)

    def u16(self, value: int) -> None:
        self.add("<H", value)

    def u32(self, value: int) -> None:
        self.add("<I", value)

    def i64(self, value: int) -> None:
        self.add("<q", value)

    def u64(self, value: int) -> None:
        self.add("<Q", value)

    def point(self, value: tuple[int, int]) -> None:
        self.i16(value[0])
        self.i16(value[1])

    def string(self, value: str) -> None:
        data = value.encode("utf-8", errors="surrogateescape")
        if len(data) > 0xFFFF:
            raise SaveFormatError("string is too long for the save format")
        self.u16(len(data))
        self.data.extend(data)

    def bytes_u16(self, value: bytes) -> None:
        if len(value) > 0xFFFF:
            raise SaveFormatError("byte sequence is too long for the save format")
        self.u16(len(value))
        self.data.extend(value)

    def int_sequence(self, values: list[int]) -> None:
        if len(values) > 0xFFFF:
            raise SaveFormatError("integer sequence is too long for the save format")
        self.u16(len(values))
        for value in values:
            self.i64(value)


@dataclass(frozen=True)
class LegacyComponent:
    kind: int
    position: tuple[int, int]
    rotation: int
    permanent_id: int
    custom_string: str
    setting_1: int
    setting_2: int
    ui_order: int
    custom_id: int = 0
    custom_displacement: tuple[int, int] = (0, 0)
    selected_programs: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LegacyWire:
    kind: int
    color: int
    comment: str
    start: tuple[int, int]
    segments: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class LegacyCircuit:
    save_id: int
    hub_id: int
    gate: int
    delay: int
    menu_visible: bool
    clock_speed: int
    dependencies: list[int]
    description: str
    camera_position: tuple[int, int]
    sync_state: int
    campaign_bound: bool
    score: int
    player_data: bytes
    hub_description: str
    components: list[LegacyComponent]
    wires: list[LegacyWire]


@dataclass(frozen=True)
class CurrentComponent:
    kind: int
    position: tuple[int, int]
    rotation: int
    permanent_id: int
    user_label: str
    custom_string: str
    settings: tuple[int, ...]
    buffer_size: int
    ui_order: int
    word_size: int
    immutable: bool = False
    cost_gate: int = -1
    cost_delay: int = 0
    little_endian: bool = False
    init_data: int = 0
    linked_components: tuple[tuple[int, int, str, int, int], ...] = ()
    selected_programs: tuple[tuple[str, str], ...] = ()
    custom_id: int = 0
    custom_word_sizes: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class CurrentWire:
    color: int
    comment: str
    start: tuple[int, int]
    segments: tuple[tuple[int, int], ...]
    legacy_teleport: bool = False


@dataclass(frozen=True)
class CurrentCircuit:
    custom_id: int
    hub_id: int
    gate: int
    delay: int
    menu_visible: bool
    clock_speed: int
    dependencies: list[int]
    description: str
    sync_state: int
    score: int
    player_data: bytes
    hub_description: str
    design: bytes
    components: list[CurrentComponent]
    wires: list[CurrentWire]


@dataclass(frozen=True)
class ComponentMapping:
    target_kind: int
    word_size: int
    quality: str = "exact"
    note: str = ""


# Current ComponentKind values used by the converter.
COM_OFF = 1
COM_ON = 2
COM_NOT_BIT = 3
COM_AND_BIT = 4
COM_AND_3_BIT = 5
COM_NAND_BIT = 6
COM_OR_BIT = 7
COM_OR_3_BIT = 8
COM_NOR_BIT = 9
COM_XOR_BIT = 10
COM_XNOR_BIT = 11
COM_SWITCH_BIT = 12
COM_DELAY_BIT = 13
COM_REGISTER_BIT = 14
COM_FULL_ADDER = 15
COM_MAKER_BIT_8 = 16
COM_SPLITTER_BIT_8 = 17
COM_NOT_WORD = 18
COM_OR_WORD = 19
COM_AND_WORD = 20
COM_NAND_WORD = 21
COM_NOR_WORD = 22
COM_XOR_WORD = 23
COM_XNOR_WORD = 24
COM_SWITCH_WORD = 25
COM_EQUAL = 26
COM_LESS_U = 27
COM_LESS_S = 28
COM_NEG = 29
COM_ADD = 30
COM_MUL = 31
COM_DIV = 32
COM_LSL = 33
COM_LSR = 34
COM_ROL = 35
COM_ROR = 36
COM_ASR = 37
COM_COUNTER = 38
COM_REGISTER_WORD = 39
COM_LEVEL_OUTPUT_8_PIN = 40
COM_LEVEL_DELAY_GATE = 41
COM_MUX = 42
COM_DECODER_1 = 43
COM_DECODER_2 = 44
COM_DECODER_3 = 45
COM_CONSTANT = 46
COM_SPLITTER_WORD_2 = 47
COM_MAKER_WORD_2 = 48
COM_REGISTER_WORD_CONFIG = 50
COM_DELAY_WORD = 55
COM_LEVEL_GATE = 59
COM_LEVEL_INPUT_1_PIN = 60
COM_LEVEL_INPUT_WORD = 61
COM_LEVEL_INPUT_SWITCHED = 62
COM_LEVEL_INPUT_2_PIN = 63
COM_LEVEL_INPUT_3_PIN = 64
COM_LEVEL_INPUT_4_PIN = 65
COM_LEVEL_OUTPUT_1_PIN = 68
COM_LEVEL_OUTPUT_WORD = 69
COM_LEVEL_OUTPUT_SWITCHED = 70
COM_LEVEL_OUTPUT_2_PIN = 73
COM_LEVEL_OUTPUT_3_PIN = 74
COM_LEVEL_OUTPUT_4_PIN = 75
COM_LEVEL_OUTPUT_COUNTER = 77
COM_CUSTOM = 78
COM_CC_INPUT = 79
COM_CC_INPUT_BUFFER = 80
COM_CC_OUTPUT = 81
COM_PROBE_MEMORY_BIT = 82
COM_PROBE_MEMORY_WORD = 83
COM_PROBE_WIRE_BIT = 84
COM_PROBE_WIRE_WORD = 85
COM_HALT = 87
COM_SEGMENT_DISPLAY = 89
COM_STATIC_VALUE = 90
COM_SCREEN = 91
COM_TIME = 92
COM_KEYBOARD = 93
COM_STATIC_EVAL = 94
COM_MAKER_WORD_4 = 97
COM_MAKER_WORD_8 = 98
COM_SPLITTER_WORD_4 = 99
COM_SPLITTER_WORD_8 = 100
COM_STATIC_INDEXER = 101
COM_RAM = 118


# Current builds merge these immutable components from campaign/circuit.data at
# load time. Keeping the legacy copies in a user schematic creates duplicate
# level ports and can make the test compiler bind to the wrong Output object.
CURRENT_LEVEL_INTERFACE_KINDS = {
    COM_LEVEL_OUTPUT_8_PIN,
    COM_LEVEL_INPUT_1_PIN,
    COM_LEVEL_INPUT_WORD,
    COM_LEVEL_INPUT_SWITCHED,
    COM_LEVEL_INPUT_2_PIN,
    COM_LEVEL_INPUT_3_PIN,
    COM_LEVEL_INPUT_4_PIN,
    COM_LEVEL_OUTPUT_1_PIN,
    COM_LEVEL_OUTPUT_WORD,
    COM_LEVEL_OUTPUT_SWITCHED,
    COM_LEVEL_OUTPUT_2_PIN,
    COM_LEVEL_OUTPUT_3_PIN,
    COM_LEVEL_OUTPUT_4_PIN,
    COM_LEVEL_OUTPUT_COUNTER,
}


LEGACY_KIND_NAMES = {
    0: "Error", 1: "Off", 2: "On", 3: "Buffer1", 4: "Not", 5: "And",
    6: "And3", 7: "Nand", 8: "Or", 9: "Or3", 10: "Nor", 11: "Xor",
    12: "Xnor", 13: "Counter8", 14: "VirtualCounter8", 15: "Counter64",
    16: "VirtualCounter64", 17: "Ram8", 18: "VirtualRam8", 23: "Register8",
    24: "VirtualRegister8", 25: "Register8Red", 26: "VirtualRegister8Red",
    27: "Register8RedPlus", 28: "VirtualRegister8RedPlus", 29: "Register64",
    30: "VirtualRegister64", 31: "Switch8", 32: "Mux8", 33: "Decoder1",
    34: "Decoder3", 35: "Constant8", 36: "Not8", 37: "Or8", 38: "And8",
    39: "Xor8", 40: "Equal8", 43: "Neg8", 44: "Add8", 45: "Mul8",
    46: "Splitter8", 47: "Maker8", 48: "Splitter64", 49: "Maker64",
    50: "FullAdder", 51: "BitMemory", 52: "VirtualBitMemory", 54: "Decoder2",
    55: "Timing", 56: "NoteSound", 59: "Keyboard", 60: "FileLoader",
    61: "Halt", 62: "WireCluster", 63: "LevelScreen", 64: "Program8_1",
    65: "Program8_1Red", 68: "Program8_4", 69: "LevelGate", 70: "Input1",
    71: "LevelInput2Pin", 72: "LevelInput3Pin", 73: "LevelInput4Pin",
    74: "LevelInputConditions", 75: "Input8", 76: "Input64",
    77: "LevelInputCode", 78: "LevelInputArch", 79: "Output1",
    80: "LevelOutput1Sum", 81: "LevelOutput1Car", 84: "LevelOutput2Pin",
    85: "LevelOutput3Pin", 86: "LevelOutput4Pin", 87: "Output8",
    88: "Output64", 89: "LevelOutputArch", 90: "LevelOutputCounter",
    92: "Custom", 93: "VirtualCustom", 94: "Program", 95: "DelayLine1",
    96: "VirtualDelayLine1", 97: "Console", 98: "Shl8", 99: "Shr8",
    100: "Constant64", 101: "Not64", 102: "Or64", 103: "And64",
    104: "Xor64", 105: "Neg64", 106: "Add64", 107: "Mul64",
    108: "Equal64", 109: "LessU64", 110: "LessI64", 111: "Shl64",
    112: "Shr64", 113: "Mux64", 114: "Switch64", 115: "ProbeMemoryBit",
    116: "ProbeMemoryWord", 117: "AndOrLatch", 118: "NandNandLatch",
    119: "NorNorLatch", 120: "LessU8", 121: "LessI8", 122: "DotMatrixDisplay",
    123: "SegmentDisplay", 124: "Input16", 125: "Input32", 126: "Output16",
    127: "Output32", 133: "Buffer8", 134: "Buffer16", 135: "Buffer32",
    136: "Buffer64", 137: "ProbeWireBit", 138: "ProbeWireWord", 139: "Switch1",
    140: "Output1z", 141: "Output8z", 142: "Output16z", 143: "Output32z",
    144: "Output64z", 145: "Constant16", 146: "Not16", 147: "Or16",
    148: "And16", 149: "Xor16", 150: "Neg16", 151: "Add16", 152: "Mul16",
    153: "Equal16", 154: "LessU16", 155: "LessI16", 156: "Shl16",
    157: "Shr16", 158: "Mux16", 159: "Switch16", 160: "Splitter16",
    161: "Maker16", 162: "Register16", 163: "VirtualRegister16",
    164: "Counter16", 165: "VirtualCounter16", 166: "Constant32", 167: "Not32",
    168: "Or32", 169: "And32", 170: "Xor32", 171: "Neg32", 172: "Add32",
    173: "Mul32", 174: "Equal32", 175: "LessU32", 176: "LessI32",
    177: "Shl32", 178: "Shr32", 179: "Mux32", 180: "Switch32",
    181: "Splitter32", 182: "Maker32", 183: "Register32",
    184: "VirtualRegister32", 185: "Counter32", 186: "VirtualCounter32",
    187: "LevelOutput8z", 188: "Nand8", 189: "Nor8", 190: "Xnor8",
    191: "Nand16", 192: "Nor16", 193: "Xnor16", 194: "Nand32",
    195: "Nor32", 196: "Xnor32", 197: "Nand64", 198: "Nor64",
    199: "Xnor64", 200: "Ram", 201: "VirtualRam", 202: "RamLatency",
    203: "VirtualRamLatency", 204: "RamFast", 205: "VirtualRamFast",
    206: "Rom", 207: "VirtualRom", 208: "SolutionRom", 209: "VirtualSolutionRom",
    210: "DelayLine8", 211: "VirtualDelayLine8", 212: "DelayLine16",
    213: "VirtualDelayLine16", 214: "DelayLine32", 215: "VirtualDelayLine32",
    216: "DelayLine64", 217: "VirtualDelayLine64", 218: "RamDualLoad",
    219: "VirtualRamDualLoad", 220: "Hdd", 221: "VirtualHdd", 222: "Network",
    223: "Rol8", 224: "Rol16", 225: "Rol32", 226: "Rol64", 227: "Ror8",
    228: "Ror16", 229: "Ror32", 230: "Ror64", 231: "IndexerBit",
    232: "IndexerByte", 233: "DivMod8", 234: "DivMod16", 235: "DivMod32",
    236: "DivMod64", 237: "SpriteDisplay", 238: "ConfigDelay", 239: "Clock",
    240: "LevelInput1", 241: "LevelInput8", 242: "LevelOutput1",
    243: "LevelOutput8", 244: "Ashr8", 245: "Ashr16", 246: "Ashr32",
    247: "Ashr64", 248: "Bidirectional1", 249: "VirtualBidirectional1",
    250: "Bidirectional8", 251: "VirtualBidirectional8", 252: "Bidirectional16",
    253: "VirtualBidirectional16", 254: "Bidirectional32",
    255: "VirtualBidirectional32", 256: "Bidirectional64",
    257: "VirtualBidirectional64",
}


def _m(target: int, width: int, quality: str = "exact", note: str = "") -> ComponentMapping:
    return ComponentMapping(target, width, quality, note)


COMPONENT_MAP: dict[int, ComponentMapping] = {}


def _register(kinds: tuple[int, ...], target: int, width: int, quality: str = "exact", note: str = "") -> None:
    for kind in kinds:
        COMPONENT_MAP[kind] = _m(target, width, quality, note)


_register((1,), COM_OFF, 1)
_register((2,), COM_ON, 1)
_register((3,), COM_CC_INPUT_BUFFER, 1, "approximate", "legacy buffer replaced by input buffer")
_register((4,), COM_NOT_BIT, 1)
_register((5,), COM_AND_BIT, 1)
_register((6,), COM_AND_3_BIT, 1)
_register((7,), COM_NAND_BIT, 1)
_register((8,), COM_OR_BIT, 1)
_register((9,), COM_OR_3_BIT, 1)
_register((10,), COM_NOR_BIT, 1)
_register((11,), COM_XOR_BIT, 1)
_register((12,), COM_XNOR_BIT, 1)
_register((13, 14), COM_COUNTER, 8)
_register((15, 16), COM_COUNTER, 64)
_register((17, 18), COM_RAM, 8, "approximate", "legacy RAM port layout changed")
_register((23, 24, 25, 26, 27, 28), COM_REGISTER_WORD, 8, "approximate", "legacy register variants merged")
_register((29, 30), COM_REGISTER_WORD, 64)
_register((31,), COM_SWITCH_WORD, 8)
_register((32,), COM_MUX, 8)
_register((33,), COM_DECODER_1, 1)
_register((34,), COM_DECODER_3, 1)
_register((35,), COM_CONSTANT, 8)
_register((36,), COM_NOT_WORD, 8)
_register((37,), COM_OR_WORD, 8)
_register((38,), COM_AND_WORD, 8)
_register((39,), COM_XOR_WORD, 8)
_register((40,), COM_EQUAL, 8)
_register((43,), COM_NEG, 8)
_register((44,), COM_ADD, 8)
_register((45,), COM_MUL, 8)
_register((46,), COM_SPLITTER_BIT_8, 8)
_register((47,), COM_MAKER_BIT_8, 8)
_register((48,), COM_SPLITTER_WORD_8, 64)
_register((49,), COM_MAKER_WORD_8, 64)
_register((50,), COM_FULL_ADDER, 1)
_register((51, 52), COM_REGISTER_BIT, 1)
_register((54,), COM_DECODER_2, 1)
_register((55,), COM_TIME, 1, "approximate", "legacy timing component replaced by time")
_register((56,), COM_STATIC_VALUE, 1, "placeholder", "note sound has no current equivalent")
_register((59,), COM_KEYBOARD, 8)
_register((60,), COM_STATIC_EVAL, 8, "approximate", "file loader has no direct current equivalent")
_register((61,), COM_HALT, 1)
_register((62,), COM_STATIC_VALUE, 1, "placeholder", "wire cluster has no current equivalent")
_register((63,), COM_SCREEN, 1)
_register((64, 65), COM_RAM, 8, "approximate", "program component replaced by RAM")
_register((68,), COM_RAM, 8, "approximate", "program component replaced by RAM")
_register((69,), COM_LEVEL_GATE, 1)
_register((70,), COM_CC_INPUT, 1)
_register((71,), COM_LEVEL_INPUT_2_PIN, 1)
_register((72,), COM_LEVEL_INPUT_3_PIN, 1)
_register((73,), COM_LEVEL_INPUT_4_PIN, 1)
_register((74,), COM_LEVEL_INPUT_1_PIN, 1, "approximate", "conditions input layout changed")
_register((75,), COM_CC_INPUT, 8)
_register((76,), COM_CC_INPUT, 64)
_register((77,), COM_LEVEL_INPUT_WORD, 8)
_register((78,), COM_LEVEL_INPUT_SWITCHED, 64)
_register((79,), COM_CC_OUTPUT, 1)
_register((80, 81), COM_LEVEL_OUTPUT_1_PIN, 1, "approximate", "sum/carry outputs merged")
_register((84,), COM_LEVEL_OUTPUT_2_PIN, 1)
_register((85,), COM_LEVEL_OUTPUT_3_PIN, 1)
_register((86,), COM_LEVEL_OUTPUT_4_PIN, 1)
_register((87,), COM_CC_OUTPUT, 8)
_register((88,), COM_CC_OUTPUT, 64)
_register((89,), COM_LEVEL_OUTPUT_SWITCHED, 64)
_register((90,), COM_LEVEL_OUTPUT_COUNTER, 64)
_register((92, 93), COM_CUSTOM, 1)
_register((94,), COM_RAM, 64, "approximate", "program component replaced by RAM")
_register((95, 96), COM_DELAY_BIT, 1)
_register((97,), COM_STATIC_EVAL, 64, "approximate", "console replaced by static evaluator")
_register((98,), COM_LSL, 8)
_register((99,), COM_LSR, 8)

for base, width in ((100, 64), (145, 16), (166, 32)):
    _register((base,), COM_CONSTANT, width)
    _register((base + 1,), COM_NOT_WORD, width)
    _register((base + 2,), COM_OR_WORD, width)
    _register((base + 3,), COM_AND_WORD, width)
    _register((base + 4,), COM_XOR_WORD, width)
    _register((base + 5,), COM_NEG, width)
    _register((base + 6,), COM_ADD, width)
    _register((base + 7,), COM_MUL, width)
    _register((base + 8,), COM_EQUAL, width)
    _register((base + 9,), COM_LESS_U, width)
    _register((base + 10,), COM_LESS_S, width)
    _register((base + 11,), COM_LSL, width)
    _register((base + 12,), COM_LSR, width)
    _register((base + 13,), COM_MUX, width)
    _register((base + 14,), COM_SWITCH_WORD, width)

_register((115,), COM_PROBE_MEMORY_BIT, 1)
_register((116,), COM_PROBE_MEMORY_WORD, 64)
_register((117, 118, 119), COM_REGISTER_BIT, 1, "approximate", "legacy latch replaced by bit register")
_register((120,), COM_LESS_U, 8)
_register((121,), COM_LESS_S, 8)
_register((122,), COM_SCREEN, 8, "approximate", "dot matrix display replaced by screen")
_register((123,), COM_SEGMENT_DISPLAY, 8)
_register((124,), COM_CC_INPUT, 16)
_register((125,), COM_CC_INPUT, 32)
_register((126,), COM_CC_OUTPUT, 16)
_register((127,), COM_CC_OUTPUT, 32)
for old_kind, width in ((128, 1), (129, 8), (130, 16), (131, 32), (132, 64)):
    _register((old_kind,), COM_CC_INPUT_BUFFER, width, "approximate", "obsolete value represented a bidirectional component")
for old_kind, width in ((133, 8), (134, 16), (135, 32), (136, 64)):
    _register((old_kind,), COM_CC_INPUT_BUFFER, width, "approximate", "legacy buffer replaced by input buffer")
_register((137,), COM_PROBE_WIRE_BIT, 1)
_register((138,), COM_PROBE_WIRE_WORD, 64)
_register((139,), COM_SWITCH_BIT, 1)
for old_kind, width in ((140, 1), (141, 8), (142, 16), (143, 32), (144, 64)):
    _register((old_kind,), COM_CC_OUTPUT, width, "approximate", "tri-state output merged into current output")
_register((158,), COM_MUX, 16)
_register((159,), COM_SWITCH_WORD, 16)
_register((160,), COM_SPLITTER_WORD_2, 16)
_register((161,), COM_MAKER_WORD_2, 16)
_register((162, 163), COM_REGISTER_WORD, 16)
_register((164, 165), COM_COUNTER, 16)
_register((179,), COM_MUX, 32)
_register((180,), COM_SWITCH_WORD, 32)
_register((181,), COM_SPLITTER_WORD_4, 32)
_register((182,), COM_MAKER_WORD_4, 32)
_register((183, 184), COM_REGISTER_WORD, 32)
_register((185, 186), COM_COUNTER, 32)
_register((187,), COM_LEVEL_OUTPUT_8_PIN, 8, "approximate", "tri-state level output merged")
for old_kind, target, width in (
    (188, COM_NAND_WORD, 8), (189, COM_NOR_WORD, 8), (190, COM_XNOR_WORD, 8),
    (191, COM_NAND_WORD, 16), (192, COM_NOR_WORD, 16), (193, COM_XNOR_WORD, 16),
    (194, COM_NAND_WORD, 32), (195, COM_NOR_WORD, 32), (196, COM_XNOR_WORD, 32),
    (197, COM_NAND_WORD, 64), (198, COM_NOR_WORD, 64), (199, COM_XNOR_WORD, 64),
):
    _register((old_kind,), target, width)
for old_kind in range(200, 210):
    _register((old_kind,), COM_RAM, 64, "approximate", "legacy memory variants merged into RAM")
for old_kind, width in ((210, 8), (211, 8), (212, 16), (213, 16), (214, 32), (215, 32), (216, 64), (217, 64)):
    _register((old_kind,), COM_DELAY_WORD, width)
for old_kind in (218, 219, 220, 221):
    _register((old_kind,), COM_RAM, 64, "approximate", "legacy storage component replaced by RAM")
_register((222,), COM_STATIC_VALUE, 64, "placeholder", "network component has no current equivalent")
for old_kind, width in ((223, 8), (224, 16), (225, 32), (226, 64)):
    _register((old_kind,), COM_ROL, width)
for old_kind, width in ((227, 8), (228, 16), (229, 32), (230, 64)):
    _register((old_kind,), COM_ROR, width)
_register((231,), COM_STATIC_INDEXER, 1, "approximate", "indexer semantics changed")
_register((232,), COM_STATIC_INDEXER, 8, "approximate", "indexer semantics changed")
for old_kind, width in ((233, 8), (234, 16), (235, 32), (236, 64)):
    _register((old_kind,), COM_DIV, width, "approximate", "DivMod replaced by division; remainder output is not preserved")
_register((237,), COM_SCREEN, 8, "approximate", "sprite display replaced by screen")
_register((238,), COM_LEVEL_DELAY_GATE, 1, "approximate", "configurable delay component changed")
_register((239,), COM_TIME, 1)
_register((240,), COM_LEVEL_INPUT_1_PIN, 1)
_register((241,), COM_LEVEL_INPUT_WORD, 8)
_register((242,), COM_LEVEL_OUTPUT_1_PIN, 1)
_register((243,), COM_LEVEL_OUTPUT_8_PIN, 8)
for old_kind, width in ((244, 8), (245, 16), (246, 32), (247, 64)):
    _register((old_kind,), COM_ASR, width)
for old_kind, width in ((248, 1), (249, 1), (250, 8), (251, 8), (252, 16), (253, 16), (254, 32), (255, 32), (256, 64), (257, 64)):
    _register((old_kind,), COM_CC_INPUT_BUFFER, width, "approximate", "bidirectional component replaced by input buffer")


_DELETED_KINDS = {0, 19, 20, 21, 22, 41, 42, 53, 57, 58, 66, 67, 82, 83, 91}
_LEGACY_PROGRAM_KINDS = {64, 68, 94}
_CUSTOM_STRING_TARGETS = {COM_HALT, COM_STATIC_EVAL, COM_STATIC_INDEXER, COM_CONSTANT}
_RAM_LIKE_KINDS = set(range(200, 222)) | {17, 18, 64, 65, 68, 94}


def legacy_kind_name(kind: int) -> str:
    return LEGACY_KIND_NAMES.get(kind, f"legacy_kind_{kind}")


def _parse_legacy_component(reader: _Reader) -> LegacyComponent:
    kind = reader.u16()
    position = reader.point()
    rotation = reader.u8()
    permanent_id = reader.i64()
    custom_string = reader.string()
    setting_1 = reader.u64()
    setting_2 = reader.u64()
    ui_order = reader.i16()
    custom_id = 0
    custom_displacement = (0, 0)
    selected_programs: dict[int, str] = {}
    if kind == 92:
        custom_id = reader.i64()
        custom_displacement = reader.point()
    elif kind in _LEGACY_PROGRAM_KINDS:
        for _ in range(reader.u16()):
            key = reader.i64()
            selected_programs[key] = reader.string()
    return LegacyComponent(
        kind=kind,
        position=position,
        rotation=rotation,
        permanent_id=permanent_id,
        custom_string=custom_string,
        setting_1=setting_1,
        setting_2=setting_2,
        ui_order=ui_order,
        custom_id=custom_id,
        custom_displacement=custom_displacement,
        selected_programs=selected_programs,
    )


def _parse_legacy_wire(reader: _Reader) -> LegacyWire:
    kind = reader.u8()
    color = reader.u8()
    comment = reader.string()
    start = reader.point()
    first = reader.u8()
    if first == TELEPORT_WIRE:
        finish = reader.point()
        raise SaveFormatError(
            f"teleport wire from {start} to {finish} cannot be represented in version 15"
        )
    segments: list[tuple[int, int]] = []
    segment = first
    while segment & 0x1F:
        segments.append((segment >> 5, segment & 0x1F))
        segment = reader.u8()
    return LegacyWire(kind, color, comment, start, tuple(segments))


def parse_legacy_v6(data: bytes) -> LegacyCircuit:
    if not data or data[0] != LEGACY_VERSION:
        version = data[0] if data else None
        raise SaveFormatError(f"expected circuit version 6, got {version}")
    reader = _Reader(decompress_raw(data[1:]))
    save_id = reader.i64()
    hub_id = reader.u32()
    gate = reader.i64()
    delay = reader.i64()
    menu_visible = reader.bool()
    clock_speed = reader.u32()
    dependencies = reader.int_sequence()
    description = reader.string()
    camera_position = reader.point()
    sync_state = reader.u8()
    campaign_bound = reader.bool()
    score = reader.u16()
    player_data = reader.bytes_u16()
    hub_description = reader.string()
    component_count = reader.i64()
    components: list[LegacyComponent] = []
    for index in range(component_count):
        start = reader.offset
        try:
            components.append(_parse_legacy_component(reader))
        except SaveFormatError as exc:
            raise SaveFormatError(
                f"cannot parse legacy component {index} starting at offset {start} "
                f"after kinds {[item.kind for item in components]}: {exc}"
            ) from exc
    wire_count = reader.i64()
    wires: list[LegacyWire] = []
    for index in range(wire_count):
        start = reader.offset
        try:
            wires.append(_parse_legacy_wire(reader))
        except SaveFormatError as exc:
            raise SaveFormatError(
                f"cannot parse legacy wire {index} starting at offset {start}: {exc}"
            ) from exc
    circuit = LegacyCircuit(
        save_id=save_id,
        hub_id=hub_id,
        gate=gate,
        delay=delay,
        menu_visible=menu_visible,
        clock_speed=clock_speed,
        dependencies=dependencies,
        description=description,
        camera_position=camera_position,
        sync_state=sync_state,
        campaign_bound=campaign_bound,
        score=score,
        player_data=player_data,
        hub_description=hub_description,
        components=components,
        wires=wires,
    )
    reader.finish()
    return circuit


def _component_settings(component: LegacyComponent, mapping: ComponentMapping) -> tuple[int, ...]:
    if mapping.target_kind == COM_CONSTANT:
        return (component.setting_1,)
    if mapping.target_kind == COM_RAM:
        return (0, 0, 0)
    if mapping.target_kind == COM_CC_INPUT:
        return (component.setting_1 if component.setting_1 else 2,)
    if mapping.target_kind == COM_CC_OUTPUT:
        return (component.setting_1,)
    if mapping.target_kind == COM_LEVEL_GATE:
        return (component.setting_1,)
    if mapping.target_kind == COM_LEVEL_DELAY_GATE:
        return (component.setting_1, component.setting_2)
    if mapping.target_kind in {COM_SEGMENT_DISPLAY, COM_KEYBOARD, COM_STATIC_INDEXER}:
        return (component.setting_1,)
    return ()


def _program_key(key: int) -> str:
    # The old format keyed selected programs by numeric level IDs. Version 15
    # uses strings. Keeping the decimal ID is lossless and allows a later
    # campaign-aware mapping without discarding the original association.
    return str(key)


def convert_component(component: LegacyComponent) -> CurrentComponent | None:
    if component.kind in _DELETED_KINDS:
        return None
    mapping = COMPONENT_MAP.get(component.kind)
    if mapping is None:
        raise SaveFormatError(
            f"no mapping for component {legacy_kind_name(component.kind)} ({component.kind})"
        )
    x, y = component.position
    if component.kind == 92:
        x += component.custom_displacement[0] + CUSTOM_OFFSET[0]
        y += component.custom_displacement[1] + CUSTOM_OFFSET[1]

    if mapping.target_kind in _CUSTOM_STRING_TARGETS:
        user_label = ""
        custom_string = component.custom_string
    else:
        user_label = component.custom_string
        custom_string = ""

    buffer_size = 0
    if component.kind in _RAM_LIKE_KINDS:
        buffer_size = component.setting_1
        if buffer_size == 0:
            buffer_size = max(1, mapping.word_size // 8) * 256

    selected_programs = tuple(
        (_program_key(key), value)
        for key, value in sorted(component.selected_programs.items())
    )
    return CurrentComponent(
        kind=mapping.target_kind,
        position=(x, y),
        rotation=component.rotation,
        permanent_id=component.permanent_id,
        user_label=user_label,
        custom_string=custom_string,
        settings=_component_settings(component, mapping),
        buffer_size=buffer_size,
        ui_order=component.ui_order,
        word_size=mapping.word_size,
        selected_programs=selected_programs,
        custom_id=component.custom_id,
    )


def _strip_level_interfaces(
    circuit: CurrentCircuit,
    strip_level_interfaces: bool,
) -> tuple[CurrentCircuit, list[CurrentComponent]]:
    if not strip_level_interfaces:
        return circuit, []
    removed = [
        component
        for component in circuit.components
        if component.kind in CURRENT_LEVEL_INTERFACE_KINDS
    ]
    if not removed:
        return circuit, []
    kept = [
        component
        for component in circuit.components
        if component.kind not in CURRENT_LEVEL_INTERFACE_KINDS
    ]
    return replace(circuit, components=kept), removed


def convert_legacy_circuit(
    circuit: LegacyCircuit,
    *,
    strip_level_interfaces: bool | None = None,
) -> CurrentCircuit:
    components: list[CurrentComponent] = []
    for component in circuit.components:
        converted = convert_component(component)
        if converted is not None:
            components.append(converted)
    dependencies = sorted(
        {component.custom_id for component in components if component.kind == COM_CUSTOM and component.custom_id}
    )
    wires = [CurrentWire(w.color, w.comment, w.start, w.segments) for w in circuit.wires]
    current = CurrentCircuit(
        custom_id=circuit.save_id,
        hub_id=circuit.hub_id,
        gate=circuit.gate,
        delay=circuit.delay,
        menu_visible=circuit.menu_visible,
        clock_speed=circuit.clock_speed or 10_000_000,
        dependencies=dependencies,
        description=circuit.description,
        sync_state=circuit.sync_state,
        score=0,
        player_data=circuit.player_data,
        hub_description=circuit.hub_description,
        design=bytes(512) if circuit.save_id != 0 else b"",
        components=components,
        wires=wires,
    )
    if strip_level_interfaces is None:
        strip_level_interfaces = circuit.save_id == 0
    current, _ = _strip_level_interfaces(current, strip_level_interfaces)
    return current


def _write_current_component(writer: _Writer, component: CurrentComponent) -> None:
    writer.u16(component.kind)
    writer.point(component.position)
    writer.u8(component.rotation)
    writer.i64(component.permanent_id)
    writer.string(component.user_label)
    writer.string(component.custom_string)
    writer.u16(len(component.settings))
    for setting in component.settings:
        writer.u64(setting)
    writer.i64(component.buffer_size)
    writer.i16(component.ui_order)
    writer.i64(component.word_size)
    writer.bool(component.immutable)
    writer.i64(component.cost_gate)
    writer.i64(component.cost_delay)
    writer.bool(component.little_endian)
    writer.u8(component.init_data)
    writer.u16(len(component.linked_components))
    for permanent_id, inner_id, name, offset, word_size in component.linked_components:
        writer.i64(permanent_id)
        writer.i64(inner_id)
        writer.string(name)
        writer.i64(offset)
        writer.i64(word_size)
    writer.u16(len(component.selected_programs))
    for level, program in component.selected_programs:
        writer.string(level)
        writer.string(program)
    if component.kind == COM_CUSTOM:
        writer.i64(component.custom_id)
        writer.u16(len(component.custom_word_sizes))
        for permanent_id, word_size in component.custom_word_sizes:
            writer.i64(permanent_id)
            writer.i64(word_size)


def _write_current_wire(writer: _Writer, wire: CurrentWire) -> None:
    writer.u8(wire.color)
    writer.string(wire.comment)
    writer.point(wire.start)
    for direction, length in wire.segments:
        if not 0 <= direction <= 7 or not 1 <= length <= 0x1FFF:
            raise SaveFormatError(f"invalid version-15 wire segment ({direction}, {length})")
        writer.u16((direction << 13) | length)
    writer.u16(0)


def write_v15(circuit: CurrentCircuit) -> bytes:
    writer = _Writer()
    writer.i64(circuit.custom_id)
    writer.u32(circuit.hub_id)
    writer.i64(circuit.gate)
    writer.i64(circuit.delay)
    writer.bool(circuit.menu_visible)
    writer.u64(circuit.clock_speed)
    writer.int_sequence(circuit.dependencies)
    writer.string(circuit.description)
    writer.u8(circuit.sync_state)
    writer.u16(circuit.score)
    writer.bytes_u16(circuit.player_data)
    writer.string(circuit.hub_description)
    if circuit.custom_id != 0:
        if len(circuit.design) != 512:
            raise SaveFormatError("version-15 custom design must contain 512 bytes")
        writer.data.extend(circuit.design)
    writer.i64(len(circuit.components))
    for component in circuit.components:
        _write_current_component(writer, component)
    writer.i64(len(circuit.wires))
    for wire in circuit.wires:
        _write_current_wire(writer, wire)
    return bytes([CURRENT_VERSION]) + compress_raw(bytes(writer.data))


def _parse_current_component(reader: _Reader) -> CurrentComponent:
    kind = reader.u16()
    position = reader.point()
    rotation = reader.u8()
    permanent_id = reader.i64()
    user_label = reader.string()
    custom_string = reader.string()
    settings = tuple(reader.u64() for _ in range(reader.u16()))
    buffer_size = reader.i64()
    ui_order = reader.i16()
    word_size = reader.i64()
    immutable = reader.bool()
    cost_gate = reader.i64()
    cost_delay = reader.i64()
    little_endian = reader.bool()
    init_data = reader.u8()
    linked = tuple(
        (reader.i64(), reader.i64(), reader.string(), reader.i64(), reader.i64())
        for _ in range(reader.u16())
    )
    selected = tuple((reader.string(), reader.string()) for _ in range(reader.u16()))
    custom_id = 0
    custom_word_sizes: tuple[tuple[int, int], ...] = ()
    if kind == COM_CUSTOM:
        custom_id = reader.i64()
        custom_word_sizes = tuple((reader.i64(), reader.i64()) for _ in range(reader.u16()))
    return CurrentComponent(
        kind, position, rotation, permanent_id, user_label, custom_string,
        settings, buffer_size, ui_order, word_size, immutable, cost_gate,
        cost_delay, little_endian, init_data, linked, selected, custom_id,
        custom_word_sizes,
    )


def _parse_current_wire(reader: _Reader) -> CurrentWire:
    color = reader.u8()
    comment = reader.string()
    start = reader.point()
    segments: list[tuple[int, int]] = []
    while True:
        code = reader.u16()
        length = code & 0x1FFF
        if length == 0:
            break
        segments.append((code >> 13, length))
    return CurrentWire(color, comment, start, tuple(segments))


def _parse_byte_segment_path(
    reader: _Reader,
) -> tuple[tuple[int, int], tuple[tuple[int, int], ...], bool]:
    """Read the one-byte segment path shared by save versions 6 through 10."""

    start = reader.point()
    first = reader.u8()
    if first == TELEPORT_WIRE:
        reader.point()  # v15 cannot store the disconnected finish point
        return start, ((0, 1),), True
    segments: list[tuple[int, int]] = []
    segment = first
    while segment & 0x1F:
        segments.append((segment >> 5, segment & 0x1F))
        segment = reader.u8()
    return start, tuple(segments), False


def _parse_direct_enum_wire(reader: _Reader) -> CurrentWire:
    color = reader.u8()
    comment = reader.string()
    start, segments, legacy_teleport = _parse_byte_segment_path(reader)
    return CurrentWire(color, comment, start, segments, legacy_teleport)


_V7_SPECIAL_COMPONENTS = {
    COM_REGISTER_WORD_CONFIG,
    COM_PROBE_MEMORY_BIT,
    COM_PROBE_MEMORY_WORD,
    COM_STATIC_VALUE,
    88,  # com_deleted_1 in the direct enum
    COM_SCREEN,
}


def _read_selected_programs(reader: _Reader) -> tuple[tuple[str, str], ...]:
    return tuple((reader.string(), reader.string()) for _ in range(reader.u16()))


def _read_custom_word_sizes(reader: _Reader) -> tuple[tuple[int, int], ...]:
    return tuple((reader.i64(), reader.i64()) for _ in range(reader.u16()))


def _parse_direct_enum_component(reader: _Reader, version: int) -> CurrentComponent:
    kind = reader.u16()
    if kind > 124:
        raise SaveFormatError(
            f"version {version} component kind {kind} exceeds the current enum"
        )
    position = reader.point()
    rotation = reader.u8()
    permanent_id = reader.i64()
    label = reader.string()
    if kind in _CUSTOM_STRING_TARGETS:
        user_label, custom_string = "", label
    else:
        user_label, custom_string = label, ""
    settings = tuple(reader.u64() for _ in range(reader.u16()))
    buffer_size = reader.i64()
    ui_order = reader.i16()
    word_size = reader.i64()

    linked: list[tuple[int, int, str, int, int]] = []
    selected: tuple[tuple[str, str], ...] = ()
    custom_id = 0
    custom_word_sizes: tuple[tuple[int, int], ...] = ()

    if version == 7:
        reader.i64()  # obsolete parent permanent ID
        if kind == COM_CUSTOM:
            custom_id = reader.i64()
            custom_word_sizes = _read_custom_word_sizes(reader)
            for _ in range(reader.u16()):
                reader.i64()
                reader.i64()
        elif kind in _V7_SPECIAL_COMPONENTS:
            selected = _read_selected_programs(reader)
            for _ in range(reader.u16()):
                linked.append((reader.i64(), reader.i64(), reader.string(), 0, 0))
    else:
        for _ in range(reader.u16()):
            permanent = reader.i64()
            inner = reader.i64()
            name = reader.string()
            offset = reader.i64() if version >= 10 else 0
            linked.append((permanent, inner, name, offset, 0))
        selected = _read_selected_programs(reader)
        if kind == COM_CUSTOM:
            custom_id = reader.i64()
            custom_word_sizes = _read_custom_word_sizes(reader)

    return CurrentComponent(
        kind=kind,
        position=position,
        rotation=rotation,
        permanent_id=permanent_id,
        user_label=user_label,
        custom_string=custom_string,
        settings=settings,
        buffer_size=buffer_size,
        ui_order=ui_order,
        word_size=word_size,
        linked_components=tuple(linked),
        selected_programs=selected,
        custom_id=custom_id,
        custom_word_sizes=custom_word_sizes,
    )


def parse_direct_enum_version(data: bytes) -> CurrentCircuit:
    """Parse versions 7, 9, and 10, which already use the current enum."""

    if not data or data[0] not in DIRECT_ENUM_VERSIONS:
        version = data[0] if data else None
        raise SaveFormatError(f"expected circuit version 7, 9, or 10, got {version}")
    version = data[0]
    reader = _Reader(decompress_raw(data[1:]))
    custom_id = reader.i64()
    hub_id = reader.u32()
    gate = reader.i64()
    delay = reader.i64()
    menu_visible = reader.bool()
    clock_speed = reader.u64()
    original_dependencies = reader.int_sequence()
    description = reader.string()
    reader.point()  # obsolete camera position
    sync_state = reader.u8()
    score = reader.u16()
    player_data = reader.bytes_u16()
    hub_description = reader.string()

    component_count = reader.i64()
    if not 0 <= component_count <= 10_000_000:
        raise SaveFormatError(f"invalid version {version} component count {component_count}")
    components: list[CurrentComponent] = []
    for index in range(component_count):
        start = reader.offset
        try:
            components.append(_parse_direct_enum_component(reader, version))
        except SaveFormatError as exc:
            raise SaveFormatError(
                f"cannot parse version {version} component {index} at offset {start}: {exc}"
            ) from exc

    wire_count = reader.i64()
    if not 0 <= wire_count <= 100_000_000:
        raise SaveFormatError(f"invalid version {version} wire count {wire_count}")
    wires: list[CurrentWire] = []
    for index in range(wire_count):
        start = reader.offset
        try:
            wires.append(_parse_direct_enum_wire(reader))
        except SaveFormatError as exc:
            raise SaveFormatError(
                f"cannot parse version {version} wire {index} at offset {start}: {exc}"
            ) from exc
    reader.finish()

    dependencies = sorted(
        {component.custom_id for component in components if component.kind == COM_CUSTOM and component.custom_id}
    )
    if not dependencies:
        dependencies = original_dependencies
    return CurrentCircuit(
        custom_id=custom_id,
        hub_id=hub_id,
        gate=gate,
        delay=delay,
        menu_visible=menu_visible,
        clock_speed=clock_speed or 10_000_000,
        dependencies=dependencies,
        description=description,
        sync_state=sync_state,
        score=score,
        player_data=player_data,
        hub_description=hub_description,
        design=bytes(512) if custom_id != 0 else b"",
        components=components,
        wires=wires,
    )


def parse_v15(data: bytes) -> CurrentCircuit:
    if not data or data[0] != CURRENT_VERSION:
        version = data[0] if data else None
        raise SaveFormatError(f"expected circuit version 15, got {version}")
    reader = _Reader(decompress_raw(data[1:]))
    custom_id = reader.i64()
    hub_id = reader.u32()
    gate = reader.i64()
    delay = reader.i64()
    menu_visible = reader.bool()
    clock_speed = reader.u64()
    dependencies = reader.int_sequence()
    description = reader.string()
    sync_state = reader.u8()
    score = reader.u16()
    player_data = reader.bytes_u16()
    hub_description = reader.string()
    design = reader._take(512) if custom_id != 0 else b""
    components = [_parse_current_component(reader) for _ in range(reader.i64())]
    wires = [_parse_current_wire(reader) for _ in range(reader.i64())]
    reader.finish()
    return CurrentCircuit(
        custom_id, hub_id, gate, delay, menu_visible, clock_speed,
        dependencies, description, sync_state, score, player_data,
        hub_description, design, components, wires,
    )


def convert_v6_bytes(
    data: bytes,
    *,
    strip_level_interfaces: bool | None = None,
) -> tuple[bytes, dict[str, object]]:
    legacy = parse_legacy_v6(data)
    if strip_level_interfaces is None:
        strip_level_interfaces = legacy.save_id == 0
    unstripped = convert_legacy_circuit(legacy, strip_level_interfaces=False)
    current, removed_interfaces = _strip_level_interfaces(
        unstripped,
        strip_level_interfaces,
    )
    converted = write_v15(current)
    reparsed = parse_v15(converted)
    old_kinds = Counter(component.kind for component in legacy.components)
    mapped_qualities = Counter()
    replacements: list[dict[str, object]] = []
    removed_interface_kinds = Counter(component.kind for component in removed_interfaces)
    for kind, count in sorted(old_kinds.items()):
        if kind in _DELETED_KINDS:
            mapped_qualities["deleted"] += count
            replacements.append({
                "legacy_kind": kind,
                "legacy_name": legacy_kind_name(kind),
                "count": count,
                "quality": "deleted",
                "target_kind": None,
                "note": "obsolete enum value omitted",
            })
            continue
        mapping = COMPONENT_MAP[kind]
        if mapping.target_kind in removed_interface_kinds:
            mapped_qualities["campaign_runtime_interface"] += count
            replacements.append({
                "legacy_kind": kind,
                "legacy_name": legacy_kind_name(kind),
                "count": count,
                "quality": "campaign_runtime_interface",
                "target_kind": mapping.target_kind,
                "target_word_size": mapping.word_size,
                "note": "omitted because the current campaign injects this immutable level interface",
            })
            continue
        mapped_qualities[mapping.quality] += count
        if mapping.quality != "exact":
            replacements.append({
                "legacy_kind": kind,
                "legacy_name": legacy_kind_name(kind),
                "count": count,
                "quality": mapping.quality,
                "target_kind": mapping.target_kind,
                "target_word_size": mapping.word_size,
                "note": mapping.note,
            })
    report = {
        "source_version": LEGACY_VERSION,
        "output_version": CURRENT_VERSION,
        "source_component_count": len(legacy.components),
        "output_component_count": len(reparsed.components),
        "runtime_component_count": len(reparsed.components) + len(removed_interfaces),
        "stripped_level_interface_count": len(removed_interfaces),
        "stripped_level_interface_kind_counts": dict(sorted(removed_interface_kinds.items())),
        "source_wire_count": len(legacy.wires),
        "output_wire_count": len(reparsed.wires),
        "source_kind_counts": {
            f"{kind}:{legacy_kind_name(kind)}": count for kind, count in sorted(old_kinds.items())
        },
        "mapping_quality_counts": dict(sorted(mapped_qualities.items())),
        "replacements": replacements,
        "custom_component_count": sum(1 for item in reparsed.components if item.kind == COM_CUSTOM),
        "selected_program_entry_count": sum(len(item.selected_programs) for item in reparsed.components),
        "teleport_wire_approximation_count": 0,
        "verified_v15": True,
    }
    return converted, report


def convert_v6_file(source: Path, destination: Path) -> dict[str, object]:
    converted, report = convert_v6_bytes(source.read_bytes())
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(converted)
    return report


def convert_direct_enum_bytes(
    data: bytes,
    *,
    strip_level_interfaces: bool | None = None,
) -> tuple[bytes, dict[str, object]]:
    source_version = data[0] if data else None
    source_circuit = parse_direct_enum_version(data)
    if strip_level_interfaces is None:
        strip_level_interfaces = source_circuit.custom_id == 0
    circuit, removed_interfaces = _strip_level_interfaces(
        source_circuit,
        strip_level_interfaces,
    )
    converted = write_v15(circuit)
    reparsed = parse_v15(converted)
    kind_counts = Counter(component.kind for component in source_circuit.components)
    removed_interface_kinds = Counter(component.kind for component in removed_interfaces)
    exact_count = len(source_circuit.components) - len(removed_interfaces)
    mapping_quality = {"exact": exact_count}
    if removed_interfaces:
        mapping_quality["campaign_runtime_interface"] = len(removed_interfaces)
    report = {
        "source_version": source_version,
        "output_version": CURRENT_VERSION,
        "source_component_count": len(source_circuit.components),
        "output_component_count": len(reparsed.components),
        "runtime_component_count": len(reparsed.components) + len(removed_interfaces),
        "stripped_level_interface_count": len(removed_interfaces),
        "stripped_level_interface_kind_counts": dict(sorted(removed_interface_kinds.items())),
        "source_wire_count": len(source_circuit.wires),
        "output_wire_count": len(reparsed.wires),
        "source_kind_counts": dict(sorted(kind_counts.items())),
        "mapping_quality_counts": mapping_quality,
        "replacements": [],
        "custom_component_count": sum(
            1 for item in reparsed.components if item.kind == COM_CUSTOM
        ),
        "selected_program_entry_count": sum(
            len(item.selected_programs) for item in reparsed.components
        ),
        "teleport_wire_approximation_count": sum(
            1 for item in circuit.wires if item.legacy_teleport
        ),
        "verified_v15": True,
    }
    return converted, report


def convert_circuit_bytes(
    data: bytes,
    *,
    strip_level_interfaces: bool | None = None,
) -> tuple[bytes, dict[str, object]]:
    """Convert any supported legacy circuit to v15 and verify the result."""

    if not data:
        raise SaveFormatError("empty circuit file")
    version = data[0]
    if version == LEGACY_VERSION:
        return convert_v6_bytes(
            data,
            strip_level_interfaces=strip_level_interfaces,
        )
    if version in DIRECT_ENUM_VERSIONS:
        return convert_direct_enum_bytes(
            data,
            strip_level_interfaces=strip_level_interfaces,
        )
    if version == CURRENT_VERSION:
        source_circuit = parse_v15(data)
        if strip_level_interfaces is None:
            strip_level_interfaces = False
        circuit, removed_interfaces = _strip_level_interfaces(
            source_circuit,
            strip_level_interfaces,
        )
        converted = write_v15(circuit) if removed_interfaces else data
        removed_interface_kinds = Counter(component.kind for component in removed_interfaces)
        return converted, {
            "source_version": CURRENT_VERSION,
            "output_version": CURRENT_VERSION,
            "source_component_count": len(source_circuit.components),
            "output_component_count": len(circuit.components),
            "runtime_component_count": len(circuit.components) + len(removed_interfaces),
            "stripped_level_interface_count": len(removed_interfaces),
            "stripped_level_interface_kind_counts": dict(sorted(removed_interface_kinds.items())),
            "source_wire_count": len(source_circuit.wires),
            "output_wire_count": len(circuit.wires),
            "source_kind_counts": dict(
                sorted(Counter(item.kind for item in source_circuit.components).items())
            ),
            "mapping_quality_counts": {
                "already_current": len(circuit.components),
                **(
                    {"campaign_runtime_interface": len(removed_interfaces)}
                    if removed_interfaces
                    else {}
                ),
            },
            "replacements": [],
            "custom_component_count": sum(
                1 for item in circuit.components if item.kind == COM_CUSTOM
            ),
            "selected_program_entry_count": sum(
                len(item.selected_programs) for item in circuit.components
            ),
            "teleport_wire_approximation_count": 0,
            "verified_v15": True,
        }
    supported = ", ".join(str(item) for item in sorted(SUPPORTED_INPUT_VERSIONS))
    raise SaveFormatError(
        f"unsupported circuit version {version}; supported versions: {supported}"
    )


def convert_circuit_file(source: Path, destination: Path) -> dict[str, object]:
    converted, report = convert_circuit_bytes(source.read_bytes())
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(converted)
    return report


def current_circuit_summary(circuit: CurrentCircuit) -> dict[str, object]:
    return {
        "custom_id": circuit.custom_id,
        "component_count": len(circuit.components),
        "wire_count": len(circuit.wires),
        "kind_counts": dict(sorted(Counter(item.kind for item in circuit.components).items())),
        "components": [asdict(item) for item in circuit.components],
    }
