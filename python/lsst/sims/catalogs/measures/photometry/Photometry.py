"""
photUtils - 


ljones@astro.washington.edu  (and ajc@astro.washington.edu)

Collection of utilities to aid usage of Sed and Bandpass with dictionaries.

"""

import os
import numpy
import palpy as pal
import lsst.sims.catalogs.measures.photometry.Sed as Sed
import lsst.sims.catalogs.measures.photometry.Bandpass as Bandpass
from lsst.sims.catalogs.measures.instance import compound

class Photometry(object):
    
    bandPasses = {}
    bandPassKey = []   
    phiArray = None
    waveLenStep = None
    
    def setupPhiArray_dict(self,bandpassDict, bandpassKeys):
        """ Generate 2-dimensional numpy array for Phi values in the bandpassDict.

        You must pass in bandpassKeys so that the ORDER of the phiArray and the order of the magnitudes returned by
        manyMagCalc can be preserved. You only have to do this ONCE and can then reuse phiArray many times for many
        manyMagCalculations."""
        # Make a list of the bandpassDict for phiArray - in the ORDER of the bandpassKeys
        bplist = []
        for f in bandpassKeys:
            bplist.append(bandpassDict[f])
        sedobj = Sed()
        self.phiArray, self.waveLenStep = sedobj.setupPhiArray(bplist)

    def loadBandPasses(self,bandPassList):
        """
        This will take the list of band passes in bandPassList and use them to set up
        self.phiArray and self.waveLenStep (which is being cached so that it does not have
        to be loaded again unless we change which bandpasses we want)
        """
        if self.bandPassKey != bandPassList:
            self.bandPassKey=[]
            self.bandPasses={}
            path = os.getenv('LSST_THROUGHPUTS_DEFAULT')
            for i in range(len(bandPassList)):
                self.bandPassKey.append(bandPassList[i])
            
            for w in self.bandPassKey:    
                self.bandPasses[w] = Bandpass()
                self.bandPasses[w].readThroughput(os.path.join(path,"total_%s.dat"%w))
        
            self.setupPhiArray_dict(self.bandPasses,self.bandPassKey)
            
    # Handy routines for handling Sed/Bandpass routines with sets of dictionaries.
    def loadSeds(self,sedList, magNorm=15.0, resample_same=False, subDir=None):
        """Generate dictionary of SEDs required for generating magnitudes

        Given a dataDir and a list of seds return a dictionary with sedName and sed as key, value
        """    
        
        if subDir == None:
            subDir = "/starSED/kurucz/
        
        dataDir=os.getenv('SED_DATA')+subDir
        
        imsimband = Bandpass()
        imsimband.imsimBandpass()
        sedDict={}
        firstsed = True
        for sedName in sedList:
            if sedName == None:
                continue
            elif sedName in sedDict:
                continue
            else:            
                sed = Sed()
                sed.readSED_flambda(os.path.join(dataDir, sedName))
                if resample_same:
                    if firstsed:
                        wavelen_same = sed.wavelen
                        firstsed = False
                    else:
                        if sed.needResample(wavelen_same):
                            sed.resampleSED(wavelen_same)
                
                fNorm = sed.calcFluxNorm(magNorm, imsimband)
                sed.multiplyFluxNorm(fNorm)
                

                
                sedDict[sedName] = sed
                
        return sedDict
    
    def applyAvAndRedshift(self,sedNames,sedDict,internalAv=None,redshift=None):
        
        for sedName in sedNames:
            if internalAv:
                a_int, b_int = sedDict[sedName].setupCCMab()
                sedDict[sedName].addCCMDust(a_int, b_int, A_v=internalAv)
            if redshift:
                sedDict[sedName].redshiftSED(redshift, dimming=True)
                sedDict[sedName].resampleSED(wavelen_match=self.bandPasses[self.bandPassKey[0]].waveln)
            
        
    
    def manyMagCalc_dict(self,sedobj, phiArray, wavelenstep, bandpassDict, bandpassKeys):
        """Return a dictionary of magnitudes for a single Sed object.

        You must pass the sed itself, phiArray and wavelenstep for the manyMagCalc itself, but
        you must also pass the bandpassDictionary and keys so that the sedobj can be resampled onto
        the correct wavelength range for the bandpass (i.e. maybe you redshifted sedobj??) and so that the
        order of the magnitude calculation / dictionary assignment is preserved from the phiArray setup previously.
        Note that THIS WILL change sedobj by resampling it onto the required wavelength range. """
        # Set up the SED for using manyMagCalc - note that this CHANGES sedobj
        # Have to check that the wavelength range for sedobj matches bandpass - this is why the dictionary is passed in.
        if sedobj.needResample(wavelen_match=bandpassDict[bandpassKeys[0]].wavelen):
            sedobj.resampleSED(wavelen_match=bandpassDict[bandpassKeys[0]].wavelen)
        sedobj.flambdaTofnu()
        magArray = sedobj.manyMagCalc(phiArray, wavelenstep)
        magDict = {}
        i = 0
        for f in bandpassKeys:
            magDict[f] = magArray[i]
            i = i + 1
        return magDict
    
    def calculate_magnitudes(self,bandPassList,sedNames,magNorm=15.0, internalAv=None, redshift=None, subDir=None):
        """
        This will return a dict of dicts of magnitudes.  The first index will be the SED name.
        The second index will be the band pass key (which is taken form bandPassList).
        """
        
        self.loadBandPasses(bandPassList)
        sedDict=self.loadSeds(sedNames,magNorm,subDir=subDir)
        
        self.applyAvAndRedshift(sedNames,sedDict,internalAv=internalAv,redshift=redshift)
        
        magDict={}
        for sedName in sedNames:
            subdict=self.manyMagCalc_dict(sedDict[sedName],self.phiArray,self.waveLenStep,self.bandPasses,self.bandPassKey)
            magDict[sedName]=subdict
            
        return magDict
    
    def calcGalaxyMags(self,bandPassList):\
        
        idName=self.column_by_name('galid')
        
        diskNames=self.column_by_name('sedFilenameDisk')
        bulgeNames=self.column_by_name('sedFilenameBulge')
        agnNames=self.column_by_name('sedFilenameAgn')

        diskmn = self.column_by_name('magNormDisk')
        bulgemn = self.column_by_name('magNormBulge')
        agnmn = self.column_by_name('magNormAgn')

        bulgeAv = self.column_by_name('internalAvBulge')
        diskAv = self.column_by_name('internalAvDisk')

        redshift = self.column_by_name('redshift')
        
        diskMags = self.calculate_mags(bandPassList,diskNames,magNorm=diskmn,subDir="/galaxSED/",redshift=redshift,internalAv=diskAv)
        bulgeMags = self.calculate_mags(bandPassList,bulgeNames,magNorm=bulgemn,subDir="/galaxySED/",redshift=redshift,internalAV=bulgeAv)
        agnMags = self.calculate_mags(bandPassList,agnNames,magNorm=agnmn,subDir="/agnSED/",redshift=redshift)
        
        total_mags = {}
        
        m_o = 22.
        
        for ii,dd,bb,aa in zip(idName,diskNames,bulgeNames,agnNames):
            for ff in bandPassList:
                nn=numpy.power(10, (diskMags[dd][ff] - m_o)/-2.5)
                nn+=numpy.power(10, (bulgeMags[bb][ff] - m_o)/-2.5)
                nn+=numpy.power(10, (agnMags[bb][ff] - m_o)/-2.5)
                total_mags[idName][ff] = -2.5*log10(nn) + m_o
        
        

    
    @compound('lsst_u','lsst_g','lsst_r','lsst_i','lsst_z','lsst_y')
    def get_magnitudes(self):
        bandPassList=['u','g','r','i','z','y']
        sedNames=self.column_by_name('sedFilename')
        magDict=self.calculate_magnitudes(bandPassList,sedNames)
        
        uu=numpy.zeros(len(sedNames),dtype=float)
        gg=numpy.zeros(len(sedNames),dtype=float)
        rr=numpy.zeros(len(sedNames),dtype=float)
        ii=numpy.zeros(len(sedNames),dtype=float)
        zz=numpy.zeros(len(sedNames),dtype=float)
        yy=numpy.zeros(len(sedNames),dtype=float)
        
        print "sedNames ",sedNames
        for i in range(len(sedNames)):
           name=sedNames[i]
           uu[i]=magDict[name]['u']
           gg[i]=magDict[name]['g']
           rr[i]=magDict[name]['r']
           ii[i]=magDict[name]['i']
           zz[i]=magDict[name]['z']
           yy[i]=magDict[name]['y']
       
       
        return numpy.array([uu,gg,rr,ii,zz,yy])
