import os

base = 'D:\\SampleRepo\\CVC4\\'
with open('D:\\SampleRepo\\deletes.log') as f:
    for line in f:
        fullpath = os.path.join(base, line)
        print "Checking " + fullpath
        if os.path.exists(fullpath):
            print fullpath + " exists!"