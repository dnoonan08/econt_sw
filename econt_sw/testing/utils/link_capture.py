import os
import uhal
import time
from .uhal_config import *

import logging
logging.basicConfig()
logger = logging.getLogger('utils:lc')
logger.setLevel(logging.INFO)

class LinkCapture:
    """Class to handle multiple link captures (lcs) over uhal. Always needs the link-capture name."""

    def __init__(self):
        """Initialization class to setup connection manager and device"""
        self.man = uhal.ConnectionManager("file://connection.xml")
        self.dev = self.man.getDevice("mylittlememory")
        self.lcs = {
            'lc-ASIC': names['lc-ASIC']['lc'],
            'lc-input': names['lc-input']['lc'],
            'lc-emulator': names['lc-emulator']['lc'],
        }
        self.fifos = {
            'lc-ASIC': names['lc-ASIC']['fifo'],
            'lc-input': names['lc-input']['fifo'],
            'lc-emulator': names['lc-emulator']['fifo'],
        }
        self.nlinks = {
            'lc-ASIC': output_nlinks,
            'lc-input': input_nlinks,
            'lc-emulator': output_nlinks,
        }
        # maximum length
        self.nwords = {
            'lc-ASIC': 4095,
            'lc-input': 511,
            'lc-emulator': 4095,
        }
        self.sync = {
            'lc-ASIC': 0x122,
            'lc-emulator': 0x122,
            'lc-input': 0xaccccccc,
        }
        # fast commands by link capture acquire mode
        self.fc_by_lfc = {
            'linkreset_ECONt': 'link_reset_econt',
            'linkreset_ECONd': 'link_reset_econd',
            'linkreset_ROCt': 'link_reset_roct',
            'linkreset_ROCd': 'link_reset_rocd',
        }
        
    def reset(self,lcaptures,syncword=""):
        """Reset lcs and sync word"""
        for lcapture in lcaptures:
            self.dev.getNode(self.lcs[lcapture]+".global.link_enable").write(0x1fff)
            self.dev.getNode(self.lcs[lcapture]+".global.explicit_resetb").write(0x0)
            time.sleep(0.001)
            self.dev.getNode(self.lcs[lcapture]+".global.explicit_resetb").write(0x1)
            self.dev.dispatch()
            
            for l in range(self.nlinks[lcapture]):
                sync_pattern = self.sync[lcapture] if syncword=="" else syncword
                self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".align_pattern").write(sync_pattern)
                self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".fifo_latency").write(0);
                self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".link_align_inhibit").write(0);
                if lcapture=="lc-ASIC":
                    # reverse bit for lc
                    self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".delay.bit_reverse").write(1);
                self.dev.dispatch()

    def syncword(self,lcaptures,syncword=""):
        """Change sync word in lcs"""
        for lcapture in lcaptures:
            for l in range(self.nlinks[lcapture]):
                sync_pattern = self.sync[lcapture] if syncword=="" else syncword
                try:
                    sync_pattern = int(sync_pattern,16)
                except:
                    logger.warning('Sync pattern already an int')
                self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".align_pattern").write(sync_pattern)
            self.dev.dispatch()                                
        
    def disable_alignment(self,lcaptures):
        """Disable alignment in lcs"""
        for lcapture in lcaptures:
            for l in range(self.nlinks[lcapture]):
                self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".link_align_inhibit").write(1);
            self.dev.dispatch()

    def set_latency(self,lcaptures,latency):
        """Reset links and set latency for multiple lcs"""
        for lcapture in lcaptures:
            for l in range(self.nlinks[lcapture]):
                self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".explicit_resetb").write(0)
                self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".fifo_latency").write(latency[l]);
            self.dev.dispatch()
            logger.info(f'Written latencies in {lcapture}: %s',latency)

    def read_latency(self,lcaptures):
        """Read latency for multiple lcs"""
        for lcapture in lcaptures:
            read_latency = {}
            for l in range(output_nlinks):
                lat = self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".fifo_latency").read();
                self.dev.dispatch()
                read_latency[l] = int(lat)
            logger.info(f'Read latencies in {lcapture}: %s',read_latency)

    def manual_align(self,lcaptures,links=None,align_position=None):
        """Manual alignment for given links (if align position is given)"""
        if not links:
            links = range(self.nlinks[lcapture])
            
        # disable alignment
        self.disable_alignment(lcaptures)
        
        for lcapture in lcaptures:
            for l in links:
                align_pos = self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".align_position").read();
                self.dev.dispatch()
                logger.info('Align pos link %i: %i'%(l,int(align_pos)))
                
                if align_position and l in links:
                    self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".override_align_position").write(1);
                    self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".align_position").write(int(align_pos)+args.alignpos);
                    self.dev.dispatch()

                    read_align_pos = self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".align_position").read();
                    self.dev.dispatch()
                    logger.info('Set align pos link %i: %i'%(l,read_align_pos))

                self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".explicit_align").write(1);
                self.dev.dispatch()
                
    def configure_acquire(self,lcaptures,mode,nwords=4095,bx=0,verbose=True):
        """Set link captures to acquire with the same mode"""
        """
        mode (str): BX,linkreset_ECONt,linkreset_ECONd,linkreset_ROCt,linkreset_ROCd,L1A,orbitSync
        mode: 0 (inmediate - writes data to BRAM) 
        mode: 1 (writes data starting on a specific BX count) 
        mode: 2 (writes data after receiving a fast command)
        mode: 3 (auto-daq mode)
        """        
        capture_dict = {'mode_in': 0,
                        'L1A': 0,
                        'orbitSync': 0,
                        'linkreset_ECONt': 0,
                        'linkreset_ECONd': 0,
                        'linkreset_ROCt': 0,
                        'linkreset_ROCd': 0,
                        }
        try:
            if "BX" in mode:
                capture_dict['mode_in'] = 1
            elif "linkreset" in mode or "L1A" in mode or "orbitSync" in mode:
                capture_dict["mode_in"] = 2
            elif "inmediate" in mode:
                capture_dict["mode_in"] = 0
            else:
                logger.warning("Not a valid capture mode!")
                return
        except:
            logger.warning("Not a valid capture mode!")
            return
        
        if capture_dict["mode_in"] == 2:
            capture_dict[mode] = 1
            bx = 0
            
        if verbose:
            logger.info("Configure acquire with bx %i"%bx)
            logger.info("Configure acquire with %s"%capture_dict)

        for lcapture in lcaptures:
            for l in range(self.nlinks[lcapture]):
                # offset from BRAM write start in 40 MHz clock ticks in L1A capture mode, or BX count to trigger BX capture mode
                self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".L1A_offset_or_BX").write(bx) 
                # acquire length
                self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".aquire_length").write(nwords)        
                self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".total_length").write(nwords)
                for key,val in capture_dict.items():
                    self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".capture_%s"%key).write(val)
                self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".aquire").write(1)
                self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".explicit_rstb_acquire").write(0)
                self.dev.dispatch()
            self.dev.getNode(self.lcs[lcapture]+".global.interrupt_enable").write(0)
            self.dev.dispatch()
    
    def do_capture(self,lcaptures,verbose=True):
        """Set acquire to 1 for multiple lcs"""
        for lcapture in lcaptures:
            self.dev.getNode(self.lcs[lcapture]+".global.aquire").write(0)
            self.dev.dispatch()
            self.dev.getNode(self.lcs[lcapture]+".global.aquire").write(1)
            self.dev.dispatch()
        
    def get_captured_data(self,lcaptures,nwords=4095,verbose=True):
        """Get captured data"""
        captured_data = {}
        for lcapture in lcaptures:
            # wait some time until acquisition finishes 
            fifo_occupancies = []; nodata=False
            for l in range(self.nlinks[lcapture]):
                i = 0;
                while True:
                    fifo_occupancy = self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".fifo_occupancy").read()
                    self.dev.dispatch()
                    if fifo_occupancy==nwords: break
                    if i>10000: break
                    i+=1
                
                fifo_occupancies.append(int(fifo_occupancy))
                if int(fifo_occupancy)==0: 
                    logger.warning('no data for %s'%lcapture)
                    nodata = True
            if nodata: continue

            # make sure that all links have the same number of words
            try:
                assert(fifo_occupancies[0] == nwords)
                assert(fifo_occupancy == fifo_occupancies[0])
                logger.debug('fifo occupancies ',fifo_occupancies[0],fifo_occupancy)
            except:            
                logger.error('not same fifo occ for link %i'%l,fifo_occupancies)
                continue

            # now look at data
            daq_data = []
            for l in range(self.nlinks[lcapture]):
                fifo_occupancy = self.dev.getNode(self.lcs[lcapture]+".link%i"%l+".fifo_occupancy").read()
                self.dev.dispatch()
                if int(fifo_occupancy)>0:
                    logger.debug('%s link-capture fifo occupancy link%i %d' %(lcapture,l,fifo_occupancy))
                    data = self.dev.getNode(self.fifos[lcapture]+".link%i"%l).readBlock(int(fifo_occupancy))
                    self.dev.dispatch()
                    daq_data.append([int(d) for d in data])
                else:
                    logger.warning('%s link-capture fifo occupancy link%i %d' %(lcapture,l,fifo_occupancy))
                    
            if len(daq_data)>0:
                if verbose:
                    logger.info('Length of captured data for %s: %i',lcapture,len(daq_data[0]))
                    
            import numpy as np
            transpose = np.array(daq_data).T
            captured_data[lcapture] = transpose
        return captured_data

    def check_links(self,lcaptures):
        """Checks if all links all aligned"""
        for lcapture in lcaptures:
            is_aligned = []; aligned_counter=[]; error_counter=[];
            for l in range(self.nlinks[lcapture]):
                aligned_c = self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".link_aligned_count").read()
                error_c = self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".link_error_count").read()
                aligned =  self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".status.link_aligned").read()
                delay_ready = self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".status.delay_ready").read()
                waiting_for_trig = self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".status.waiting_for_trig").read()
                writing = self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".status.writing").read()
                self.dev.dispatch()

                is_aligned.append(int(aligned))
                aligned_counter.append(int(aligned_c))
                error_counter.append(int(error_c))
                logger.debug(f'{lcapture} link {l}: aligned(%d), delayready(%d), waiting(%d), writing(%d), aligned_c(%d), error_c(%d)'%(aligned, delay_ready, waiting_for_trig, writing, aligned_c, error_c))

            import numpy as np
            is_aligned = np.array(is_aligned)
            aligned_counter = np.array(aligned_counter)
            error_counter = np.array(error_counter)
            try:
                assert np.all(is_aligned==1)
                assert np.all(aligned_counter==128)
                assert np.all(error_counter==0)
                logger.info('%s: all links are aligned!'%lcapture)
            except AssertionError:
                logger.error('%s: is not aligned:'%lcapture)
                for l in range(self.nlinks[lcapture]):
                    bit_err =  self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+".bit_align_errors").read()
                    self.dev.dispatch()
                    logger.error('LINK-%i: is_aligned %d, aligned_counter %d, error_counter %d, bit err %i'%(l, is_aligned[l], aligned_counter[l], error_counter[l], bit_err))
                return False
        return True
    
    def check_lc(self,lcaptures):
        """Print the settings of lcs"""
        reg_links = ['delay.in','delay.idelay_error_offset','delay.set','delay.mode','delay.invert',
                     'align_pattern','capture_mode_in','capture_L1A','capture_orbitSync',
                     'capture_linkreset_ROCd','capture_linkreset_ROCt','capture_linkreset_ECONd','capture_linkreset_ECONt',
                     'L1A_offset_or_BX','fifo_latency','aquire','continuous_acquire','acquire_lock','aquire_length','total_length',
                     'explicit_align','override_align_position','align_position',
                     'explicit_resetb','explicit_rstb_acquire',
                     'reset_counters','link_align_inhibit',
                     'status.link_aligned','status.delay_ready','status.waiting_for_trig','status.writing',
                     'delay_out','delay_out_N',
                     'link_aligned_count','link_error_count',
                     'walign_state','bit_align_errors','word_errors','fifo_occupancy',
                     ]
        regs_global = ['interrupt_enable',#'interrupt_vec',
                       'link_enable','invert_backpressure','inhibit_dump','aquire','continous_acquire',
                       'explicit_align','align_on','explicit_resetb','num_links','bram_size','modules_included','inter_link_locked'
                       ]
                
        for lcapture in lcaptures:
            for l in range(self.nlinks[lcapture]):
                reads = {}
                for key in reg_links:
                    r = self.dev.getNode(self.lcs[lcapture]+".link"+str(l)+"."+key).read()
                    self.dev.dispatch()
                    reads[key] = int(r)
                logger.info('%s link %i %s'%(lcapture,l,reads))
            reads = {}
            for key in regs_global:
                r = self.dev.getNode(self.lcs[lcapture]+".global."+key).read()
                self.dev.dispatch()
                reads[key] = int(r)
            logger.info('%s global %s'%(lcapture,reads))
