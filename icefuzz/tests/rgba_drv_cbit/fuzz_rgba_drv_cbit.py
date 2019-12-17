#!/usr/bin/env python3

import os, sys
# SB_RGBA_DRV automatic fuzzing script

device = "up5k"

# SB_RGBA_DRV config bits to be fuzzed
# These must be in an order such that a config with bit i set doesn't set any other undiscovered bits yet


fuzz_bits = [
    "RGB0_CURRENT_0",
    "RGB0_CURRENT_1",
    "RGB0_CURRENT_2",
    "RGB0_CURRENT_3",
    "RGB0_CURRENT_4",
    "RGB0_CURRENT_5",

    "RGB1_CURRENT_0",
    "RGB1_CURRENT_1",
    "RGB1_CURRENT_2",
    "RGB1_CURRENT_3",
    "RGB1_CURRENT_4",
    "RGB1_CURRENT_5",

    "RGB2_CURRENT_0",
    "RGB2_CURRENT_1",
    "RGB2_CURRENT_2",
    "RGB2_CURRENT_3",
    "RGB2_CURRENT_4",
    "RGB2_CURRENT_5",

    "CURRENT_MODE"
]


# Boilerplate code based on the icefuzz script
code_prefix = """
module top(
    input curren,
    input rgbleden,
    input r_in,
    input g_in,
    input b_in,
    output r_led,
    output g_led,
    output b_led);
"""

def get_param_value(param_name, param_size, fuzz_bit):
    param = "\"0b";
    #In the RGB driver, once bit i of a current parameter is set i-1..0 must also be set
    is_high = False
    for i in range(param_size - 1, -1, -1):
        if fuzz_bit == param_name + "_" + str(i) or (i == 0 and fuzz_bit == "CURRENT_MODE") or is_high:
            param += '1'
            is_high = True
        else:
            param += '0'
    param += "\""
    return param
def inst_rgba(fuzz_bit):
    v = ""
    v += """SB_RGBA_DRV rgba_inst (
        .CURREN(curren),
        .RGBLEDEN(rgbleden),
        .RGB0PWM(r_in),
        .RGB1PWM(g_in),
        .RGB2PWM(b_in),
        .RGB0(r_led),
        .RGB1(g_led),
        .RGB2(b_led)
      );"""
    
    v += "defparam rgba_inst.CURRENT_MODE = " + get_param_value("CURRENT_MODE", 1, fuzz_bit) + ";\n"
    v += "defparam rgba_inst.RGB0_CURRENT = " + get_param_value("RGB0_CURRENT", 6, fuzz_bit) + ";\n"
    v += "defparam rgba_inst.RGB1_CURRENT = " + get_param_value("RGB1_CURRENT", 6, fuzz_bit) + ";\n"
    v += "defparam rgba_inst.RGB2_CURRENT = " + get_param_value("RGB2_CURRENT", 6, fuzz_bit) + ";\n"
    
    return v;

def make_vlog(fuzz_bit):
    vlog = code_prefix
    vlog += inst_rgba(fuzz_bit)
    vlog += "endmodule"
    return vlog

known_bits = []

# Set to true to continue even if multiple bits are changed (needed because
# of the issue discusssed below)
show_all_bits = False #TODO: make this an argument

device = "up5k" #TODO: environment variable?

#HACK: icecube doesn't let you set all of the config bits to 0,
#which makes fuzzing early on annoying as there is never a case
#with just 1 bit set. So a tiny bit of semi-manual work is needed
#first to discover this (basically run this script with show_all_bits=True
#and look for the stuck bit)
#TODO: clever code could get rid of this
rgba_drv_en_bit = {
    "up5k" : (0, 28, 5)
}

#Return a list of RGBA_DRIVER config bits in the format (x, y, bit)
def parse_exp(expfile):
    current_x = 0
    current_y = 0
    bits = []
    with open(expfile, 'r') as f:
        for line in f:
            splitline = line.split(' ')
            if splitline[0].endswith("_tile"):
                current_x = int(splitline[1])
                current_y = int(splitline[2])
            elif splitline[0] == "IpConfig":
                if splitline[1][:5] == "CBIT_":
                    bitidx = int(splitline[1][5:])
                    bits.append((current_x, current_y, bitidx))    
    return bits

#Convert a bit tuple as returned from the above to a nice string
def bit_to_str(bit):
    return "(%d, %d, \"CBIT_%d\")" % bit

#The main fuzzing function
def do_fuzz():
    if not os.path.exists("./work_rgba_drv"):
        os.mkdir("./work_rgba_drv")
    known_bits.append(rgba_drv_en_bit[device])
    with open("rgba_drv_data_" + device + ".txt", 'w') as dat:
        for fuzz_bit in fuzz_bits:
            vlog = make_vlog(fuzz_bit)
            with open("./work_rgba_drv/rgba_drv.v", 'w') as f:
                f.write(vlog)
            with open("./work_rgba_drv/rgba_drv.pcf", 'w') as f:
                f.write("""
set_io r_led 39
set_io g_led 40
set_io b_led 41
                """)
            retval = os.system("bash ../../icecube.sh -" + device + " ./work_rgba_drv/rgba_drv.v > ./work_rgba_drv/icecube.log 2>&1")
            if retval != 0:
                sys.stderr.write('ERROR: icecube returned non-zero error code\n')
                sys.exit(1)
            retval = os.system("../../../icebox/icebox_explain.py ./work_rgba_drv/rgba_drv.asc > ./work_rgba_drv/rgba_drv.exp")
            if retval != 0:
                sys.stderr.write('ERROR: icebox_explain returned non-zero error code\n')
                sys.exit(1)
            rgba_bits = parse_exp("./work_rgba_drv/rgba_drv.exp")
            new_bits = []
            for set_bit in rgba_bits:
                if not (set_bit in known_bits):
                    new_bits.append(set_bit)
            if len(new_bits) == 0:
                sys.stderr.write('ERROR: no new bits set when setting config bit ' + fuzz_bit + '\n')
                sys.exit(1)      
            if len(new_bits) > 1:
                sys.stderr.write('ERROR: multiple new bits set when setting config bit ' + fuzz_bit + '\n')
                for bit in new_bits:
                    sys.stderr.write('\t' + bit_to_str(bit) + '\n')
                if not show_all_bits:
                    sys.exit(1)
            if len(new_bits) == 1:
                known_bits.append(new_bits[0])
                #print DIVQ_0 at the right moment, as it's not fuzzed normally
                if fuzz_bit == "RGB0_CURRENT_0":
                    print(("\"RGBA_DRV_EN\":").ljust(24) + bit_to_str(rgba_drv_en_bit[device]) + ",")
                    dat.write(("\"RGBA_DRV_EN\":").ljust(24) + bit_to_str(rgba_drv_en_bit[device]) + ",\n")
                print(("\"" + fuzz_bit + "\":").ljust(24) + bit_to_str(new_bits[0]) + ",")
                dat.write(("\"" + fuzz_bit + "\":").ljust(24) + bit_to_str(new_bits[0]) + ",\n")
do_fuzz()
