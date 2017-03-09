import dependency
import pickle

folder = "openage/game"
extension = "py"
# makefile = "src/context/Makefile.am"

path = dependency.dump_filepath()

with open(path) as f:
    results = pickle.load(f)

for makefile, hexlist in results[(folder, extension)].iteritems():
    if makefile == '':
        print "No dependency:"
    elif makefile != dependency.total_count:
        print "{}:".format(makefile)

    for hexsha in hexlist:
        print hexsha

    print '\n'
