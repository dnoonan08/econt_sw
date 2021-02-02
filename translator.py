import functools
from yaml import safe_load, load, dump
from nested_dict import nested_dict
import math

def memoize(fn):
    """ Readable memoize decorator. """
    fn.cache = {}
    @functools.wraps(fn)
    def inner(inst, *key):
        if key not in fn.cache:
            fn.cache[key] = fn(inst, *key)
        return fn.cache[key]
    return inner

class Translator():
    """ Translate between (human-readable) config and corresponding address/register values. """

    def __init__(self):
        self.paramMap = self.__load_param_map("reg_maps/ECON_I2C_params_regmap.yaml")

    def __load_param_map(self, fname):
        """ Load a yaml register map into cache (as a dict). """
        with open(fname) as fin:
            paramMap = safe_load(fin)
        return paramMap

    def cfg_from_pairs(self, pairs):
        """
        Convert from {addr:val} pairs to {param:param_val} config.
        We can only recover a parameter from a pair when it is in the common cache.
        However, when we read (or write) a param the common cache is populated in advance.
        """
        cfg = nested_dict()
        #print(self.__regs_from_paramMap.items())
        for param, param_regs in self.__regs_from_paramMap.cache.items():
            print(param,param_regs)
        return cfg.to_dict()

    def pairs_from_cfg(self, cfg, writeCache):
        """
        Convert an input config dict to address: value pairs
        Case 1: One parameter value has one register
        Case 2: Several parameter values share same register
        Case 3: A block of registers is `repeated` for the number of channels (*)
        Case 4: A block of paramaters for a given register is `repeated` for the number of channels (*)
        """
        cfg_str = dump(cfg)
        pairs = {}
        nchannels = cfg['nchannels']
        for access in cfg:
            if access=='nchannels': continue
            for block in cfg[access]:
                block_shift = cfg[access][block]['block_shift'] if 'block_shift' in cfg[access][block] else 0
                addr_base = cfg[access][block]['addr_base']
                    
                for param, paramDict in  cfg[access][block]['params'].items():
                    #print(access,block,param,paramDict)
                    addr_offset = paramDict['addr_offset'] if 'addr_offset' in paramDict else 0
                    size_byte = paramDict['size_byte'] if 'size_byte' in paramDict else 1
                    
                    address = addr_base + addr_offset
                    values = paramDict['default']
                    
                    # make list of addresses and values
                    if '*' in param:
                        try:
                            #paramList = [param.replace('*',i) for i in range(len(values))]
                            addrList = [address + i*paramDict['addr_shift'] for i in range(len(values))]
                            valList = values
                        except:
                            print('list of parameters but no shift of address')
                            raise
                    elif '*' in block:
                        try:
                            #paramList[block] = [param]
                            addrList = [address + i*block_shift for i in range(nchannels)]
                            valList = [values for i in range(nchannels)]
                        except:
                            print('no block shift in block dictionary')
                            raise
                    else:
                        addrList = [address]
                        valList = [values]

                    par_regs = self.__regs_from_paramMap(access, block, param)
                    #print('par_regs ',par_regs)
                    for i,addr in enumerate(addrList):
                        # check for previous register value
                        if addr in pairs:
                            if size_byte > 1: prev_regVal = int.from_bytes(pairs[addr], 'little')
                            else: prev_regVal = pairs[addr][0]
                        elif addr in writeCache:
                            prev_paramVal = writeCache[addr][0]
                        else:
                            prev_regVal = 0
                            
                        # convert parameter value (from config) into register value
                        paramVal = valList[i]
                        val = prev_regVal + paramVal
                        if size_byte > 1:
                            pairs[addr] = list(val.to_bytes(size_byte, 'little'))
                        else:
                            pairs[addr] = [val]

        # testing
        '''
        for p,lpp in pairs.items():
            print(p,lpp)
            for pp in lpp:
                print(hex(p), hex(pp))
                '''
        print(self.paramMap['ECON-T']['RW']['PLL_ALL']['params'])
        return pairs
    
    @memoize
    def __regs_from_paramMap(self, access, block, param):
        return self.paramMap['ECON-T'][access][block]['params'][param]
    
    def __regVal_from_paramVal(self, reg, param_value, prev_param_value=0):
        """ Convert parameter value (from config) into register value (1 byte). """
        reg_value = param_value & reg["param_mask"]
        reg_value <<= reg["param_shift"]
        reg_value = prev_param_value + reg_value
        return reg_value

    def __paramVal_from_regVal(self, reg, reg_value, prev_reg_value=0):
        """ Convert register value into (part of) parameter value. """
        param_val = (reg_value >> reg["param_shift"])
        param_val &= reg["param_mask"]
        param_val += prev_reg_value
        return param_val
