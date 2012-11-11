#!/usr/bin/python

# This file will spawn off threads and generate the data sets
# It will assume passwordless access and the config file only allows
# specifying <string>+# as the machine name.

import sys, os, thread, commands

# Default config file (a sample is included)
configFile = "config.txt"

if len(sys.argv) > 1:
   if sys.argv[1].lower() in ['-h','--h','--help','-help']:
      print "\nUsage: %s <config>\n" % sys.argv[0]
      sys.exit(1)
   else:
      configFile = sys.argv[1]

# A dictionary of parameters
params = {}
dict = {}

machinesFile = "/root/persistent-hdfs/conf/slaves"

# Get the username
params['whoami'] = commands.getstatusoutput('whoami')[1]

configCont = open(configFile,'r').readlines()
for i in configCont:
    if len(i)>1 and not i.strip()[0] == '#':
        iSplit = map(lambda x:x.strip(), i.split(':')[1:])
        params[i.split(':')[0]] = ':'.join(iSplit)
machines = open(machinesFile,'r').readlines()
machines = map(lambda s: s.strip(), machines)
# Make temporary subdirectory unique in order to avoid permission issues
params['TempSubDir'] = params['TempSubDir'].replace("/","").strip()
params['TempSubDir'] = params['TempSubDir']+"_"+params['whoami']+"/"
print params

def log( msg ):
   tmp = open(params['Log'], 'a')
   tmp.write(msg + "\n")
   tmp.close()

# This is the set of files needed at the local machine
NEEDED_FILES = ['genhtml/genhtml', 'genhtml/parsehtml', 'extractUrls.py', 'duplicates.py', \
	        'genUserVisits.py', 'ColumnGenerator.py', 'TableGenerator.py', \
                'redo_ip.py', 'data_files/user_agents.dat', 'data_files/country_codes.dat', \
                 'data_files/country_codes_plus_languages.dat', 'data_files/keywords.dat' ]

# Parameters should probably be in a global include file
# For now there is 3 actions that I actually use - scp, rm and killall
def fileAction( action, mach, files, params ):
   for fi in files:
      # Source and destination details are to be filled later
      cmd = action

      slashLoc = 0
      if fi.rfind("/")>-1:
         slashLoc = fi.rfind("/")
      # Just the file name, in case it included a path
      fName = fi[slashLoc:]

      src = ""
      dst = ""

      if action == "scp":
          src = (fi)
          # Destination directory plus just the file name
          dst = mach + ":"+params['TempDir']+"/"+params['TempSubDir']+"/"+fName
      else:
          cmd = "ssh "+mach+" "+cmd

      if action == "killall":
          dst = fName

      if action == "rm -rf":
          dst = params['TempDir']+"/"+params['TempSubDir']+"/"+fName

      cmd = cmd + " " + src + " " + dst + ">& /dev/null"
#      cmd = cmd + " " + src + " " + dst

#      log( "Run " + cmd )
      os.system(cmd)

def genDataThread( mach, myID, *args ):

   log( "Begin thread execution for host %s" % mach)
   print "Begin thread execution for host %s, MY ID = %d" % (mach, myID)

   remoteDir = params['TempDir']+"/"+params['TempSubDir']

   # Remove persistent hdfs data
   os.system("ssh %s 'rm -rf /scratch.1/arasin/new_cacm_data'" %(mach))

   # Install openssl-devel
   os.system("ssh %s 'yes | yum install openssl-devel' > /dev/null" %(mach))

   # Link libcrypto
   os.system("ssh %s 'ln /usr/lib64/libcrypto.so /usr/lib64/libcrypto.so.5' > /dev/null" %(mach))

   # Make the temporary directory
   os.system("ssh %s mkdir -p %s > /dev/null" %(mach, remoteDir))

   # Kill off any lingering processes
   fileAction("killall", mach, ['genUserVisits.py', 'extractUrls.py', 'genhtml', 'parsehtml'], params)

   # Clean up the old files
   os.system("ssh %s rm -rf %s" % (mach, params['Output']))

   # Set "done" flag here if we want to just clean up the files

   # Recreate the output directory
   os.system("ssh %s mkdir -p %s" % (mach, params['Output']))

   # Compile the binaries
   os.system("cd genhtml; make genhtml > /dev/null; make parsehtml > /dev/null")

   # Copy the binaries and scripts to the /tmp directory of the relevant host
   fileAction("scp", mach, NEEDED_FILES, params)

   numFPerSite = int(params['Rankings'])

   # Sites per node
   sitesPerNode = 6
   for i in range( sitesPerNode ):  # Around 1 Gig in total
      os.system("ssh %s \'cd %s > /dev/null; %s/genhtml -s %d -f %d -r %d -ns %d > /dev/null\'" % ( mach, params['Output'], remoteDir, myID, numFPerSite, 100+i+myID, params['MachCount']))
      if i == 5:
         log("Generated data on site "+mach)

      #print "ssh %s \'cd %s > /dev/null; %s/parsehtml > Rankings%d.dat\' " % (mach, params['Output'], remoteDir, i)
      os.system("ssh %s \'cd %s > /dev/null; %s/parsehtml > Rankings%d.dat\' " % (mach, params['Output'], remoteDir, i))

      if i == 5:
         log("Parsed data on site "+mach)

      os.system("ssh %s \'cd %s > /dev/null; cat %s/Rankings%d.dat >> %s/Rankings.dat\' " % (mach, params['Output'], params['Output'], i, params['Output']))

      # Clean up the temporary files for this pass
      os.system("ssh %s rm %s/Rankings%d.dat"%(mach,params['Output'],i))
      os.system("ssh %s mv %s/docs %s/docs.%d" % (mach, params['Output'],params['Output'],i))

   os.system("ssh %s \'cd %s > /dev/null; %s/extractUrls.py Rankings.dat > URLs\' " % (mach, params['Output'], remoteDir))

   # 165M rows should be about 20G
   os.system("ssh %s \'cd %s > /dev/null; %s/genUserVisits.py %s %s/URLs %s/UserVisits.dat %s \\\\\\%s\' " % (mach, params['Output'], remoteDir, params['UserVisits'], params['Output'], params['Output'], remoteDir, params['Delimiter']))
   #print "ssh %s \'cd %s > /dev/null; %s/genUserVisits.py %s %s/URLs %s/UserVisits.dat %s \\\\\\%s\' " % (mach, params['Output'], remoteDir, params['UserVisits'], params['Output'], params['Output'], remoteDir, params['Delimiter'])

   # Remove the URLs file
   os.system("ssh %s rm %s/URLs" % (mach, params['Output']))
   log("UserVisits generated on site " + mach)

   # Remove duplicate entries from Rankings.  Also add  average time on site
   os.system("ssh %s %s/duplicates.py %s/Rankings.dat %s/Rankings_Unique.dat \\\\\\%s" % (mach, remoteDir, params['Output'], params['Output'], params['Delimiter']))
   os.system("ssh %s chmod a+rx %s/Rankings_Unique.dat" % (mach, params['Output']))
   os.system("ssh %s mv %s/Rankings_Unique.dat %s/Rankings.dat" % (mach, params['Output'], params['Output']))

   # Move files from local disk to hdfs
   # cmd = "/root/ephemeral-hdfs/bin/hadoop fs -copyFromLocal"
   # os.system("ssh %s '%s %s/Rankings.dat /data/rankings/Rankings_%s.dat'" % (mach, cmd, params['Output'], myID))

   # os.system("ssh %s '%s %s/UserVisits.dat /data/rankings/UserVisits_%s.dat'" % (mach, cmd, params['Output'], myID))


   # Cleanup
   fileAction("rm -rf", mach, [remoteDir], params)
   dict[ mach ] = "Done"

params['MachCount']=len(machines)

machID = 0

for mach in ( machines ):
#   print "Start running Thread#", str(i)
   os.system('sleep 1')

   a = thread.start_new_thread( genDataThread, (mach, machID) )
   machID = machID + 1


while ( len(dict.keys()) < params['MachCount'] ):
   os.system('sleep 60')
   print len(dict.keys()), " out of ", params['MachCount'], " done"
   # Added to give status updates
   machID = 0
   for mach in machines:
      print "Machine %i generated: " % (machID)
      os.system("ssh %s 'du -h %s'" % (mach, params['Output'] + "/UserVisits.dat"))
      machID = machID + 1
