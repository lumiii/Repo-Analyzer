import os

makepath = "D:\\Makefile\\CVC4\\src"
makefile = "Makefile.am"
extensions = [".h", ".cpp"]

hardcoded_sources = ["libcvc4_la_SOURCES", "nodist_libcvc4_la_SOURCES", "BUILT_SOURCES", "CLEANFILES", "EXTRA_DIST"]
missing = set()

with open(os.path.join(makepath, makefile)) as f:
    capture = False
    for line in f:
        if line[0] != '#':
            if not capture:
                for source_str in hardcoded_sources:
                    if source_str in line:
                        capture = True
            else:
                stripped_line = line.strip()

                if stripped_line == "":
                    capture = False
                else:
                    for ext in extensions:
                        if ext in stripped_line:
                            filename = stripped_line.replace("\\", "")
                            filename = filename.strip()
                            filepath = os.path.join(makepath, filename)

                            if not os.path.isfile(filepath):
                                missing.add(filepath)

for filepath in missing:
    print filepath


