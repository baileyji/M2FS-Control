/*
  Nathan Seidle
  SparkFun Electronics 2011
  
  This code is public domain but you buy me a beer if you use this and we meet someday (Beerware license).
  
  Controlling an LED strip with individually controllable RGB LEDs. This stuff is awesome.
  
  The SparkFun (individually controllable) RGB strip contains a bunch of WS2801 ICs. These
  are controlled over a simple data and clock setup. The WS2801 is really cool! Each IC has its
  own internal clock so that it can do all the PWM for that specific LED for you. Each IC
  requires 24 bits of 'greyscale' data. This means you can have 256 levels of red, 256 of blue,
  and 256 levels of green for each RGB LED. REALLY granular.
 
  To control the strip, you clock in data continually. Each IC automatically passes the data onto
  the next IC. Once you pause for more than 500us, each IC 'posts' or begins to output the color data
  you just clocked in. So, clock in (24bits * 32LEDs = ) 768 bits, then pause for 500us. Then
  repeat if you wish to display something new.
  
  This example code will display bright red, green, and blue, then 'trickle' random colors down 
  the LED strip.
  
  You will need to connect 5V/Gnd from the Arduino (USB power seems to be sufficient).
  
  For the data pins, please pay attention to the arrow printed on the strip. You will need to connect to
  the end that is the begining of the arrows (data connection)--->
  
  If you have a 4-pin connection:
  Blue = CKI
  Red = 5V
  Green = SDI
  Yellow = GND
 */

#define SDI 2 
#define CKI 3 
#define LEDPIN 13
#define SWITCHPIN 12
#define STRIP_LENGTH 25
#define WRITE_WAIT_US 1000
#define OFF 0
#define WHITE 1
#define TRIPPY 2

#define DEBOUNCE_MS 50

uint8_t mode=OFF;
uint8_t activeMode=TRIPPY;

int lastButtonState = LOW;   // the previous reading from the input pin
int buttonState;
long lastDebounceTime = 0;  // the last time the output pin was toggled
long debounceDelay = 50;    // the debounce time; increase if the output flickers


long strip_colors[STRIP_LENGTH];

void setup() {
  pinMode(SDI, OUTPUT);
  pinMode(CKI, OUTPUT);
  pinMode(LEDPIN, OUTPUT);
  pinMode(SWITCHPIN, INPUT);
  digitalWrite(SWITCHPIN, HIGH);
  
  //Clear out the array
  for(int x = 0 ; x < STRIP_LENGTH ; x++) strip_colors[x] = 0;
  
  //Seed random generator
  randomSeed(analogRead(0));

  Serial.begin(115200);
}

void loop() {
  
  //Monitor operating mode
  // read the state of the switch into a local variable:
  int reading = digitalRead(SWITCHPIN);
  // If the switch changed, due to noise or pressing, reset the debouncing timer
  if (reading != lastButtonState)
    lastDebounceTime = millis();
  //If the time since state chage exceeds the debounceDelay then the button
  // was pressed or released
  if ((millis() - lastDebounceTime) > DEBOUNCE_MS) {
    //If it was pressed go to the next mode
    if (reading==LOW && buttonState==HIGH) {
      mode=(mode+1) % 3;
      Serial.print("Mode is now:");Serial.println((long)mode);
    }
    buttonState=reading;
  }
  // save the reading.  Next time through the loop,
  // it'll be the lastButtonState:
  lastButtonState = reading;
  
  
  switch (mode) {
   case OFF:
       lightsOut();
       break;
   case WHITE:
       lightsOn();
       break;
   case TRIPPY:
       rave();
       break;
  } 
  
}

void lightsOut(void) {
  if (activeMode !=0) {
    for(int x = (STRIP_LENGTH - 1) ; x >= 0 ; x--) strip_colors[x] = 0;
    post_frame();
    activeMode=0;
  }
}

void lightsOn(void) {
    for(int x = (STRIP_LENGTH - 1) ; x >= 0 ; x--) strip_colors[x] = 0xFFFFFF;
    post_frame();
    activeMode=1;
}

void rave(void) {
  addRandom();
  post_frame();
  activeMode=2;
}

//Throws random colors down the strip array
void addRandom(void) {
  
  //First, shuffle all the current colors down one spot on the strip
  for(int x = (STRIP_LENGTH - 1) ; x > 0 ; x--)
    strip_colors[x] = strip_colors[x - 1];
    
  //Now form a new RGB color
  long new_color = newRandomColor();
  /*for(int x = 0 ; x < 3 ; x++){
    new_color <<= 8;
    new_color |= random(0xFF); //Give me a number from 0 to 0xFF
    //new_color &= 0xFFFFF0; //Force the random number to just the upper brightness levels. It sort of works.
  }*/
  
  strip_colors[0] = new_color; //Add the new random color to the strip
}


long newRandomColor() {

    int h1 = random(6);

    float r, g, b;
  
    float s = 0.65 + (random(101)/100.0) * 0.35; // Quite saturated
    float l = 0.5;
  
    float c = (1 - abs(2 * l - 1)) * s; // Chroma.

    float m = l - c/2;
    
    float x = c * (1 - abs(h1 % 2 - 1));    

    if (h1 < 1) { r=c; g=x; b=0;}
    else if (h1<2) { r=x; g=c; b=0;}
    else if (h1<3) { r=0; g=c; b=x;}
    else if (h1<4) { r=0; g=x; b=c;}
    else if (h1<5) { r=x; g=0; b=c;}
    else { r=c; g=0; b=x;}
    
    return ( ( (long) ((r + m)*255) ) <<16) | (( (long) ((g + m)*255) ) <<8) | ( (long) ((b + m)*255) );
}


//Takes the current strip color array and pushes it out
void post_frame (void) {
  //Each LED requires 24 bits of data
  //MSB: R7, R6, R5..., G7, G6..., B7, B6... B0 
  //Once the 24 bits have been delivered, the IC immediately relays these bits to its neighbor
  //Pulling the clock low for 500us or more causes the IC to post the data.

  for(int LED_number = 0 ; LED_number < STRIP_LENGTH ; LED_number++) {
    long this_led_color = strip_colors[LED_number]; //24 bits of color data

    for(byte color_bit = 23 ; color_bit != 255 ; color_bit--) {
      //Feed color bit 23 first (red data MSB)
      
      digitalWrite(CKI, LOW); //Only change data when clock is low
      
      long mask = 1L << color_bit;
      //The 1'L' forces the 1 to start as a 32 bit number, otherwise it defaults to 16-bit.
      
      if(this_led_color & mask) 
        digitalWrite(SDI, HIGH);
      else
        digitalWrite(SDI, LOW);
  
      digitalWrite(CKI, HIGH); //Data is latched when clock goes high
    }
  }

  //Pull clock low to put strip into reset/post mode
  digitalWrite(CKI, LOW);
  delayMicroseconds(WRITE_WAIT_US);
}
