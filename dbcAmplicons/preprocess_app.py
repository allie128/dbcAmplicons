#!/usr/bin/env python

# Copyright 2013, Institute for Bioninformatics and Evolutionary Studies
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import sys, os, traceback
import time
from dbcAmplicons import barcodeTable
from dbcAmplicons import primerTable
from dbcAmplicons import sampleTable
from dbcAmplicons import FourReadIlluminaRun
from dbcAmplicons import IlluminaTwoReadOutput

class preprocessApp:
    """
    Preprocess raw Illumina four read amplicon data
    """ 
    def __init__(self):
        self.verbose = False
    def start(self, fastq_file1, fastq_file2, fastq_file3, fastq_file4, output_prefix, barcodesFile, primerFile, samplesFile, barcodeMaxDiff=1, primerMaxDiff=4, primerEndMatch=4, batchsize=10000, uncompressed=False, output_unidentified=False, minQ=None, minL = 0, verbose=True, debug=False):
        """
        Start preprocessing double barcoded Illumina sequencing run, perform 
        """
        self.verbose = verbose
        evalPrimer = primerFile != None
        evalSample = samplesFile != None
        try:
            ## read in primer sequences
            bcTable = barcodeTable(barcodesFile)
            if self.verbose:
                print "barcode table length: %s" % bcTable.getLength()
            ## read in primer sequences if present
            if evalPrimer:
                prTable = primerTable(primerFile)
                if verbose:
                    print "primer table length P5 Primer Sequences:%s, P7 Primer Sequences:%s" % (len(prTable.getP5sequences()),len(prTable.getP7sequences()))
            if evalSample:
                sTable = sampleTable(samplesFile)
                if verbose:
                    print "sample table length: %s, and %s projects." % (sTable.getSampleNumber(),len(sTable.getProjectList()))
            ## setup output files
            barcode_counts = {}
            identified_count = 0
            unidentified_count = 0
            self.run_out = {}
            if evalSample:
                for project in sTable.getProjectList():
                    self.run_out[project] = IlluminaTwoReadOutput(os.path.join(output_prefix,project),uncompressed)
            else:
                self.run_out["Identified"] = IlluminaTwoReadOutput(output_prefix,uncompressed)
            if output_unidentified:
                if evalSample:
                    self.run_out["Unidentified"] = IlluminaTwoReadOutput(os.path.join(output_prefix,'UnidentifiedProject'),uncompressed)
                else:
                    self.run_out["Unidentified"] = IlluminaTwoReadOutput(output_prefix+"_Unidentified",uncompressed)
            ## establish and open the Illumin run
            self.run = FourReadIlluminaRun(fastq_file1, fastq_file2, fastq_file3, fastq_file4)
            self.run.open()
            lasttime = time.time()
            while 1:
                ## get next batch of reads
                reads = self.run.next(batchsize)
                if len(reads) == 0:
                    break
                ## process individual reads
                for read in reads:
                    read.assignBarcode(bcTable,barcodeMaxDiff) ## barcode
                    if evalPrimer and read.goodRead: ## primer
                        read.assignPrimer(prTable,primerMaxDiff,primerEndMatch)
                    if evalSample and read.goodRead: ## sample
                        read.assignRead(sTable) ## barcode
                    if minQ != None:
                        read.trimRead(minQ, minL)
                    if read.goodRead == True:
                        identified_count += 1
                        if evalSample:
                            self.run_out[read.getProject()].addRead(read.getFastq())
                        else:
                            self.run_out["Identified"].addRead(read.getFastq())
                        # Record data for final barcode table
                        if read.getBarcode() in barcode_counts:
                            if evalPrimer:
                                barcode_counts[read.getBarcode()][read.getPrimer()] += 1
                            else:
                                barcode_counts[read.getBarcode()]["Total"] += 1
                        else:
                            # setup blank primer count table
                            barcode_counts[read.getBarcode()] = {}
                            if evalPrimer:
                                for pr in prTable.getPrimers():
                                    barcode_counts[read.getBarcode()][pr] = 0
                                barcode_counts[read.getBarcode()][read.getPrimer()] += 1
                            else:
                                barcode_counts[read.getBarcode()]["Total"] = 1
                    else:
                        unidentified_count += 1
                        if output_unidentified:
                            self.run_out["Unidentified"].addRead(read.getFastq())
                ### Write out reads
                for key in self.run_out:
                    self.run_out[key].writeReads()
                if self.verbose:
                    print "processed %s total reads, %s Reads/second, %s identified reads, %s unidentified reads" % (self.run.count(), round(self.run.count()/(time.time() - lasttime),0), identified_count,unidentified_count)
            if self.verbose:
                print "%s reads processed in %s minutes" % (self.run.count(),round((time.time()-lasttime)/(60),2))
            # Write out barcode and primer table
            if (identified_count > 0):
                if evalSample:
                    file_name = os.path.join(output_prefix,'Identified_Barcodes.txt')
                else:
                    file_name = output_prefix + '_Identified_Barcodes.txt'
                try:
                    bcFile = open(file_name, 'w')
                except:
                    print ("Can't open file %s for writing" % file_name)
                # write out header line
                if evalPrimer:
                    txt = 'Barcode\t'+ '\t'.join(prTable.getPrimers()) + '\n'
                else:
                    txt = 'Barcode\tTotal\n'
                bcFile.write(txt)
                bckeys = barcode_counts.keys()
                for bc in bcTable.getBarcodes():
                    if bc in bckeys and evalPrimer:
                        txt = str(bc)
                        for pr in prTable.getPrimers():
                            txt = '\t'.join([txt,str(barcode_counts[bc][pr])])
                    elif bc in bckeys:
                        txt = "\t".join([str(bc),str(barcode_counts[bc]["Total"])])
                    else:
                        continue
                    bcFile.write(txt  + '\n')
            # write out project table
            if evalSample and self.verbose:
                for key in self.run_out:
                    print "%s\treads found for project\t%s" % (self.run_out[key].count(), key)
            self.clean()
            return 0    
        except (KeyboardInterrupt, SystemExit):
            self.clean()
            print("%s unexpectedly terminated" % (__name__))
            return 1
        except:
            self.clean()
            print("A fatal error was encountered.")
            if debug:
                print "".join(traceback.format_exception(*sys.exc_info()))
            return 1

    def clean(self):
        if self.verbose:
            print("Cleaning up.")
        try:
            self.run.close()
            for key in self.run_out:
                self.run_out[key].close()
        except:
            pass
