// ______          _        _____            _             _ 
// | ___ \        | |      /  __ \          | |           | |
// | |_/ / __ ___ | |_ ___ | /  \/ ___ _ __ | |_ _ __ __ _| |
// |  __/ '__/ _ \| __/ _ \| |    / _ \ '_ \| __| '__/ _` | |
// | |  | | | (_) | || (_) | \__/\  __/ | | | |_| | | (_| | |
// \_|  |_|  \___/ \__\___/ \____/\___|_| |_|\__|_|  \__,_|_|

//////////////////////////////////////////////////////////////////////////////////////////
//
//  Arduino Library for the TI TLA20XX ADC (https://www.ti.com/product/TLA20XX)
//
//  Copyright (c) 2022 ProtoCentral
//
//  Written by: Ashwin Whitchurch (ashwin@protocentral.com)
//
//  This software is licensed under the MIT License(http://opensource.org/licenses/MIT).
//
//  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
//  NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
//  IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
//  WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
//  SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
//
//
/////////////////////////////////////////////////////////////////////////////////////////

#include <Arduino.h>
#include <Wire.h>

#include <protocentral_TLA20xx.h>

#define TLA20XX_I2C_ADDR 0x49

TLA20XX tla2022(TLA20XX_I2C_ADDR);

void setup() 
{
    Serial.begin(57600);
    Serial.println("Starting ADC...");

    //Wire.setSDA(4);
    //Wire.setSCL(5);

    Wire.begin();

    tla2022.begin();
    
    tla2022.setMode(TLA20XX::OP_CONTINUOUS);
    tla2022.setDR(TLA20XX::DR_128SPS);
    tla2022.setFSR(TLA20XX::FSR_2_048V);
}

float val;

void loop() 
{
    float val = tla2022.read_adc(); // +/- 2.048 V FSR, 1 LSB = 1 mV
    Serial.println(val);
    
    delay(100);
}