import uhal
import time
import argparse

"""
To be run on ASIC.
"""

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('debug', metavar='d', type=str, nargs='+',
                        help='debug options')
    parser.add_argument('--io', type=str, default="to",
                        help='to IO or from IO')
    args = parser.parse_args()

    man = uhal.ConnectionManager("file://connection.xml")
    dev = man.getDevice("mylittlememory")

    io_name_to = "IO-to-ECONT-IO-blocks-0"
    input_link_capture_name="IO-to-ECONT-input-link-capture-link-capture-AXI-0"
    input_bram_name="IO-to-ECONT-input-link-capture-link-capture-AXI-0_FIFO"
    input_nlinks = 12

    io_name_from = "IO-from-ECONT-IO-blocks-0"
    output_link_capture_name="IO-from-ECONT-output-link-capture-link-capture-AXI-0"
    output_bram_name="IO-from-ECONT-output-link-capture-link-capture-AXI-0_FIFO"
    output_nlinks = 13

    # align to-IO
    for l in range(input_nlinks):
        link = "link%i"%l
        dev.getNode(io_name_to+"."+link+".reg0.tristate_IOBUF").write(0x0)
        dev.getNode(io_name_to+"."+link+".reg0.bypass_IOBUF").write(0x0)
        dev.getNode(io_name_to+"."+link+".reg0.invert").write(0x0)

        dev.getNode(io_name_to+"."+link+".reg0.reset_link").write(0x0)
        dev.getNode(io_name_to+"."+link+".reg0.reset_counters").write(0x1)
        dev.getNode(io_name_to+"."+link+".reg0.delay_mode").write(0x1)

    dev.getNode(io_name_to+".global.global_rstb_links").write(0x1)
    dev.dispatch()

    # check that IO is aligned
    for l in range(input_nlinks):
        link = "link%i"%l
        while True:
            bit_tr = dev.getNode(io_name+"."+link+".reg3.waiting_for_transitions").read()
            delay_ready = dev.getNode(io_name+"."+link+".reg3.delay_ready").read()
            dev.dispatch()
            # print("%s: bit_tr %d and delay ready %d"%(link,bit_tr,delay_ready))
            if delay_ready==1:
                print('%s DELAY READY!'%link)
                break;    

    # configure input link capture
    dev.getNode(link_capture_name+".global.link_enable").write(0x1fff)
    dev.getNode(link_capture_name+".global.explicit_resetb").write(0x0)
    time.sleep(0.001)
    dev.getNode(link_capture_name+".global.explicit_resetb").write(0x1)
    for l in range(input_nlinks):
        link = "link%i"%l
        dev.getNode(link_capture_name+"."+link+".explicit_resetb").write(0x0)
        dev.getNode(link_capture_name+"."+link+".explicit_resetb").write(0x1)
        dev.getNode(link_capture_name+"."+link+".L1A_offset_or_BX").write(3500)
        dev.getNode(link_capture_name+"."+link+".capture_mode_in").write(0x1)
        dev.getNode(link_capture_name+"."+link+".aquire_length").write(0x1000)
    dev.dispatch()

    # capture input link capture
    for l in range(input_nlinks):
        link = "link%i"%l
        data = dev.getNode(bram_name+"."+link).readBlock(0x1000)
        dev.dispatch()
        if l==0:
            print(link)
            print([hex(i) for i in data])
        dev.getNode(link_capture_name+"."+link+".aquire").write(0x0)
        dev.getNode(link_capture_name+"."+link+".explicit_rstb_acquire").write(0x0)
        dev.getNode(link_capture_name+"."+link+".explicit_rstb_acquire").write(0x1)
        dev.dispatch()
    dev.getNode(link_capture_name+".global.interrupt_enable").write(0x0)
    dev.dispatch()

    # only needed for from-IO
    dev.getNode(link_capture_name+".global.link_enable").write(0x1fff)
    dev.getNode(link_capture_name+".global.explicit_resetb").write(0x0)
    time.sleep(0.001)
    dev.getNode(link_capture_name+".global.explicit_resetb").write(0x1)
    for l in range(nlinks):
        link = "link%i"%l
        dev.getNode(link_capture_name+"."+link+".align_pattern").write(0b00100100010)
        dev.getNode(link_capture_name+"."+link+".L1A_offset_or_BX").write(3500)
        dev.getNode(link_capture_name+"."+link+".capture_mode_in").write(0x1)
        dev.getNode(link_capture_name+"."+link+".aquire_length").write(0x1000)
        dev.getNode(link_capture_name+"."+link+".fifo_latency").write(0x0)
        dev.dispatch()
