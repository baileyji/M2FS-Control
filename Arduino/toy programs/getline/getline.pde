/*
 * Example of getline from section 27.7.1.3 of the C++ standard
 * Demonstrates the behavior of getline for various exceptions.
 * See http://www.cplusplus.com/reference/iostream/istream/getline/
 *
 * Note: This example is meant to demonstrate subtleties the standard and
 * may not the best way to read a file.
 */
#include <SdFat.h>
#include <SdFatUtil.h>

// SD chip select pin
const uint8_t chipSelect = 10;

// file system object
SdFat sd;

// create a serial stream
ArduinoOutStream cout(Serial);


const int line_buffer_size = 80;
char buffer[line_buffer_size];
obufstream bout(buffer,sizeof(buffer));  

//------------------------------------------------------------------------------
void setup(void) {
  Serial.begin(115200);

  cout<<FreeRam();
  cout << pstr("Type any character to start\n");
  while (Serial.read() < 0);

  // initialize the SD card at SPI_HALF_SPEED to avoid bus errors with
  // breadboards.  use SPI_FULL_SPEED for better performance.
  if (!sd.init(SPI_QUARTER_SPEED, chipSelect)) sd.initErrorHalt();

  fstream logfile;//()"log.txt",ios::in | ios::out);
  logfile.open("log.txt",ios::in | ios::out | ios::trunc );
  if (logfile.is_open()) cout<<"Log opened."<<endl;
  uint32_t t0=micros();
  cout<<"file position: "<<logfile.tellp()<<" "<<logfile.tellg()<<endl;

  // use flash for text to save RAM
  logfile << pstr(
    "short line\n"
    "17 character line\n"
    "too long for buffer\n");
  logfile << "another line"<<endl;
 
  uint32_t t1=micros();
  cout<<t1-t0<<endl;
 
  t0=micros();
  logfile.flush();
  t1=micros();
  cout<<t1-t0<<endl;
  
  uint32_t gp=logfile.tellg();
  cout<<"file position: "<<logfile.tellp()<<" "<<logfile.tellg()<<endl;
  logfile.seekg(0);
  cout<<"file position: "<<logfile.tellp()<<" "<<logfile.tellg()<<endl;

  t0=micros();
  while (logfile.getline(buffer, line_buffer_size, '\n') || logfile.gcount()) {
  int count = logfile.gcount();
  if (logfile.fail()) {
    bout.seekp(count);
    cout << "Partial long line: "<<bout;
    logfile.clear(logfile.rdstate() & ~ios_base::failbit);
  } else if (logfile.eof()) {
    bout.seekp(count);
    cout << "Partial final line: "<<bout;  // sdin.fail() is false
  } else {
    bout.seekp(count);
    cout << "Line: "<< bout.buf() <<endl;
  }
  }
  t1=micros();
  cout<<t1-t0<<endl;
  
  cout<<"file position: "<<logfile.tellp()<<" "<<logfile.tellg()<<endl;

  logfile << "newestline\nevennewerline\n";
  cout<<"file position: "<<logfile.tellp()<<" "<<logfile.tellg()<<endl;
  logfile.seekg(gp);
  cout<<"file position: "<<logfile.tellp()<<" "<<logfile.tellg()<<endl;
  
  logfile.getline(buffer, line_buffer_size, '\n');
  int count = logfile.gcount();
  bout.seekp(count);
  cout << "Line: "<< bout.buf() <<endl;
  
  logfile.flush();
  
  logfile.getline(buffer, line_buffer_size, '\n');
  count = logfile.gcount();
  bout.seekp(count);
  cout << "Line: "<< bout.buf() <<endl;
  

  cout<<"Done"<<endl;

}




//------------------------------------------------------------------------------
void loop(void) {}
