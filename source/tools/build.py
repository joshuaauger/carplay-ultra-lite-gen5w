#!/usr/bin/env python3
"""cp-climate M1: build the code segment and turn it into an HMG-API memory recipe.

Two stages, so the first can run on a CI runner that has no manufacturer files:

  build.py seg <build> <out dir> [variant] [--stock <libCarPlayCore.so>]
      Compiles native/seg.S + native/hooks.c for the head unit (Thumb-2, no libc, no relocations),
      links them as one block at SEG_VA and fills cpc_table (each entry = target in libCarPlayCore
      - address of cpc_table). Writes segment.bin and segment.json. Needs clang, ld.lld and
      pyelftools, and no library: a build whose PLT addresses are listed below needs no --stock.

  build.py recipe <stock libCarPlayCore.so> <HMG-API source> <out dir> [variant]
      Makes a patched copy of the stock library (the segment appended as a PT_LOAD at SEG_VA, a b.w
      into it at each hook site) and runs HMG-API's tools/mkmemrecipe.py on (stock, patched).
      Needs the stock library and Python only, and the out dir of the first stage.

  build.py <stock libCarPlayCore.so> <HMG-API source> <out dir> [variant]
      Both, the build picked by the library's MD5.

  build.py list                       the builds CI makes a segment for, as JSON (the CI matrix)
  build.py verify <build> <out dir>   CI: the committed recipe matches the segment just built

<build> is the first 8 digits of the library's MD5 (BUILDS below). Library copies from a car are
never committed: the recipe holds hashes and our own bytes only."""
import hashlib, json, os, struct, subprocess, sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
SEG_VA = 0x30000

# Table targets (cpc.h order): "@name" = a library vaddr from the build's "addr" (Thumb code
# with bit 0 set, GOT slots, data), any other string = a PLT entry by name.
TABLE = ["@orig_info", "@ret_info", "@ret_setup", "@logcat", "@got_dkey", "@got_dval", "@got_arr",
         "CFDictionaryGetValue", "CFDictionarySetValue", "CFRelease", "CFBinaryPlistV0CreateWithData",
         "CFArrayGetCount", "CFArrayGetValueAtIndex", "CFEqual", "CFArrayCreateMutable",
         "CFArrayAppendValue", "CFDictionaryCreateMutable", "CFDictionarySetInt64",
         "CFStringGetCStringPtr", "CFStringCreateWithCString", "LogPrintF", "CFGetTypeID",
         "CFArrayGetTypeID", "CFStringGetTypeID", "CFDictionaryGetTypeID",
         "CFBinaryPlistV0Create", "free", "CFDictionaryApplyFunction",
         "@ret_stream_stock", "@ret_stream_done", "@derive", "@add_stream_reply", "CFDictionaryGetInt64",
         "@cmd_typed", "@cmd_451", "@cmd_done",
         "dispatch_get_global_queue", "dispatch_async_f", "dispatch_sync_f", "HTTPMessageCreate",
         "HTTPHeader_InitRequest", "HTTPHeader_AddFieldF", "HTTPMessageSetBodyPtr", "HTTPClientSendMessage",
         "CFRetain", "malloc", "memcpy"]

BUILDS = {
    # CEEV.USA 260507 / CEEV.CAN 250818 / CEEV.CAN 260206 (the stock library isn't kept with the source)
    "d3a47296": dict(
        md5="d3a47296437df56fb1ffc7ac3dfca4cb",
        recipe_id="carplay-climate-m1",
        # hook sites: (vaddr, stock bytes, stub symbol)
        sites=[
            (0x9c20, "fff7ecfa", "cpc_stub_info"),     # bl AirPlayCopyServerInfo
            (0x12430, "dff8f007", "cpc_stub_setup"),   # ldr.w r0, [pc, #0x7f0]
            (0x11718, "fb487844", "cpc_stub_stream"),  # ldr r0, [pc, #0x3ec]; add r0, pc (unsupported stream type)
            (0xaf10, "81460028", "cpc_stub_command"),  # mov r9, r0; cmp r0, #0 (POST /command, after its "type")
        ],
        # the setup log (cp-setup-log 0.1.x): the phone's SETUP request printed at Notice with its plist.
        # Part of this recipe because HMG-API applies one recipe per library and mod (the first that fits).
        setup_log=[(0x10ef4, "1e2b", "322b"), (0x1254a, "1e21", "3221"), (0x12564, "0021", "0121"),
                   (0x12580, "1e22", "3222")],
        # variant f: DiPO's own version, as the phone hears it (/info sourceVersion constant, Bonjour srcvers
        # and the "Server: AirTunes/%s" header, the timing User-Agent), 320.17.6 -> LIVI's 950.7.1, in place
        version=[(0x19850, "3332302e31372e36", "3935302e372e3100"),
                 (0x1a238, "3332302e31372e36", "3935302e372e3100"),
                 (0x1d420, "3332302e31372e36", "3935302e372e3100")],
        addr=dict(orig_info=0x91fd, ret_info=0x9c25, ret_setup=0x12437, logcat=0x200c8,
                  got_dkey=0x1fb20, got_dval=0x1fb1c, got_arr=0x1fb24,
                  ret_stream_stock=0x1171d, ret_stream_done=0x11725, derive=0xf015, add_stream_reply=0xd59d,
                  cmd_typed=0xaf19, cmd_451=0xb6d1, cmd_done=0xaf6d),
        plt=None,                                      # read from the stock library (--stock)
        defines=[],                                    # /command: plist in r7, error slot [sp, #0x7c]
    ),
    # CEEV.CAN 260903 (head unit build CEEV.CAN.0000.V016.010.260903), library from the user's car
    "ef49c09b": dict(
        md5="ef49c09b7ab5eb72298f9973443b66b3",
        recipe_id="carplay-climate-m1-ef49c09b",
        sites=[
            (0x9c20, "fff7ecfa", "cpc_stub_info"),
            (0x124b8, "dff8f007", "cpc_stub_setup"),
            (0x117a0, "fb487844", "cpc_stub_stream"),
            (0xaf30, "81460028", "cpc_stub_command"),
        ],
        setup_log=[(0x10f7c, "1e2b", "322b"), (0x125d2, "1e21", "3221"), (0x125ec, "0021", "0121"),
                   (0x12608, "1e22", "3222")],
        version=[],
        addr=dict(orig_info=0x91fd, ret_info=0x9c25, ret_setup=0x124bf, logcat=0x200c8,
                  got_dkey=0x1fb20, got_dval=0x1fb1c, got_arr=0x1fb24,
                  ret_stream_stock=0x117a5, ret_stream_done=0x117ad, derive=0xf095, add_stream_reply=0xd61d,
                  cmd_typed=0xaf39, cmd_451=0xb913, cmd_done=0xaf8d),
        # PLT entry vaddrs: .plt 0x5c08 + 20 + 12 * (index in .rel.plt)
        plt=dict(CFDictionaryGetValue=0x60e4, CFDictionarySetValue=0x60f0, CFRelease=0x5c4c,
                 CFBinaryPlistV0CreateWithData=0x6168, CFArrayGetCount=0x5d18, CFArrayGetValueAtIndex=0x69fc,
                 CFEqual=0x5d60, CFArrayCreateMutable=0x6120, CFArrayAppendValue=0x5ea4,
                 CFDictionaryCreateMutable=0x60d8, CFDictionarySetInt64=0x6114, CFStringGetCStringPtr=0x6750,
                 CFStringCreateWithCString=0x678c, LogPrintF=0x5c64, CFGetTypeID=0x5e98,
                 CFArrayGetTypeID=0x5d00, CFStringGetTypeID=0x5d84, CFDictionaryGetTypeID=0x5d24,
                 CFBinaryPlistV0Create=0x5e2c, free=0x5d54, CFDictionaryApplyFunction=0x5eb0,
                 CFDictionaryGetInt64=0x5d3c, dispatch_get_global_queue=0x62e8, dispatch_async_f=0x62f4,
                 dispatch_sync_f=0x5dcc, HTTPMessageCreate=0x65ac, HTTPHeader_InitRequest=0x65b8,
                 HTTPHeader_AddFieldF=0x5e14, HTTPMessageSetBodyPtr=0x5dfc, HTTPClientSendMessage=0x65c4,
                 CFRetain=0x5d90, malloc=0x6234, memcpy=0x6618),
        # /command: the plist is in r8 (r7 is a string-table base), the error slot is [sp, #0x74]
        defines=["-DCPC_CMD_PLIST=r8", "-DCPC_CMD_ERR=0x74"],
    ),
}

# test variants (optional argument): which of M1's additions are compiled in
VARIANTS = {
    "full": [],                                                        # 0.1.0: everything
    "a": ["-DCPC_FEATURES=0"],                                         # /info only
    "b": ["-DCPC_INFO=0"],                                             # SETUP features only
    "c": ["-DCPC_CLUSTER=0"],                                          # both, no instrument panel
    "e": ["-DCPC_FEATURES=0", "-DCPC_PANELS=0"],                        # /info: vehicleStateProtocolInfo only
    "f": [],                                                           # everything, reported as 950.7.1
    "d": ["-DCPC_DIAG=1", "-DCPC_FEATURES=0"],                                       # /info stock; save what would be sent
}
ARM = ["--target=armv7a-linux-androideabi", "-mthumb", "-march=armv7-a", "-mfloat-abi=soft", "-Os",
       "-fPIC", "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-fno-unwind-tables",
       "-fno-asynchronous-unwind-tables", "-fno-jump-tables", "-fvisibility=hidden", "-fno-common", "-Wall", "-Wextra", "-Werror"]


def run(*a):
    subprocess.run([str(x) for x in a], check=True)


def plt_targets(elf_bytes):
    """name -> PLT entry vaddr, from .rel.plt order"""
    import io
    from elftools.elf.elffile import ELFFile
    e = ELFFile(io.BytesIO(elf_bytes))
    plt = e.get_section_by_name(".plt"); rel = e.get_section_by_name(".rel.plt")
    sym = e.get_section_by_name(".dynsym")
    out = {}
    for i, r in enumerate(rel.iter_relocations()):
        out[sym.get_symbol(r["r_info_sym"]).name] = plt["sh_addr"] + 20 + 12 * i
    return out


def bw(at, to):
    """Thumb-2 B.W (T4) at vaddr at to vaddr to"""
    off = (to & ~1) - (at + 4)
    assert -(1 << 24) <= off < (1 << 24) and off % 2 == 0
    s = 1 if off < 0 else 0
    imm = off & ((1 << 25) - 1)
    i1 = (imm >> 23) & 1; i2 = (imm >> 22) & 1
    j1 = (1 - i1) ^ s; j2 = (1 - i2) ^ s
    hw1 = 0xf000 | (s << 10) | ((imm >> 12) & 0x3ff)
    hw2 = 0x9000 | (j1 << 13) | (j2 << 11) | ((imm >> 1) & 0x7ff)
    return struct.pack("<HH", hw1, hw2)


def table_targets(b, stock):
    plt = b["plt"]
    if plt is None:
        if stock is None:
            sys.exit("this build's PLT addresses come from the stock library: pass --stock")
        plt = plt_targets(stock)
    out = []
    for t in TABLE:
        out.append(b["addr"][t[1:]] if t.startswith("@") else plt[t])
    return out


def stage_seg(build, out, variant, stock_path):
    from elftools.elf.elffile import ELFFile
    b = BUILDS[build]
    flags = VARIANTS[variant]
    out.mkdir(parents=True, exist_ok=True)
    stock = None
    if stock_path:
        stock = Path(stock_path).read_bytes()
        if hashlib.md5(stock).hexdigest() != b["md5"]:
            sys.exit(f"{stock_path} isn't build {build}'s libCarPlayCore.so")
    clang = os.environ.get("CLANG", "clang"); lld = os.environ.get("LLD", "ld.lld")
    nat = R / "native"
    run(clang, *ARM, "-I", nat, f'-DVSPI_FILE="{R / "data/vspi.bplist"}"', *b["defines"], "-c", nat / "seg.S", "-o", out / "seg.o")
    run(clang, *ARM, "-I", nat, *flags, "-c", nat / "hooks.c", "-o", out / "hooks.o")
    (out / "seg.ld").write_text(f"""ENTRY(cpc_stub_info)
SECTIONS {{
  . = {SEG_VA:#x};
  .seg : {{ *(.text.entry) *(.text .text.*) *(.rodata .rodata.*) }}
  /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.attributes) *(.comment) *(.note*) }}
}}
""")
    run(lld, "-static", "--no-dynamic-linker", "-T", out / "seg.ld", "-o", out / "seg.elf", out / "seg.o", out / "hooks.o")
    with open(out / "seg.elf", "rb") as f:
        e = ELFFile(f)
        names = [s.name for s in e.iter_sections() if s["sh_flags"] & 2]   # SHF_ALLOC
        if names != [".seg"]:
            sys.exit(f"segment must be one allocated section, got {names}")
        if any(s.name.startswith(".rel") for s in e.iter_sections()):
            sys.exit("segment has relocations")
        seg = e.get_section_by_name(".seg")
        code = bytearray(seg.data())
        assert seg["sh_addr"] == SEG_VA
        syms = {s.name: s["st_value"] for s in e.get_section_by_name(".symtab").iter_symbols() if s.name}
        undef = [s.name for s in e.get_section_by_name(".symtab").iter_symbols() if s.name and s["st_shndx"] == "SHN_UNDEF"]
        if undef:
            sys.exit(f"undefined symbols: {undef}")
    table = syms["cpc_table"]
    targets = table_targets(b, stock)
    for k, target in enumerate(targets):
        struct.pack_into("<i", code, table - SEG_VA + 4 * k, target - table)
    (out / "segment.bin").write_bytes(code)
    stubs = {s: syms[s] for _, _, s in b["sites"]}
    (out / "segment.json").write_text(json.dumps(
        dict(build=build, variant=variant, seg_va=SEG_VA, table=table, count=len(TABLE), stubs=stubs,
             sha256=hashlib.sha256(code).hexdigest()), indent=1) + "\n")
    print(f"segment {len(code)} bytes at {SEG_VA:#x}; table {table:#x} x{len(TABLE)}; "
          + ", ".join(f"{s}={a:#x}" for s, a in stubs.items()))


def stage_recipe(stock_path, hmgapi, out, variant):
    stock = Path(stock_path).read_bytes()
    md5 = hashlib.md5(stock).hexdigest()
    build = next((k for k, b in BUILDS.items() if b["md5"] == md5), None)
    if build is None:
        sys.exit(f"libCarPlayCore.so md5 {md5} isn't one of: " + ", ".join(b["md5"] for b in BUILDS.values()))
    b = BUILDS[build]
    info = json.loads((out / "segment.json").read_text())
    if info["build"] != build or info["variant"] != variant:
        sys.exit(f"{out}/segment.json is build {info['build']} variant {info['variant']}, not {build} {variant}")
    code = (out / "segment.bin").read_bytes()
    if hashlib.sha256(code).hexdigest() != info["sha256"]:
        sys.exit("segment.bin doesn't match segment.json")
    syms = info["stubs"]
    # patched library: the block as a PT_LOAD at SEG_VA, b.w at each site
    p = bytearray(stock)
    for at, before, stub in b["sites"]:
        if p[at:at + 4].hex() != before:
            sys.exit(f"site {at:#x} isn't the stock instruction")
        p[at:at + 4] = bw(at, syms[stub])
    for at, before, after in b["setup_log"]:
        if p[at:at + 2].hex() != before:
            sys.exit(f"setup log site {at:#x} isn't stock")
        p[at:at + 2] = bytes.fromhex(after)
    if variant == "f" and not b["version"]:
        sys.exit(f"variant f (version strings) isn't defined for build {build}")
    version = b["version"] if variant == "f" else []
    for at, before, after in version:
        if p[at:at + 8].hex() != before:
            sys.exit(f"version string at {at:#x} isn't stock")
        p[at:at + 8] = bytes.fromhex(after)
    if len(p) > SEG_VA:
        sys.exit("library longer than SEG_VA")
    p += b"\0" * (SEG_VA - len(p)) + code
    phoff, = struct.unpack_from("<I", p, 0x1c); phnum, = struct.unpack_from("<H", p, 0x2c)
    for k in range(phnum):
        if struct.unpack_from("<I", p, phoff + 32 * k)[0] == 0x6474e551:   # PT_GNU_STACK: file-only stand-in
            struct.pack_into("<8I", p, phoff + 32 * k, 1, SEG_VA, SEG_VA, SEG_VA, len(code), len(code), 5, 0x1000)
            break
    else:
        sys.exit("no PT_GNU_STACK to stand in for the segment's PT_LOAD")
    (out / "libCarPlayCore.patched.so").write_bytes(p)
    recipe = subprocess.run([sys.executable, "-I", hmgapi / "tools/mkmemrecipe.py", b["recipe_id"],
                             "/system/lib/libCarPlayCore.so", stock_path, out / "libCarPlayCore.patched.so",
                             "--code", hex(SEG_VA), "--table", f"{info['table']:#x}:{info['count']}", "--context", "8",
                             "--desc", "libCarPlayCore: vehicleStateProtocolInfo + displayPanels in /info, "
                                       "features [vehicleStateProtocol] in the SETUP reply (cp-climate M1)"],
                            check=True, capture_output=True, text=True).stdout
    # the stand-in PT_LOAD is a file-only change: keep its program header out of the recipe
    ph_lo, ph_hi = phoff, phoff + 32 * phnum
    kept = [l for l in recipe.splitlines()
            if not (l.split()[:1] in (["verify"], ["patch"]) and ph_lo <= int(l.split()[1], 0) < ph_hi)]
    changes = [l.split()[0] + " " + l.split()[1] for l in kept if l.split()[:1] in (["patch"], ["branch"])]
    want = [f"branch {at:#x}" for at, _, _ in b["sites"]] + [f"patch {at:#x}" for at, _, _ in b["setup_log"]] \
        + [f"patch {at:#x}" for at, _, _ in version]
    if sorted(changes) != sorted(want):
        sys.exit(f"recipe changes {changes}, expected only {want}")
    recipe = "\n".join(kept) + "\n"
    name = out / f"{b['recipe_id']}.recipe"
    name.write_text(recipe)
    print(name)


def ci_builds():
    """the builds the segment can be made for without a library (their PLT addresses are listed)"""
    return [k for k, b in BUILDS.items() if b["plt"] is not None]


def stage_verify(build, out):
    """the committed recipe for <build> carries the segment the sources build now, and mod.json lists it"""
    b = BUILDS[build]
    recipe = R / "mod/recipes" / f"{b['recipe_id']}.recipe"
    if not recipe.is_file():
        sys.exit(f"{build}: no recipe yet. Download this run's cp-climate-segment-{build} artifact and run\n"
                 f"  python3 source/tools/build.py recipe <that car's stock libCarPlayCore.so> <HMG-API checkout> <artifact dir>\n"
                 f"then commit <artifact dir>/{recipe.name} as source/mod/recipes/{recipe.name} and list it in mod.json")
    seg = [l.split() for l in recipe.read_text().splitlines() if l.startswith("segment ")]
    code = (out / "segment.bin").read_bytes()
    if len(seg) != 1 or bytes.fromhex(seg[0][2]) != code:
        sys.exit(f"{build}: {recipe.name} was made from a different segment than native/ builds now: "
                 "make the recipe again from this run's segment artifact (see the README)")
    listed = json.loads((R / "mod/mod.json").read_text())["hooks"]["native"]["libCarPlayCore.so"]
    if f"recipes/{recipe.name}" not in listed:
        sys.exit(f"{build}: recipes/{recipe.name} isn't in mod.json's hooks.native")
    print(f"{build}: {recipe.name} matches the segment ({len(code)} bytes) and is listed in mod.json")


def main():
    a = sys.argv[1:]
    stock = None
    if "--stock" in a:
        k = a.index("--stock"); stock = a[k + 1]; del a[k:k + 2]
    if a == ["list"]:
        print(json.dumps(ci_builds()))                 # the CI matrix
    elif a and a[0] == "verify":
        if len(a) != 3 or a[1] not in BUILDS:
            sys.exit("usage: build.py verify <build> <seg out dir>")
        stage_verify(a[1], Path(a[2]))
    elif a and a[0] == "seg":
        if len(a) < 3 or a[1] not in BUILDS:
            sys.exit("usage: build.py seg <" + "|".join(BUILDS) + "> <out dir> [variant] [--stock lib]")
        stage_seg(a[1], Path(a[2]), a[3] if len(a) > 3 else "full", stock)
    elif a and a[0] == "recipe":
        if len(a) < 4:
            sys.exit("usage: build.py recipe <stock lib> <HMG-API source> <out dir> [variant]")
        stage_recipe(a[1], Path(a[2]), Path(a[3]), a[4] if len(a) > 4 else "full")
    elif len(a) >= 3:
        md5 = hashlib.md5(Path(a[0]).read_bytes()).hexdigest()
        build = next((k for k, b in BUILDS.items() if b["md5"] == md5), None)
        if build is None:
            sys.exit(f"libCarPlayCore.so md5 {md5} isn't a known build")
        variant = a[3] if len(a) > 3 else "full"
        stage_seg(build, Path(a[2]), variant, a[0])
        stage_recipe(a[0], Path(a[1]), Path(a[2]), variant)
    else:
        sys.exit(__doc__)


main()
