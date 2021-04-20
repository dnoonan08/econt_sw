#include <LinkAligner.h>

#include <iostream>
#include <sstream>
#include <fstream>
#include <cstring>
#include <iomanip>
#include <algorithm>
#include <chrono>
#include <thread>

LinkAligner::LinkAligner(uhal::HwInterface* uhalHWInterface, 
			 FastControlManager* fc)
{
  m_uhalHW = uhalHWInterface;
  m_fcMan = fc;

  auto buildname = [](std::string base, int val)->std::string{ return base+std::to_string(val); };

  // input eLinks
  std::vector<std::string> eLinks;
  std::vector<std::string> outputBrams;
  auto base = std::string("link");
  for( int i=0; i<12; i++ ){
    std::string name=buildname(base,i);
    eLinks.push_back(name);
    std::string bramname=buildname(std::string("eLink_outputs_block"),i)+std::string("_bram_ctrl");
    outputBrams.push_back(bramname);
  }
  m_eLinks = eLinks;
  m_outputBrams = outputBrams;

  // output eLinks
  std::vector<std::string> eLinksOutput;
  for( int i=0; i<13; i++ ){
    std::string name=buildname(base,i);
    eLinksOutput.push_back(name);
  }
  m_eLinksOutput = eLinksOutput;

  // eLinkOutputs
  eLinkOutputsBlockHandler out( m_uhalHW,
                                std::string("eLink_outputs_ipif_stream_mux"),
				std::string("eLink_outputs_ipif_switch_mux"),
				outputBrams
                                );

  // link capture
  LinkCaptureBlockHandler lchandler( m_uhalHW,
                                     std::string("link_capture_axi"),
				     std::string("link_capture_axi_full_ipif")
				     );
  
  // IO
  IOBlockHandler fromIOhandler( m_uhalHW,
                                std::string("from_ECONT_IO_axi_to_ipif")
                                );
  IOBlockHandler toIOhandler( m_uhalHW,
                              std::string("from_ECONT_IO_axi_to_ipif")
                              );
  m_out = out;
  m_link_capture = lchandler;
  m_fromIO = fromIOhandler;
  m_toIO = toIOhandler;
}

void LinkAligner::align() {

  std::cout << "LinkAligner:: align " << std::endl;
  for(auto eLink : m_eLinks){
    // Select the stream from RAM as the source
    m_out.setSwitchRegister(eLink,"output_select",0);
    // Send 255 words in the link reset pattern
    m_out.setSwitchRegister(eLink,"n_idle_words",255);
    // Send this word for almost all of the link reset pattern
    m_out.setSwitchRegister(eLink,"idle_word",0xaccccccc);
    // Send this word on BX0 during the link reset pattern
    m_out.setSwitchRegister(eLink,"idle_word_BX0",0x9ccccccc);

    // Stream one complete orbit from RAM before looping
    m_out.setStreamRegister(eLink,"sync_mode",1);
    // Determine pattern length in orbits: 1
    m_out.setStreamRegister(eLink,"ram_range",1);
  }

  std::cout << "LinkAligner:: wrote stream/switch " << std::endl;

  // setting up the output RAMs
  for(auto bram : m_outputBrams){
    uint32_t size_bram = 8192;
    std::vector<uint32_t> outData;
    // special header for BX0
    outData.push_back(static_cast<uint32_t>(0x90000000));
    // almost all words get this header
    for(size_t i=1; i!= size_bram; ++i) 
      outData.push_back(static_cast<uint32_t>(0xa0000000));
    m_out.setData(bram, outData, size_bram);
  }

  std::cout << "LinkAligner:: output RAMSs " << std::endl;

  // switching on IO
  for(auto eLink : m_eLinks){
    m_toIO.setRegister(eLink,"reg0",0b110);
    m_toIO.setRegister(eLink,"reg0",0b101);
  }
  for(auto eLink : m_eLinksOutput){
    m_fromIO.setRegister(eLink,"reg0",0b110);
    m_fromIO.setRegister(eLink,"reg0",0b101);
  }
  std::cout << "LinkAligner:: IO " << std::endl;

  // Sending 3 link resets to get IO delays set up properly
  for( int i=0; i<3; i++ ){
    m_fcMan->resetFC(); // send a link reset
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
    m_fcMan->clear_ink_reset_l1a(); // clear the link reset and L1A request bits                                                                                                                    
    //std::cout << "enable_FC_stream " << m_fcMan->getRegister("command.enable_fast_ctrl_stream") << std::endl;
    //std::cout << "orbit sync " << m_fcMan->getRegister("command.enable_orbit_sync") << std::endl;
    // maybe we can't read link reset because it is write only?                                                                                                                                         
    //std::cout << "link reset " << m_fcMan->getRegister("command.link_reset") << std::endl;
  }

  std::cout << "LinkAligner:: FC " << std::endl;

  // enable all 13 links
  m_link_capture.setRegister("global","link_enable",1);
  // reset all links
  m_link_capture.setRegister("global","explicit_resetb",0);
  std::this_thread::sleep_for(std::chrono::milliseconds(1));
  m_link_capture.setRegister("global","explicit_resetb",1);
  // for all links
  for(auto eLink : m_eLinksOutput){
    // set the alignment pattern for all links
    m_link_capture.setRegister(eLink,"align_pattern",SYNC_WORD);
    // set the capture mode of all 13 links to 2 (L1A)
    m_link_capture.setRegister(eLink,"capture_mode_in",2);
    // set the BX offset of all 13 links
    uint32_t bx_offset = m_link_capture.getRegister(eLink,"L1A_offset_or_BX");
    m_link_capture.setRegister(eLink,"L1A_offset_or_BX", (bx_offset&0xffff0000)|10 );
    // set the acquire length of all 13 links
    m_link_capture.setRegister(eLink,"aquire_length", 256);
    // set the latency buffer based on the IO delays
    uint32_t delay_out = m_fromIO.getRegister(eLink,"delay_out");
    //elay_out = (fromIO[1:,3] >> 1) & 0x1ff
    //LCs[:,3] = (LCs[:,3] & 0xffff) | ((1*(delay_out < 0x100)) << 16)
    //m_link_capture.setRegister(eLink,"fifo_latency", 0x1ff);
    // tell link capture to do an acquisition
    m_link_capture.setRegister(eLink,"aquire", 1);
  }

  std::cout << "LinkAligner:: link capture  " << std::endl;

  // sending a link reset and L1A together, to capture the reset sequence
  // set the BX on which link reset will be sent
  m_fcMan->set_link_reset_bx(3550); // sync pattern from eLink_outputs appears in the snapshot 2 BX later? 
  m_fcMan->set_l1a_A_bx(3549); // BX on which L1A will be sent
  // send a link reset fast command and an L1A 
  m_fcMan->send_link_reset_l1a(); 
  std::this_thread::sleep_for(std::chrono::milliseconds(1));
  // clear the link reset and L1A request bits
  m_fcMan->clear_ink_reset_l1a();
  std::cout << "LinkAligner:: clear link reset " << std::endl;

  // check alignment status
  for(auto eLink : m_eLinks){
    std::cout << "Status " << m_link_capture.getRegister(eLink,"status.link_aligned") << std::endl;
  }

  // reading out captured data
  std::cout << "LinkAligner:: reading captured data " << std::endl;
  auto linksdata = std::vector< std::vector<uint32_t> >(m_eLinksOutput.size());
  int id=0;
  for( auto eLink : m_eLinksOutput){
    m_link_capture.getData( eLink, linksdata[id], 256 );
    int nBX0 = (int)std::count( linksdata[id].begin(), linksdata[id].end(), BX0_WORD );
    std::cout << "iElink " << id << " BX0 found " << nBX0 << std::endl;
    id++;
  }

}
