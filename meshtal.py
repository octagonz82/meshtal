"""Mesh tally module."""

from math import cos, sin, pi, sqrt, log, atan2
import numpy as np
from tqdm import tqdm
# from pylab import *

# Particles dictionary
IPT = dict([('all', 0), ('neutron', 1), ('photon', 2), ('electron', 3),
            ('positron', 4), ('proton', 9)])
revIPT = {v: k for k, v in IPT.items()}


class MeshTally:
    """
    This class is surprisingly enough, a MCNP mesh tally.

    It has the following atributes:
        part: particle tracked. Neutrons by default
        iints, jints, kints: Number of divisions in the 3 dimensions
        ibins, jbins, kbins: Vectors defining the divisions in the 3d
        eints, ebins: Same as above, but with energies
        value: The tally result itself
        error: Tally uncertainty
        nps: Number of source particles used.
        probID: The problem ID. Typically, it is the run date and time.
        geom: "XYZ" for cartesian tallies, "Cyl" for cylindrical
        n: Tally number
        comment: Tally comment as in the FC card.
        axis: axis of cylindrical geometry
        origin: Tally origin for cylindrical geoms.
        TR: Transformation vector.
    The following properties are defined, but are NOT present in  meshtal file.
    Take extra care when using them!
        FM: Tally multplier
    """

    def __init__(self, iints, jints, kints, eints, geom='XYZ'):
        self.part = 'neutron'  # particle. By default, neutrons"""
        self.iints = iints  # divisions in 1st dimension
        self.jints = jints  # divisions in 2nd dimension
        self.kints = kints
        self.eints = eints
        self.ibins = np.zeros(iints+1)
        self.jbins = np.zeros(jints+1)
        self.kbins = np.zeros(kints+1)
        self.ebins = np.zeros(eints+1)
        self.value = np.zeros((iints, jints, kints, eints+1))
        self.value_ww = np.zeros((iints, jints, kints, eints+1))
        self.error = np.zeros((iints, jints, kints, eints+1))
        self.nps = 0
        self.modID = "No model ID provided"
        self.probID = "No problem ID provided"
        self.geom = geom
        self.origin = np.zeros(3)  # Default origin is 0,0,0
        self.TR = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1],
                            [0, 0, 0]])  # Tally transformation
        self.n = 4  # Tally number
        self.FM = 1  # Tally multiplier. I don't know how to treat this, actually...
        self.comment = 'no comment provided'  # Tally comment
        if self.geom == "Cyl":
            self.axis = np.array([0, 0, 1])  # Axis
            self.vec = np.array([1, 0, 0])   # Azimuthal vector

    def shape(self):
        return [self.iints, self.jints, self.kints, self.eints]

    @property
    def volume(self):
        """Return the volume of the meshtal voxels."""
        vol = np.zeros((self.iints, self.jints, self.kints))
        for (i, j, k), v in np.ndenumerate(vol):
            if self.geom == "XYZ":
                v = (self.ibins[i+1]-self.ibins[i])\
                *(self.jbins[j+1]-self.jbins[j])\
                *(self.kbins[k+1]-self.kbins[k])
            elif self.geom == "Cyl":
                v = (pow(self.ibins[i+1], 2)-pow(self.ibins[i], 2))\
                *(self.jbins[j+1]-self.jbins[j])\
                *(self.kbins[k+1]-self.kbins[k])*pi
            else:
                print("Unknown Geometry type")
                return None
            vol[i, j, k] = v
        return vol

    def userrotate(self, logfile=None):
        """Rotate a tally according to user inpute"""
        print('default TMESH origin: ', self.origin)
        print('default TMESH axis: ', self.axis)
        newaxis = self.axis
        newvec = self.vec
        neworigin = self.origin
        anglemod = 0
        select = input('Do you want to modify default tmesh orientation y/n ')
        while select not in ['y', 'n']:
            select = input('Choose, y o n:')
        if select == 'y':
            updatearray(neworigin)
            updatearray(newaxis)
            updatearray(newvec)
            projection = np.dot(newvec, newaxis)/np.linalg.norm(newaxis)**2
            newvec = newvec - projection*newaxis
            if np.linalg.norm(newvec) == 0:
                print('Fatal: VEC is 0 0 0')
                select = 'n'
            else:
                self.origin = neworigin
                self.axis = newaxis/np.linalg.norm(newaxis)
                self.vec = newvec/np.linalg.norm(newvec)
        if logfile is not None:
            print('adding ', anglemod, ' degrees to default cylinder kbins')
            log_results_file = open(logfile, 'w')
            log_results_file.write('Have we modified tmesh orientation? {} \n'.format(select))
            log_results_file.write('New origin vector instead 0 0 0: {} \n'.format(self.origin))
            log_results_file.write('New axis vector instead 0 0 1: {} \n'.format(self.axis))
            log_results_file.write('New  XX\' {0}\n '.format(self.vec))
            log_results_file.close()


    def smoothang(self, maxangle):
        """
        In-place smoothing of the angular bins.

        Parameters
        ----------
        maxangle : float
            Maximum angle allowed for the theta division, in deg

        Returns:  None.
        """
        angles = np.diff(self.kbins)
        ipoints = np.array(angles // maxangle, dtype=int)  # interpolation points in bins
        kbins = np.zeros(0)
        kindex = []
        for i, ipoint in enumerate(ipoints):
            newkbins = np.linspace(self.kbins[i], self.kbins[i+1], ipoint+1, endpoint=False)
            kbins = np.append(kbins, newkbins)
            kindex.extend([i]*(ipoint+1))
        kbins = np.append(kbins, self.kbins[-1])  # Final angle bin is not in previous loop

        val = np.zeros((self.iints, self.jints, kbins.shape[0] - 1, self.eints + 1))
        err = np.zeros((self.iints, self.jints, kbins.shape[0] - 1, self.eints + 1))
        for k, ki in enumerate(kindex):
            val[:, :, k, :] = self.value[:, :, ki, :]
            err[:, :, k, :] = self.error[:, :, ki, :]

        result = copy(self, exclude=['kbins', 'value', 'error'])
        result.kbins = kbins
        result.value = val
        result.error = err  # TODO: Check, not sure
        result.kints = len(kbins)-1
        return result
    
    def RoNormalization(self, ptrac_file, outp_file, method="pointsample", pformat="Ascii"):
        import ptrac
        Ro,Ss=ptrac.romesh(self, ptrac_file, outp_file, method, pformat, None)
        Result = copy (self, exclude=['probID', 'value', 'error'])
        Result.probID = "Generated by meshtal class from {probID}".format(probID=self.probID)
        Result.comment+= "Normalized by density from {0}".format(ptrac_file)
        for (i, j, k, e) in np.ndindex(Result.iints, Result.jints, Result.kints, Result.eints+1):
            if Ro[i,j,k] != 0:
                if Ro[i,j,k] > 0:
                    Result.value[i,j,k,e] = self.value[i,j,k,e]/Ro[i,j,k]
                else:
                    Result.value[i,j,k,e] = self.value[i,j,k,e]/Ro[i,j,k]*-1
                Result.error[i,j,k,e] = self.error[i,j,k,e]
            else:
                Result.value[i,j,k,e] = 0
                Result.error[i,j,k,e] = 0
        return Result
    


# ======================= END OF CLASS DEFINITION ==========================

def flist(infile='meshtal'):
    """ Get the tally numbers for all mesh tallies present in infile """

    with open(infile, "r") as MeshtalFile:
        tallylist = []
        for line in MeshtalFile:
            if "Mesh Tally Number" in line:
                n = line.split()[-1]
                tallylist.append(int(n))
    return tallylist


def fgetheader(infile='meshtal'):
    """ Auxiliary method to get probID, modID and nps from a meshtal file """
    with open(infile, "r") as MeshtalFile:
        header = MeshtalFile.readline()
        probID = header.split("probid =")[1]  # got problem ID
        modID = MeshtalFile.readline()  # Description of the model
        header = MeshtalFile.readline()  # Line with the number of histories
        fnps = float(header.split()[-1])  # NPS in floating number
        nps = int(fnps)  # NPS
    return{'nps': nps, 'probID': probID, 'modID': modID}


def fgettally(tallystr):
    """Auxiliary to get the tally data from string tallystr"""
    data = iter(tallystr)
    line = next(data)
    n = line.split()[-1]

    line = next(data)
    if  line[0:5] == '     ':  # 5 blank spaces is how the next file is identified as a comment
        comment = line
        line = next(data)
        print('comment:', comment)
    else:
        comment = None

    particle = line.split()[0]
    print('particle:', particle)
    line = next(data) # This is the line where it should say if it has a dose function
    if line == ' This mesh tally is modified by a dose response function.\n':
        print("Dose function:", line)
        line = next(data)
    line = next(data)
 # TODO: Apparently, Tally multipliers are here, but I don't have a good one
    if line != ' Tally bin boundaries:\n':
        print(line)
        print("Uh, uh, tally boundaries not found.\
              Quitting, because this is not really what I expected")
        return None
    line = next(data)
    words = line.split()
    if words[0] == "origin": # This is a cylindrical tally
        Ttype = "Cyl"
        location = words[2:] #variable descripting the cylinder origin and orientation. Important!!
        line = next(data)
        words = line.split()
        print('tally location string', location)

    if words[0] == "X":
        Ttype = "XYZ"
    ibinlist = words[2:]
    ibins = [float(i) for i in ibinlist]
    iints = len(ibins)-1
    line = next(data)
    words = line.split()

    if words[0] == "Z":
        Ttype = "Cyl"
    jbinlist = words[2:]
    jbins = [float(j) for j in jbinlist]
    jints = len(jbins)-1

    line = next(data)
    words = line.split()
    if Ttype == "XYZ":
        kbinlist = words[2:]

    elif Ttype == "Cyl":
        kbinlist = words[3:]
    else:
        print("Tally does not seem rectangular nor cylindrical.\
               Quitting because I don't know what is this...")
        return None

    kbins = [float(k) for k in kbinlist]
    kints = len(kbins)-1

    line = next(data)
    words = line.split()
    ebinlist = words[3:]
    ebins = [float(e) for e in ebinlist]
    eints = len(ebins)-1
    tally = MeshTally(iints, jints, kints, eints)
    tally.ibins = np.array(ibins)
    tally.jbins = np.array(jbins)
    tally.kbins = np.array(kbins)
    tally.ebins = np.array(ebins)
    tally.part = particle
    tally.n = int(n)
    next(data)
    line = next(data)  # Assert this is going as intended TODO: Support
                             # for time tallies is possible!
    header = line.split()
    if Ttype == "XYZ":
        assert header[-4] == 'Z'
    else:
        assert header[-4] == 'Th'
        assert header[-3] == 'Result'
        assert header[-1] == 'Error'

    for e in range(eints):
        for (i, j, k) in np.ndindex(iints, jints, kints):
            line = next(data)
            tally.value[i, j, k, e+1] = line.split()[-2]
            tally.error[i, j, k, e+1] = line.split()[-1]
    # We now have the values for the energy bins, but we are missing the totals.
    # This changes depending on wether we have
    # a single energy bin (eints=1) or more
    if eints == 1:
        tally.value[:, :, :, 0] = tally.value[:, :, :, 1]
        tally.error[:, :, :, 0] = tally.error[:, :, :, 1]
    else:
        for (i, j, k) in np.ndindex(iints, jints, kints):
            line = next(data)
            tally.value[i, j, k, 0] = line.split()[-2]
            tally.error[i, j, k, 0] = line.split()[-1]
    if Ttype == "Cyl":
        tally.geom = "Cyl"
        tally.origin = [float(l) for l in location[0:3]]
        tally.origin = np.asarray(tally.origin)
        tally.axis = [float(l) for l in location[5:8]]
        tally.axis = np.asarray(tally.axis)
        tally.vec = [float(l) for l in location[11:14]]
        tally.vec = np.asarray(tally.vec)
    return tally


def fget(n, infile='meshtal'):
    """ Get tally number n from meshtal file. """
    header = fgetheader(infile)
    with open(infile, "r") as MeshtalFile:
        for lines in MeshtalFile:
            if "Mesh Tally Number" in lines and str(n) == lines.split()[-1]:
                print("Found tally", n)
                tallystr1 = [lines]
                tallystr2 = [lines for lines in MeshtalFile]
                break
        else:
            print("Tally {0:d} not found".format(n))
            return None

    for i, line in enumerate(tallystr2):
        if "Mesh Tally Number" in line:
            tallystr2 = tallystr2[:i]
    tallystr = tallystr1 +tallystr2
    tally = fgettally(tallystr)

    tally.nps = header['nps']
    tally.probID = header['probID'][:-1]
    tally.modID = header['modID'][:-1]
    return tally


def fgetall(infile='meshtal'):
    """ Returns an array with all the mesh tallies in ifile """
    nlist = flist(infile)
    print('Found tallies:')
    print(*nlist, sep=', ')
    header = fgetheader(infile)
    with open(infile, "r") as MeshtalFile:
        for lines in MeshtalFile:
            if "Mesh Tally Number" in lines:
                tallystr1 = [lines]
                tallystr2 = [lines for lines in MeshtalFile]
                break
    alltallystr = tallystr1 + tallystr2

# Split the list into ones containing different tallies
    spltline = []
    for i, line in enumerate(alltallystr):
        if 'Mesh Tally Number' in line:
            spltline.append(i)


    tallystr = [alltallystr[i:j] for i, j in zip(spltline, spltline[1:]+[len(alltallystr)])]
    tallylist = []

    for t in tallystr:
        tallylist.append(fgettally(t))
        tallylist[-1].nps = header['nps']
        tallylist[-1].modID = header['modID'].rstrip( )
        tallylist[-1].probID = header['probID'].rstrip( )
    return tallylist


def tgetall(tfile):
    """ Get all the mesh tallies from the gridconv file tfile"""
    try:
        tmesh = open(tfile, "r")
    except OSError:
        print('cannot open file', tfile)
        return
    else:
        tmesh.close()

    with open(tfile, "r") as meshtalfile:
        comment = meshtalfile.readline()
        lines = meshtalfile.readline()
        valores = lines.split()
        ntallies = int(valores[0]) # Nº tallies
        VMCNP = valores[2]
        print(ntallies, " tallies found calculated using MCNP", VMCNP)
        nps = valores[-1] # Should be NPS problem
        tallylist = []
        for tally in range(ntallies):
            UFO1 = meshtalfile.readline() # TODO: What is that?
            lines = meshtalfile.readline()
            valores = lines.split()
            print(int(valores[0]))
            if int( valores[0]) // 10 == 1:
                GEOM = "XYZ"
            elif int(valores[0]) // 10 == 2:
                GEOM = "Cyl"
            else:
                print("Unknown geometry type for tally", tally)
                return
            parttype = int(valores[1])
            part = revIPT[parttype]
            iints = int(valores[2])-1
            jints = int(valores[3])-1
            if GEOM == "XYZ":
                kints = int(valores[4])-1
            if GEOM == "Cyl":
                kints = int(valores[4])
            eints = 1 # TMeshes only seem capable of 1 energy bin.
            ngrids = int(valores[5]) # TODO: This value is actually the number of meshes (I think),
            # and only seems to appear in tally type 2. Add a way to deal with this crap, probably
            # splitting the tally. Right now, a tally 2 not in last position screws the whole method.
            tallylist.append(MeshTally(iints, jints, kints, eints, GEOM))
            tallylist[tally].n = int(valores[7])  # Tally number
            tallylist[tally].geom = GEOM  # Geometry
            lines = meshtalfile.readline()
            valores = lines.split()
            tallylist[tally].ebins = [float(ebin) for ebin in valores]
            UFO2 = meshtalfile.readline()
# Headers are read. We now read the geometry, values, and error. Multi-particles tallies will cause this to crash.
#        return tallylist

        UFO3 = meshtalfile.readline()
        for tally in range(ntallies):
            print("getting tally", tally)
            iints = tallylist[tally].iints
            jints = tallylist[tally].jints
            kints = tallylist[tally].kints
            value = np.zeros((iints, jints, kints))
            error = np.zeros((iints, jints, kints))

# Added by OGM to re-orient TMESH. Hackish but working?
            if tallylist[tally].geom=="Cyl":
                tallylist[tally].userrotate(logfile='log_tgetall_{}.txt'.format(tally))

            lines = meshtalfile.readline()
            valores = lines.split()
            tallylist[tally].ibins = [float(ibin) for ibin in valores]

            lines = meshtalfile.readline()
            valores = lines.split()
            tallylist[tally].jbins = [float(jbin) for jbin in valores]

            lines = meshtalfile.readline()
            valores = lines.split()

            if tallylist[tally].geom == "XYZ":
                tallylist[tally].kbins = [float(kbin) for kbin in valores]
            if tallylist[tally].geom=="Cyl":
                tallylist[tally].kbins[1:] = [float(kbin)/360 for kbin in valores]
                tallylist[tally].kbins[0] = 0
            for (k, j) in np.ndindex(kints, jints):
                lines = meshtalfile.readline()
                valores = lines.split()
                value[:, j, k] = [float(number) for number in valores]
            for (k, j) in np.ndindex(kints, jints):
                lines = meshtalfile.readline()
                valores = lines.split()
                error[:, j, k] = [float(number) for number in valores]

            tallylist[tally].value[:, :, :, 0] = value
            tallylist[tally].value[:, :, :, 1] = value
            tallylist[tally].error[:, :, :, 0] = error
            tallylist[tally].error[:, :, :, 1] = error
            tallylist[tally].nps = nps
            tallylist[tally].comment = comment

    return tallylist


def updatearray(inparray, name=''):
    """Auxiliary to update an array with user input"""
    arsize = len(inparray)
    data = input('Enter new {0} vector instead of {1} using space: '.format(name, inparray))
    try:
        inparray[:] =[float(d) for d in data.split(' ')[:arsize]]
    except:
        print('Invalid input, keeping {0}'.format(name))


def copy(basetally, exclude=None):
    """
    returns a copy of basetally, except for the parameters in exclude.
    Notice that the spatial and energy ints can not be excluded.
    """
    result = MeshTally(basetally.iints, basetally.jints, basetally.kints, basetally.eints)
    for var in vars(basetally):
        if var not in exclude:
            vars(result)[var] = vars(basetally)[var]
    return result

class HealthReport:
    """ Class to hold the results of the meshtally Health report."""
    def __init__(self, meshtally):
        # if not isinstance(self, MeshTally):
        #     print("Argument is not a MeshTally instance")
        #     raise TypeError
        self.val = [None]*(meshtally.eints+1)
        self.err = [None]*(meshtally.eints+1)
        for energy in range(meshtally.eints+1):
            self.val[energy] = np.array([v for v in meshtally.value[:, :, :, energy].flatten()
                                         if v > 0])
            self.err[energy] = np.array([e for e in meshtally.error[:, :, :, energy].flatten()
                                         if e > 0])
        self.nvox = meshtally.iints*meshtally.jints*meshtally.kints
        self.ebins = meshtally.ebins


    def mingoodval(self, minerror, ebin=0):
        if not isinstance(ebin, int):
            print("ebin provided not an integer number")
            return None
        if ebin > len(self.val):
            print("ebin provided is out of tally range")
            return None
        if min(self.err[ebin]) < minerror:
            index = np.nonzero(self.err[ebin] < minerror)
            minval = min([self.val[ebin][i] for i in index[0]])
            return minval
        else:
            return None  # No voxels with good enough error


    def fractionbelowE(self, minerror, ebin=0):
        if not isinstance(ebin, int):
            print("ebin provided not an integer number")
            return None
        if ebin > len(self.val):
            print("ebin provided is out of tally range")
            return None
        num = np.count_nonzero((self.err[ebin] < minerror) & (0 < self.err[ebin]))
        return num/self.nvox


    def report(self, ebins=[0], thresolds=[0.1, 0.2]):
        """
        Print general mesh tally health information. Done by default on total energy, but more
        bins can be added as ebins
        """
        try:
            import colr
            colour = True
        except ImportError:
            print("colr module not found, fancy output deactivated")
            colour=False
        minval = self.val[0].min()
        maxval = self.val[0].max()
        print("Maximum value is {0:E}\n".format(maxval))
        print("Minimum value is {0:E}\n".format(minval))
        print("Minimum good value is {0:E} \n".format(self.mingoodval(thresolds[0])))
        print("Minimum relevant value is {0:E} \n".format(self.mingoodval(thresolds[1])))
        print("Tally nonzero elements are {0:.2%}\n".format(len(self.val[0])/self.nvox))
        for i, j in enumerate(thresolds):
            ratio = self.fractionbelowE(thresolds[i])
            if colour == False:
                print("{0:.2%} voxels are below {1:.2F} error\n".format(ratio, j))
            else:
                if ratio<0.8:
                    redvalue = 255
                    greenvalue = 255*(0.8-ratio)
                else:
                    redvalue = 1275*(1-ratio)
                    greenvalue = 255
                print(colr.color("{0:.2%} voxels are below {1:.2F} error\n",
                      fore=(redvalue, greenvalue, 0)).format(ratio, j))

    def ploterrorhist(self, ebin=0):
        """Plot the cumulative fraction of voxels below error for ebint. Experimental for now"""
        import matplotlib.pyplot as plt
        nbins = min(len(self.err[0]) // 10, 100)
        plt.xlabel("Statistical uncertainty")
        plt.ylabel("Fraction of nonzero data")
        plt.title("Error histogram for tally")
        plt.grid(True)
        plt.hist(self.err[ebin], cumulative=True, density=True, bins=nbins)

########################## END OF CLASS DEFINITION #############################################


def Geoeq(*tallies):
    """ Check if the mesh tallies in array tallies are geometrically equivalent,
    i.e: Have the same mesh. Will always return true for a single tally.
    If something goes awry, the answer is NO"""
    for index, tally in enumerate(tallies):
        if not isinstance(tally, MeshTally):
            print("Argument #{0} is not a meshtally object".format(index))
            return False
    for tally in tallies[1:]:
        if not np.array_equal(tally.ibins, tallies[0].ibins):
            return False
        if not np.array_equal(tally.jbins, tallies[0].jbins):
            return False
        if not np.array_equal(tally.kbins, tallies[0].kbins):
            return False
    return True


def vtkwrite(meshtal, ofile):
    """create an vtk file ofile from tally meshtal"""
    if meshtal.eints == 1:
        NFields = 2
    else:
        NFields = 2*meshtal.eints+2
    vtk_name = ofile[:-4]   # TODO: Pardon me?
    with open(ofile,"w") as VTKFile:
        VTKFile.write('# vtk DataFile Version 3.0\n'
                      '{ProbID} vtk output\n'
                      'ASCII\n'.format(ProbID=meshtal.probID))
    if meshtal.geom == "XYZ":
        nvoxels = meshtal.iints * meshtal.jints * meshtal.kints  # Total number of voxels
        with open(ofile,"a") as VTKFile:
            VTKFile.write('DATASET RECTILINEAR_GRID\n')
            VTKFile.write('DIMENSIONS {X} {Y} {Z}\n'.format(X=meshtal.iints+1, Y=meshtal.jints+1,
                                                            Z=meshtal.kints+1))
            VTKFile.write('X_COORDINATES {X} float\n'.format(X=meshtal.iints+1))
            VTKFile.writelines(["{0}\n".format(i) for i in meshtal.ibins])
            VTKFile.write('Y_COORDINATES {Y} float\n'.format(Y=meshtal.jints+1))
            VTKFile.writelines(["{0}\n".format(j) for j in meshtal.jbins])
            VTKFile.write('Z_COORDINATES {Z} float\n'.format(Z=meshtal.kints+1))
            VTKFile.writelines(["{0}\n".format(k) for k in meshtal.kbins])
            value = [meshtal.value[:, :, :, e].flatten(order="F") for e in range(meshtal.eints+1)]
            error = [meshtal.error[:, :, :, e].flatten(order="F") for e in range(meshtal.eints+1)]

    elif meshtal.geom == "Cyl":
        angles = np.diff(meshtal.kbins)
        if max(angles) > 0.1666:
            print (' Smoothing angles above 60º\n')
        smoothed_tally = meshtal.smoothang(1/36)
        kints = smoothed_tally.kints
        kbins = smoothed_tally.kbins  # we call the smoothing anyway, easier code that way
        value = [smoothed_tally.value[:, :, :, e].flatten(order="C") for e in range(meshtal.eints+1)]
        error = [smoothed_tally.error[:, :, :, e].flatten(order="C") for e in range(meshtal.eints+1)]

        nvoxels = meshtal.iints * meshtal.jints * kints  # Total number of voxels
        npoints = (meshtal.iints +1)*(meshtal.jints+1)*(kints +1)  # Total number of points
        #Let's define a point matrix, where each component is an array [X,Y,Z]
        points = np.zeros((meshtal.iints+1, meshtal.jints+1, kints+1), dtype=(float, 3))
# Make the transformation of axis, origin and vec according to TR
        AXS = np.matmul(meshtal.axis, meshtal.TR[0:3].T)
        VEC = np.matmul(meshtal.vec, meshtal.TR[0:3].T)
        origin = np.matmul(meshtal.origin, meshtal.TR[0:3].T +meshtal.TR[3])
        YVEC = np.cross(AXS, VEC)
        for j, jbin in enumerate(meshtal.jbins):
            for k, kbin in enumerate(kbins):
                points[0, j, k] = 1E-3*(cos(kbin*2*pi)*VEC+sin(kbin*2*pi)*YVEC) + jbin*AXS + origin
        #Now the rest
        for i, ibin in enumerate(meshtal.ibins[1:]):
            for j, jbin in enumerate(meshtal.jbins):
                for k, kbin in enumerate(kbins):
                    points[i+1, j, k] = ibin*(cos(kbin*2*pi)*VEC+sin(kbin*2*pi)*YVEC) + jbin*AXS + origin

        with open(ofile, "a") as VTKFile:
            VTKFile.write('DATASET STRUCTURED_GRID\n')
            VTKFile.write('DIMENSIONS {Z} {Y} {X}\n'.format(X=meshtal.iints+1, Y=meshtal.jints+1,
                                                            Z=kints+1))
            VTKFile.write('POINTS {N} float\n'.format(N=npoints))
            for (i, j, k) in np.ndindex(meshtal.iints+1, meshtal.jints+1, kints+1):
                VTKFile.write(' {0:E} {1:E} {2:E}\n'.format(points[i, j, k, 0],points[i, j, k, 1],points[i, j, k, 2]))
    else:
        print("I do not know this mesh tally geometry. Quitting, sorry.")
        return

    with open(ofile, "a") as VTKFile:
        VTKFile.write('CELL_DATA {N}\n'.format(N=nvoxels))
        VTKFile.write('FIELD FieldData {N} \n'.format(N=NFields))
        VTKFile.write('TotalTally_{vtkname} 1 {N} float\n'.format(vtkname=vtk_name, N=nvoxels))
        VTKFile.write(' '.join("%s" % v for v in value[0])+'\n')
        VTKFile.write('TotalError_{vtkname} 1 {N} float\n'.format(vtkname=vtk_name, N=nvoxels))
        VTKFile.write(' '.join("%s" % e for e in error[0])+'\n')

        if meshtal.eints > 1:
            for e in range(1, meshtal.eints+1):
                VTKFile.write('Tally{E1}-{E2}_{vtkname} 1 {N} float\n'.format(vtkname=vtk_name, E1=meshtal.ebins[e-1], E2=meshtal.ebins[e], N=nvoxels))
                VTKFile.write(' '.join("%s" % v for v in value[e])+'\n')
                VTKFile.write('Error{E1}-{E2}_{vtkname} 1 {N} float\n'.format(vtkname=vtk_name, E1=meshtal.ebins[e-1], E2=meshtal.ebins[e], N=nvoxels))
                VTKFile.write(' '.join("%s" % e for e in error[e])+'\n')


def ecollapse(meshtal, ebinmap):
    """Collapses the energy groups in meshtal acording to integer list
       or array ebinmap.
       WARNING: Error calculations are mere aproximation. Information is lost in
       the process and the actual error CAN NOT be calculated
    """
    if sum(ebinmap) != meshtal.eints:
        print("energy bin map does not match mesh tally energy bins, cancelling")
        return
    result = copy(meshtal, exclude=['error', 'value', 'ebins'])
    result.eints = len(ebinmap)-1
    energies = np.zeros(result.eints+1) # ebin for new tally
    energies[0] = meshtal.ebins[0]
    pos = 0 # position we are reading in the ebins vector
    for e, ebinblock in enumerate(ebinmap):
        pos = pos+ebinblock
        energies[e] = meshtal.ebins[pos]

    pos = 1 # reset position to bin 1. bin 0 is total, remember!!!!
    for e, ebin in enumerate(ebinmap):
        addval = np.sum(meshtal.value[:, :, :, pos:(pos+ebin)], axis=-1)
        result.value[:, :, :, e+1] = addval
        arrayadderr = [meshtal.value[:, :, :, e0]**2*meshtal.error[:, :, :,e0]**2
                       for e0 in range(pos,pos+ebinmap[e])]
        addvaldiv = np.where(addval!=0, addval, 1)  # We do this to avoid dividing by zero for blank values
        adderr = np.sqrt(np.sum(arrayadderr, axis=0)/(addvaldiv**2))
        result.error[:, :, :, e+1] = adderr
        pos = pos+ebinmap[e]  # Move to next block of energy bins.

    result.value[:, :, :, 0] = meshtal.value[:, :, :, 0]  # Total does not change
    result.error[:, :, :, 0] = meshtal.error[:, :, :, 0]  # Total does not change
    result.comment = "{A}, with collapsed energies as {B}".format(A=meshtal.comment[:-1], B=ebinmap)
    return result


def merge(*meshtalarray):
    """Merge array of mesh tallies meshtalarray into mesh tally result"""
    basetally = meshtalarray[0] # More or less as the MCNP tool.
    if not Geoeq(*meshtalarray):
        print('Tallys do not match and heterogeneous tally merging is not implemented. Sorry')
        return None
    for meshtal in meshtalarray:
        if meshtal.modID!=basetally.modID:
            print('BIG FAT WARNING: Non-matching model ID found. Make sure you know what you\
                  are doing, if you do not, IT IS NOT MY PROBLEM!')
    result = copy(basetally, exclude=['value', 'error', 'nps'])
    nps = sum([tally.nps  for tally in meshtalarray])
    result.nps = nps

    # Now the results and errors
    for (i, j, k, e) in np.ndindex(basetally.iints, basetally.jints, basetally.kints, basetally.eints):
        mergeval = 0
        mergeerr = 0
        w = []
        for tally in meshtalarray:
            mergeval = tally.value[i,j,k,e]*tally.nps+mergeval
            w0 = tally.nps*(tally.nps*tally.error[i, j, k, e]**2+1)*tally.value[i, j, k, e]**2
            w.append(w0)
            result.value[i, j, k, e] = mergeval/nps
            if mergeval != 0:
                result.error[i, j, k, e] = sqrt((sum(w)/nps-mergeval**2/nps**2)/(mergeval**2/nps))
            else:
                result.error[i, j, k, e] = 0
    return result


def voxelmerge(meshtal, voxelmap):
    """ Merge voxels of meshtal according to numpy array voxelmap. Returns a dictionary with value
        and error arrays which are analogous to a single cell mesh tally.
        WARNING:Becuase tally contributions to different cell often come from the same event,
        information is lost and errors are a mere aproximation. Use with caution!!
        Voxelmap must be a 3x2 map stating the    subset of voxels to merge
    """

    if not hasattr(voxelmap,'shape'):
        print("voxelmap does not look like a Numpy array, aborting")
        return
    if voxelmap.shape != (3, 2):
        print("Voxelmap has wrong shape. Aborting")
        return
    for i in range(3):
        if voxelmap[i, 1] <= voxelmap[i, 0]:
            print("This voxelmap doesn't look good to me")
            return
        for j in range(2):
            if not voxelmap[i, j].is_integer():
                print("WARNING: voxelmap value not integer at index {i},{j}. This is not fatal to\
                      the method, but something smells fishy here".format(i=i,j=j))

    ii = voxelmap[0].astype(int)
    jj = voxelmap[1].astype(int)
    kk = voxelmap[2].astype(int)
    n = (ii[1]-ii[0]) * (jj[1]-jj[0]) * (kk[1]-kk[0])
    Result = meshtal.value[ii[0]:ii[1], jj[0]:jj[1], kk[0]:kk[1], :]
    Error = meshtal.error[ii[0]:ii[1], jj[0]:jj[1], kk[0]:kk[1], :]
    Volume = meshtal.volume[ii[0]:ii[1], jj[0]:jj[1], kk[0]:kk[1], :]
    Integral = np.zeros((ii[1]-ii[0], jj[1]-jj[0], kk[1]-kk[0], meshtal.eints+1))
    for e in range(meshtal.eints+1):
        Integral[:, :, :, e] = Result[:, :, :, e] * Volume
    Ave = np.zeros(meshtal.eints+1)
    for e in range(meshtal.eints+1):
        Ave[e] = Integral[:, :, :, e].sum()/Volume.sum()
    w = np.zeros((ii[1]-ii[0], jj[1]-jj[0], kk[1]-kk[0], meshtal.eints+1))
    for e in range(meshtal.eints+1):
        w[:, :, :, e] = (Error[:, :, :, e]**2+1)*(Ave[e]**2) # We use the meshtal_merge formula with constant NPS
    print(n)
    Err = [sqrt((w[:, :, :, e].sum()/n-Ave[e]**2) / (n*Ave[e]**2)) for e in range(meshtal.eints+1)]
    return  {'value':Ave, 'error':Err}


def xyzput(tally,ofile):
    """Write a meshtal point list in ofile with the data of tally.
    Autoconvert if tally is cylindrical """
#Preliminary check
    if type(tally)!=MeshTally:
        print("Argument #0 is not a meshtally object")
    if tally.eints > 1:
        print("WARNING: Multiple energy tally. Dumping only total energy")
    if tally.geom=="Cyl":
        AXS = tally.axis
        XVEC = tally.vec
        YVEC = np.cross(AXS,XVEC)
    with open(ofile+'.csv', "w") as putfile:
        putfile.write('X Y Z TallyValue TallyError\n')
        for i in range(tally.iints):
            for j in range(tally.jints):
                for k in range(tally.kints):
                    if tally.geom=="Cyl":
                        R = (tally.ibins[i]+tally.ibins[i+1])/2
                        Z = (tally.jbins[j]+tally.jbins[j+1])/2
                        Theta = (tally.kbins[k]+tally.kbins[k+1])/2
                        XYZ = R*(XVEC*cos(2*pi*Theta)+YVEC*sin(2*pi*Theta))+Z*AXS+tally.origin
                    else:
                        X = (tally.ibins[i]+tally.ibins[i+1])/2
                        Y = (tally.jbins[j]+tally.jbins[j+1])/2
                        Z = (tally.kbins[k]+tally.kbins[k+1])/2
                        XYZ = [X,Y,Z]+tally.origin
                    putfile.write("{0} {1} {2} {3} {4}\n".format(XYZ[0],XYZ[1],XYZ[2],
                                          tally.value[i,j,k,-1],tally.error[i,j,k,-1]))


def fput(tallylist,ofile):
    """Write a meshtal file ofile with the data of tallylist. ProbID and nps MUST match"""
    print("Not implemented. You are welcome to do it yourself!")
    for tally in tallylist:
        for e in tally.eints:
            for i in tally.iints:
                for j in tally.jints:
                    for k in tally.kints:
                        pass


def wwrite_auto(ofile='wwout_auto', *tallies, **kwargs):
    wwrite(ofile, None, None, *tallies, **kwargs)
    return

# def wwrite(*tallies,ofile='wwout',scale=None,wmin=None):
def wwrite(ofile='wwout', scale=None, wmin=None, *tallies, **kwargs):
    #  TODO: Maybe we should rewrite this with **kwargs, even if it screws up virtually every script out there.
    # Bonus TODO: Implement wmin value for anything above an uncertainty.
    """ Write a MAGIC-like weight window file from tallies to ofile,
        using wmin minimal weight and scale agressivity.
        Tally geometrical consistency and particle non-redundancy is checked.
        Mind you, currently time dependency is NOT supported.
    """
    
   # Preliminary checks:
    for tally in tallies[1:]:
        if tally.part == tallies[0].part:
            print("tally type collision detected: At least two tallies are of the same particles.\
                  Please check your inputs. Quitting")
            return
    if not Geoeq(*tallies):
        print("Tallies do not match geometrically. Quitting")
        return

    # if scale==None and not wmin==None:
    #     print("You have specified minimal weight but not scaling factor. While this could actually be implemented, my creator does not like the idea. Quitting")
    #     return
    # Tally sorting acordint tp IPT:

    sorted(tallies, key=lambda tally: IPT[tally.part])
    # Check
    print([tal.part for tal in tallies])

    if scale == None:  # 
        scale = np.zeros(len(tallies))
        # wmin = np.zeros(len(tallies))
        for i, tally in enumerate(tallies):
            h = HealthReport(tally)
            scale[i] = h.fractionbelowE(0.1)/h.fractionbelowE(1)
            if scale[i] == 0:
                print("Tally #{0} has nothing below threshold uncertainty.\
                      Please manually provide scaling values".format(i))
                return
            print("Scale for tally{0} :{1}\n".format(i,scale[i]))
    if not hasattr(scale,'len'):
        scale=np.ones(len(tallies))*scale
    
    if  wmin == None:
        wmin = np.zeros(len(tallies))
        for i, tally in enumerate(tallies):
            maxval = tally.value.max()
            h = HealthReport(tally)
            midval = h.mingoodval(0.1)
            if midval == 0:
                print("Tally #{0} has nothing below threshold uncertainty. \
                      Please manually provide scaling values".format(i))
                return
            wmin[i] = (midval/maxval) ** scale[i]
            print("Minimal weight for tally{0}: {1:.3E}\n".format(i,wmin[i]))
    if not hasattr(wmin, 'len'):
        wmin = np.ones(len(tallies))*wmin

    wmin_head = wmin[0]  
    scale_head = scale[0]
    top_cap = kwargs.get("top_cap", 0)
    if top_cap == 0:
        wwinpID = ("{0:>5.2f} {1:5.1E} {2:}".format(scale_head, wmin_head, "nocap"))
    else:
        wwinpID = ("{0:>5.2f} {1:5.1E} {2:5.0E}".format(scale_head,wmin_head,top_cap))

#        print(wwinpID)
#        print(tally.probID)


# A litte explanation on this: Due to the WWINP format, we need to transform the bins into
# a coarse mesh with homogeneous fine divisions inside.
    tally = tallies[0]
    fineiints = [1]
    coarseimesh = [tally.ibins[0]]
    finejints = [1]
    coarsejmesh = [tally.jbins[0]]
    finekints = [1]
    coarsekmesh = [tally.kbins[0]]
    npart = max([IPT[tally.part] for tally in tallies])
#    print(npart)

    bins = [tally.ibins, tally.jbins, tally.kbins]
    coarses = [coarseimesh, coarsejmesh, coarsekmesh]
    fines = [fineiints, finejints, finekints]
    for [mesh, coarse, fine] in zip(bins, coarses, fines):
        diffs = np.diff(mesh)
        for i, diff in enumerate(diffs[:-1]):
            if not np.isclose(diff, diffs[i+1], 1e-2):  #   Yes, we actually have to use that, because MCNP in its infinite wisdom writes approximate bin values
                coarse.append(mesh[i+1])
                fine.append(1)
            else:
                fine[-1] = fine[-1] + 1
        coarse.append(mesh[-1])

#lets check
    print('fineiints',fineiints)
    print('finejints',finejints)
    print('finekints',finekints)
    print('coarseimesh',coarseimesh)
    print('coarsejmesh',coarsejmesh)
    print('coarsekmesh',coarsekmesh)

    with open(ofile,"w") as wwfile:

#BLOCK 1        
        if tally.geom=="XYZ":
            igeom=10
            x0 = tally.ibins[0]
            y0 = tally.jbins[0]
            z0 = tally.kbins[0]
            nwg = 1
        else:
            igeom = 16 
            [x0, y0, z0] = tally.origin
            nwg = 2

        wwfile.write("{:>10n}{:>10n}{:>10n}{:>10n}                    {probid}\n".format(1,1,npart,igeom ,probid=wwinpID))
#        wwfile.write("{:>10n}{:>10n}{:>10n}{:>10n}                    {probid}\n".format(1,1,npart,igeom ,probid=tally.probID))
        
        ne = np.zeros(npart) # This is the equally named variable in the wwout file
        for tally in tallies:
            ne[IPT[tally.part]-1] = tally.eints
        # Second line, energies per particle types
#        print(ne)
        for i, nei in enumerate(ne):
            wwfile.write("{:>10n}".format(nei))
            if (i+1) % 7 == 0 or i+1 == len(ne):
                wwfile.write("\n")

        #array of tally location:
        wwfile.write("{0:>13.5E}{1:13.5E}{2:13.5E}{3:13.5E}{4:13.5E}{5:13.5E}\n".
                     format(tally.iints,tally.jints,tally.kints,x0,y0,z0))
        
        if igeom==10:  #remember, cartesian
            wwfile.write("{0:13.5E}{1:13.5E}{2:13.5E}{3:13.5E}\n".format(len(coarseimesh)-1,len(coarsejmesh)-1,len(coarsekmesh)-1,1))
        else: # cylindrical
            x1 = x0+tally.axis[0]*(tally.jbins[-1] - tally.jbins[0])
            y1 = y0+tally.axis[1]*(tally.jbins[-1] - tally.jbins[0])
            z1 = z0+tally.axis[2]*(tally.jbins[-1] - tally.jbins[0])

            x2 = x0+tally.vec[0]*(tally.ibins[-1] - tally.ibins[0])
            y2 = y0+tally.vec[1]*(tally.ibins[-1] - tally.ibins[0])
            z2 = z0+tally.vec[2]*(tally.ibins[-1] - tally.ibins[0])

            wwfile.write("{0:13.5E}{1:13.5E}{2:13.5E}{3:13.5E}{4:13.5E}{5:13.5E}\n".format(len(coarseimesh)-1,len(coarsejmesh)-1,len(coarsekmesh)-1,x1,y1,z1))
            wwfile.write("{0:13.5E}{1:13.5E}{2:13.5E}{3:13.5E}\n".format(x2,y2,z2,2))
           
# BLOCK 2 
        for [mesh, coarse, fine] in zip(bins, coarses, fines):
            mesharray = [mesh[0]]
            for i,v in enumerate(fine):
                mesharray.append(fine[i])
                mesharray.append(coarse[i+1])
                mesharray.append(1)

            print('The mesh array is',mesharray)
            for i in range(0,len(mesharray)-6,6):
                wwfile.write(''.join('{0:13.5E}{1:13.5E}{2:13.5E}{3:13.5E}{4:13.5E}{5:13.5E}\n'.format(*mesharray[i:i+6])))
            remains = np.mod(len(mesharray), 6) # the number of last elements of mesharray

            wwfile.write(''.join('{0:13.5E}'.format(mesharray[-i]) for i in range(remains,0,-1)))
            wwfile.write('\n')

#   BLOCK 3
        # We unroll all the tally values, since this is actually the "logic" of MCNP
        # and, while we are at it, scale and cap them. This must be done for all tallies
    ntal=0
    for tally in tallies:
        nwwma = tally.iints*tally.jints*tally.kints
        WW = np.zeros((nwwma, tally.eints))
        WW_topcap = np.zeros((tally.iints, tally.jints, tally.kints))
        for e in range(tally.eints):
            WW[:, e] = tally.value[:, :, :, e+1].flatten(order="F")
# Exponential attenuation used in BeamLine Guides #
        idim = tally.ibins[-1]-tally.ibins[0]
        for i in range(tally.iints):
            WW_topcap[i] = (wmin[ntal])**(((tally.ibins[i]-tally.ibins[0])/idim*top_cap))
#            print(WW_topcap[i, -1, -1])

        Wmax = WW.max()
        print('Max value=', Wmax)
        #Normalize & scale
        aggro = scale[ntal]
        for e in range(tally.eints):
            for i, v in enumerate(WW[:, e]):
                WW[i, e] = max((v/Wmax)**aggro, wmin[ntal])

        #top_cap
        if top_cap == 0:
            print('NO upper cap on wwinp')

        for e in range(tally.eints):
            l=0
            for k in range(tally.kints):
                for j in range(tally.jints):
                    for i in range(tally.iints):
                        WW[l, e] = min(WW[l, e], WW_topcap[i, j, k])
                        tally.value_ww[i,j,k,0]=WW[l,e]
                        l = l+1
            if top_cap != 0:
                cont = np.count_nonzero(tally.value_ww[:, :, :, e] == WW_topcap)
                print(cont,' values modified by an upper cap for energy bin', e)

        with open(ofile, "a") as wwfile:
            #print
            for e in range(tally.eints):
                wwfile.write('{0:13.5E} '.format(tally.ebins[e+1]))
                if (e % 6 == 0) or (e == tally.eints):
                    wwfile.write('\n')
            for e in range(tally.eints):
                for i in range(0,len(WW)-6,6):
                    wwfile.write(''.join('{0:13.5E}{1:13.5E}{2:13.5E}{3:13.5E}{4:13.5E}{5:13.5E}\n'.format(*WW[i:i+6, e])))
                remains=np.mod(len(WW),6) # the number of last elements of WW
                if remains==0:
                    remains=6 # the number of elements is a multiple of 6, so the last line is full
                wwfile.write(''.join('{0:13.5E}'.format(WW[-i,e]) for i in range(remains,0,-1)))
                wwfile.write('\n')
        ntal = ntal+1
    return


def conv_Cilind(Axs, Vec, origin, XYZ):
    if len(XYZ) != 3:
        print("input coordinate not a Triad")
        return
    if len(Vec) != 3:
        print("Vector coordinate not a Triad")
        return
    if len(Axs) != 3:
        print("Axis coordinate not a Triad")
        return
    # Transform to arrays
    Axs = np.array(Axs)
    Vec = np.array(Vec)
    origin = np.array(origin)
    XYZ = np.array(XYZ)
    
    Axs = Axs/np.linalg.norm(Axs)
    Vec = Vec/np.linalg.norm(Vec)  # Normalize the Axs and Vec vector, just in case!!
    XYZ = XYZ-origin  # Displacement made
    L2 = np.dot(XYZ, XYZ)
    Z = np.dot(XYZ, Axs)
    R2 = L2-pow(Z, 2)
    R = sqrt(R2)

    Radial = XYZ - Axs*Z
    X = np.dot(Radial, Vec)
    YVec = np.cross(Axs, Vec)
    Y = np.dot(Radial, YVec)
    Theta = atan2(Y, X) % (2*pi)
    Theta = Theta/(2*pi)  # Because Numpy gives the results in radian and we want revolutions.
    return(R, Z, Theta)


def conv_Cilindricas_multi(Axs,Vec,origin,XYZ):   #TODO: Should use the above function in loop
    if len(Vec)!=3:
        print("Vector coordinate not a Triad")
        return
    if len(Axs)!=3:
        print("Axis coordinate not a Triad")
        return
    Axs2 = np.dot(Axs,Axs)
    Vec2 = np.dot(Vec,Vec)
    YVec = np.cross(Axs,Vec)
    Transformed = []
    XYZ = XYZ-origin
    print("\nTransforming geometry")
    for i in range(3):
        Axs[i]=Axs[i]/Axs2
        Vec[i]=Vec[i]/Vec2  # Normalize the Axs and Vec vector, just in case!!
    for point in tqdm(XYZ,position=0, unit='part', unit_scale=True):
        L = np.linalg.norm(point)
        Z = np.dot(point,Axs)
        R2 = pow(L,2)-pow(Z,2)
        Radial = point-np.multiply(Axs,Z)
        X = np.dot(Radial,Vec)
        Y = np.dot(Radial,YVec)
        Theta = atan2(Y,X)
        R = sqrt(R2)
        Theta = Theta/(2*pi)  # Because Numpy gives the results in radian and we want revolutions...
        if Theta<0:
            Theta=Theta+1
        Transformed.append([R,Z,Theta])
#        j = j+1
#        if ((j+1)% 1e5==0):
#            print (j+1,' transformed points')
   #         print (Transformed[:-1])
    return(Transformed)


def add(*tallies):
    """ Add the tallies (2+) in the input.  Geometry must match or it will fail."""
    RefTal = tallies[0]
    Part = RefTal.part
    ee = RefTal.ebins
    print("checking tally consistency")

    for tally in tallies[1:]:
        if not Geoeq(tally, RefTal):
            print("Tally {ntally} Geometry does not match tally {nref}, adding them is beyond my current capabilites. Sorry".format(ntally=tally.n,nref=RefTal.n))
            return None
        if tally.part != Part:
            confirm = input("Tally {ntally} and tally {nref}, are for different particles. Do you REALLY know what you are doing??(Y/N).".format(ntally=tally.n,nref=RefTal.n))
            if confirm not in ["Y","y"]:
                print("Cancelling")
                return None
            else:
                print("Very well")
        if not np.array_equal(tally.ebins, ee):
            print("WARNING: Energy bins not matching. This can be OK, but make sure you know what you are doing!")
    Result = copy (RefTal, exclude=['probID', 'comment', 'value', 'error'])
    Result.probID = "Generated by meshtal class from {probID}".format(probID=RefTal.probID)
    Result.comment = "Tallies added: {valor}".format(valor=[tally.n for tally in tallies])
    Result.value = sum([tally.value for tally in tallies])
    totnps = sum([tally.nps for tally in tallies])
    for (i, j, k, e) in np.ndindex(Result.iints, Result. jints, Result.kints, Result.eints):
        w = []
        for tally in tallies:
            w0 = pow(tally.error[i, j, k, e], 2)*pow(tally.value[i, j, k, e], 2)
            w.append(w0)
        if (Result.value[i, j, k, e] != 0):
            Result.error[i, j, k, e] = sqrt(sum(w)/pow(Result.value[i, j, k, e], 2))
        else:
            Result.error[i, j, k, e] = 0
    Result.nps = totnps
    return Result


def smooth(Tally, maxfactor, ebin=0):  # TODO: This should be a class method, not a module one
    """Smoothes out a meshtally so that no voxel may stand out a factor of maxfactor
    from his neighbourss. Highly experimental and completely risky to use"""
#   Object check
    if not hasattr(Tally, 'value'):
        print("Uh, uh, First argument does not seem like a meshtal object. Quitting.")
        return None
    import itertools 
    neighbours = np.full((Tally.iints, Tally.jints, Tally.kints), 1) 
    for i in range(Tally.iints):
        ineighbours = [i]
        if i!=0:
            ineighbours.append(i-1)
        if i!=Tally.iints-1:
            ineighbours.append(i+1)
        for j in range(Tally.jints):
            jneighbours = [j]
            if j!=0:
                jneighbours.append(j-1)
            if j!=Tally.jints-1:
                jneighbours.append(j+1)
                for k in range(Tally.kints):
                    kneighbours = [k]
                if k!=0:
                    kneighbours.append(k-1)
                if k!=Tally.kints-1:
                    kneighbours.append(k+1)
                neighbours = list(itertools.product(ineighbours,jneighbours,kneighbours))
                neighbours.remove((i,j,k))
#                MaxN=max([Tally.value[n[0],n[1],n[2],ebin] for n in neighbours])
                MaxN = np.mean([Tally.value[n[0],n[1],n[2],ebin] for n in neighbours])
#                MaxN=np.exp(np.mean(np.log([Tally.value[n[0],n[1],n[2],ebin] for n in neighbours])))
                if Tally.value[i, j, k, ebin] > MaxN*maxfactor:
                    print ("point at {i},{j},{k} is slated for reduction".format(i=i,j=j,k=k))
                    print ("Value reduced from:", Tally.value[i,j,k,ebin])
                    Tally.value[i, j, k, ebin] = 0.9*MaxN*maxfactor
                    print ("To:", Tally.value[i, j, k, ebin])


def ww_get(infile='wwinp'):  
#BLOCK 1
    with open (infile,"r") as ww_file:
        header = ww_file.readline() 
        if len(header)>4:
            wwprobID = header.split()[4:] # got problem ID
        else:   
            wwprobID = "no ID provided"
        wwnpart = int(header.split()[2])  # particle number
        wwgeom = header.split()[3]  # define geometry
#      print(wwgeom)

        line = ww_file.readline()
        eints = np.zeros(wwnpart, dtype=int)
        for p in range(wwnpart):
            eints[p] = line.split()[p]
        print(eints)
        line = ww_file.readline() # mesh bins
        iints = int(float(line.split()[0]))
        jints = int(float(line.split()[1]))
        kints = int(float(line.split()[2]))
        x0 = round(float(line.split()[3]), 2)
        y0 = round(float(line.split()[4]), 2)
        z0 = round(float(line.split()[5]), 2)
        tallylist = []
        for p in range(wwnpart):
            tally = MeshTally(iints, jints, kints, eints[p])
            tallylist.append(tally)
        #print(iints,jints,kints,x0,y0,z0)

        line = ww_file.readline() # coarse mesh bins
        coarseimesh = int(float(line.split()[0]))+1
        coarsejmesh = int(float(line.split()[1]))+1
        coarsekmesh = int(float(line.split()[2]))+1
        nwg = int(float(line.split()[3])) # Geometry type
#      print(line)

# BLOCK 2
# Construct the ibins, jbins, kbins arrays

        ibins = np.zeros(iints+1)
        jbins = np.zeros(jints+1)
        kbins = np.zeros(kints+1)
        maxbins = max(iints,jints,kints)+1  #TODO: Pretty sure there is not a good reason for this
        bins = np.zeros((3, maxbins))
        for dim in [0, 1, 2]:
            mesharray = []
            while True:   #
                line = ww_file.readline()  # x axis
                for element in line.split():
                    mesharray.append(element)
                if len(line.split()) in [1,4]:
                    break
#            print(mesharray)
            j=0
            bins [dim,0] = mesharray[0]
            for i in range(1,len(mesharray),3):
                bins[dim,j+int(float(mesharray[i]))]=float(mesharray[i+1])
                interval = (float(mesharray[i+1])-bins[dim,j])/int(float(mesharray[i]))
#                print(interval)
                for k in range(int(float(mesharray[i]))):
                    bins[dim, j+k] = bins[dim, j]+interval*k
                j = j+int(float(mesharray[i]))
        ibins = bins[0, 0:iints+1]
        jbins = bins[1, 0:jints+1]
        kbins = bins[2, 0:kints+1]
#        print(ibins)
#        print(jbins)
#        print(kbins)

        for p in range(wwnpart):
            nwwma = iints*jints*kints
#            print('nwwma',nwwma)
            ww_value = np.zeros((nwwma,eints[p]))
            ebins = np.zeros(1) 
            while True:
                line = ww_file.readline()  # energy bin
#                print(line)
                for e in line.split():
                    ebins = np.append(ebins, float(e))
                if ebins.size>eints[p]:
                    break
#            print(ebins)
            min_value=1 
            for e in range(eints[p]):
                for i in range(0, nwwma, 6):
                    line = ww_file.readline()
#                    print(line)
                    ndata_line = len(line.split()) # para que no pete si los voxel no son multiplos de 6
#                    print(ndata_line)
                    for j in range(0,ndata_line):
                        ww_value[i+j, e] = float(line.split()[j])
                        if min_value > float(line.split()[j]):
                            min_value = float(line.split()[j])
            print(min_value)
            if wwgeom == "10":
                for e in range(eints[p]):
                    l=0
                    for k in range(kints):
                        for j in range(jints):
                            for i in range(iints):
                                tallylist[p].value[i,j,k,e]=ww_value[l,e]
                                if ww_value[l,e] != min_value:
                                    tallylist[p].error[i,j,k,e] = 1 # add free info about real data of wwinp
#                  print(e,k,j,i,l,ww_value[l,e])
                                l=l+1
            tallylist[p].ebins=ebins
            tallylist[p].ibins=ibins  # Aren't all the same?!
            tallylist[p].jbins=jbins
            tallylist[p].kbins=kbins
#   if wwgeom == '16':
#      tally.geom="CYL"
#      tally.origin=[x0,y0,z0]
#      print('cylindrical wwinp, not developed... sorry')
#      return
#      
#   
#   print(tally.geom,tally.iints,tally.jints,tally.kints,tally.eints)
##   print(tally.ibins, tally.jbins, tally.kbins,tally.ebins) 
#   
#   mt.vtkwrite(tally,infile+'.vtk')
#   
##   print(coarseimesh,coarsejmesh,coarsekmesh,nwg)
    return tallylist


def SEAM(*meshtalarray):
    """Smart Error Aware Merger. Merges mesh tallies in meshtalarray giving different weight 
    to the results according to their statistical error. For instance, if one of the tallies has 
    very good statistic in one voxel (say below 0.05), and the other tallies are poor (over 0.5), 
    the result will be the one from the first tally. Exact methodology to be discussed and set.
    Highly experimental. May provide wrong results, eat your ice cream or set your house on fire.
    Use at your own risk.
    """
    basetally=meshtalarray[0] # More or less as the MCNP tool. 
    if not Geoeq(*meshtalarray):
        print('Tallys do not match and heterogeneous tally merging is not implemented. Sorry')
        return None
    for meshtal in meshtalarray:
        if meshtal.modID!=basetally.modID:
            print('BIG FAT WARNING: Non-matching model ID found. Make sure you know what you are doing, if you do not, IT IS NOT MY PROBLEM!')
    result = copy(basetally, exclude=['value', 'error', 'nps'])
    
    nps = sum([tally.nps for tally in meshtalarray])
    result.nps = nps
  
    # Now the results and errors
    for i in range(basetally.iints):
        for j in range(basetally.jints):
            for k in range(basetally.kints): 
                for e in range(basetally.eints+1): 
                    print(i, j, k, e)
                    errors = [tally.error[i, j, k, e] for tally in meshtalarray]
                    values = [tally.value[i, j, k, e] for tally in meshtalarray]
                    mergeval = 0
                    mergeerr = 0  # TODO: This does NOT seem well thought, review algo
                    totalweight = 0
                    w=[]
                    if sum(values)==0:
                        result.value[i, j, k, e] = 0
                        result.error[i, j, k, e] = 0
                        continue
                    minerror = min(filter(lambda i: i >0,[errors]))
                    for tally in meshtalarray:
                        if tally.error[i , j, k, e]==0:
                            w0 = 0
                        elif minerror<0.1:
                            if tally.error[i , j, k, e]>0.5:
                                w0 = 0
                            else:
                                w0 = (minerror/tally.error[i, j, k, e])**2
                        else:
                            w0 = (minerror/tally.error[i, j, k, e])**2
                        w.append(w0)
                    result.value[i, j, k, e] = np.dot(w, errors)/sum(w)
                    result.error[i, j, k, e] = minerror
    return result

def ratio(RefTal,DivTal):
    """ Makes a ratio between meshtally1 and meshtally2 (mesh1/mesh2).  Geometry must match or it will fail."""
    Part = RefTal.part
    ee = RefTal.ebins
    print("checking tally consistency")

    if not Geoeq(DivTal, RefTal):
        print("Tally {ntally} Geometry does not match tally {nref}, adding them is beyond my current capabilites. Sorry".format(ntally=DivTal.n,nref=RefTal.n))
        return None
    if DivTal.part != Part:
        confirm = input("Tally {ntally} and tally {nref}, are for different particles. Do you REALLY know what you are doing??(Y/N).".format(ntally=DivTal.n,nref=RefTal.n))
        if confirm not in ["Y","y"]:
            print("Cancelling")
            return None
        else:
            print("Very well")
    if not np.array_equal(DivTal.ebins, ee):
        print("WARNING: Energy bins not matching. This can be OK, but make sure you know what you are doing!")
    Result = copy (RefTal, exclude=['probID', 'comment', 'value', 'error'])
    Result.probID = "Generated by meshtal class from {probID}".format(probID=RefTal.probID)
    Result.comment = "Tallies compared: {0}/{1}".format(RefTal.n,DivTal.n)
    for (i, j, k, e) in np.ndindex(Result.iints, Result.jints, Result.kints, Result.eints):
        if DivTal.value[i,j,k,e] != 0:
            Result.value[i,j,k,e] = RefTal.value[i,j,k,e]/DivTal.value[i,j,k,e]
            if RefTal.error[i,j,k,e] == 1 or DivTal.error[i,j,k,e] == 1:
                Result.error[i,j,k,e] = 1
            else:
                Result.error[i,j,k,e] = (sqrt(pow(RefTal.error[i,j,k,e],2) + pow(DivTal.error[i,j,k,e],2)))
        else:
            Result.value[i,j,k,e] = 0
            Result.error[i,j,k,e] = 0
    return Result

def combine(*tallies):
    """ Mix the tallies in the input to remove voxel with value 0 and average the rest of them. 
                                        Geometry must match or it will fail."""
    RefTal = tallies[0]
    Part = RefTal.part
    ee = RefTal.ebins
    print("checking tally consistency")

    for tally in tallies[1:]:
        if not Geoeq(tally, RefTal):
            print("Tally {ntally} Geometry does not match tally {nref}, adding them is beyond my current capabilites. Sorry".format(ntally=tally.n,nref=RefTal.n))
            return None
        if tally.part != Part:
            confirm = input("Tally {ntally} and tally {nref}, are for different particles. Do you REALLY know what you are doing??(Y/N).".format(ntally=tally.n,nref=RefTal.n))
            if confirm not in ["Y","y"]:
                print("Cancelling")
                return None
            else:
                print("Very well")
        if not np.array_equal(tally.ebins, ee):
            print("WARNING: Energy bins not matching. This can be OK, but make sure you know what you are doing!")
    Result = copy (RefTal, exclude=['probID', 'comment', 'value', 'error'])
    Result.probID = "Generated by meshtal class from {probID}".format(probID=RefTal.probID)
    Result.comment = "Tallies combine: {valor}".format(valor=[tally.n for tally in tallies])
    for (i, j, k, e) in np.ndindex(Result.iints, Result. jints, Result.kints, Result.eints):
        count=0
        for tally in tallies:
            if tally.value[i, j, k, e] != 0:
                Result.value[i, j, k, e] = Result.value[i, j, k, e] + tally.value[i, j, k, e]
                count += 1
#        print(count)
        Result.value[i, j, k, e]/count
    totnps = sum([int(tally.nps) for tally in tallies])
    for (i, j, k, e) in np.ndindex(Result.iints, Result. jints, Result.kints, Result.eints):
        w = []
        for tally in tallies:
            w0 = pow(tally.error[i, j, k, e], 2)*pow(tally.value[i, j, k, e], 2)
            w.append(w0)
        if (Result.value[i, j, k, e] != 0):
            Result.error[i, j, k, e] = sqrt(sum(w)/pow(Result.value[i, j, k, e], 2))
        else:
            Result.error[i, j, k, e] = 0
    Result.nps = totnps
    return Result
