#!/bin/bash
python3 testing/i2c.py --name FCTRL_EdgeSel_T1 --value 0 --quiet
python3 testing/i2c.py --name PLL_ref_clk_sel,PLL_enableCapBankOverride,PLL_CBOvcoCapSelect --value 1,1,100 --quiet

python3 testing/i2c.py --name EPRXGRP_TOP_trackMode,CH_EPRXGRP_[0-11]_phaseSelect --value 0,6,6,7,7,7,8,7,8,7,8,7,8 --quiet

python3 testing/i2c.py --name CH_ALIGNER_[0-11]_sel_override_val,CH_ALIGNER_[0-11]_sel_override_en,ALIGNER_orbsyn_cnt_load_val --value [0x38]*12,[1]*12,0 --quiet

python3 testing/i2c.py --name ALGO_threshold_val_[0-47],FMTBUF_eporttx_numen --value [0x3fffff]*48,13 --quiet
python3 testing/i2c.py --name FMTBUF_tx_sync_word,ALGO_drop_lsb --value 0,1 --quiet

python3 testing/i2c.py --name MISC_run --value 1 --quiet

echo "PUSM state"
python3 testing/i2c.py --name PUSM_state
