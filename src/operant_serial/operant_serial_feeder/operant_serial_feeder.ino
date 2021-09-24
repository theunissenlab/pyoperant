
unsigned long baudRate = 115200; // 9600 seems common though it can probably be increased significantly if needed.
char ioBytes[2];
int ioPort = 0;


// Feeder variables
const int LED_PORT = 9;
const int EN_PIN = 0;
const int STEP_PIN = 1;
const int DIR_PIN = 2;
const int FEEDER_IOPORT=10; // what chan is sent for feeder

// time settings
int delay_time = 2; // msec
long nextStep = -1;
int step_counter = -1;
const int STEPS_PER_CYCLE = 200; // one revolutions
const int MS_DELAY_TIME = 2; // ideal time between steps
//const int feed

#include <TMC2208Stepper.h>             // Include library
TMC2208Stepper driver = TMC2208Stepper(&Serial);  // Create driver and use

void setup()
{
  // start serial port at the specified baud rate
  Serial.begin(baudRate);
  while (!Serial) {
    ; // wait for serial port to connect. Needed for Leonardo only
  }
  Serial.println("Initialized!");
}

void loop()
{
  myTime = millis();
  //set pin modes
  pinMode(EN_PIN, OUTPUT);
  digitalWrite(EN_PIN, HIGH); //deactivate driver (LOW active)
  pinMode(DIR_PIN, OUTPUT);
  digitalWrite(DIR_PIN, LOW); //LOW or HIGH
  pinMode(STEP_PIN, OUTPUT);
  digitalWrite(STEP_PIN, LOW);

  digitalWrite(EN_PIN, HIGH); //de-activate driver
  
  // All serial communications should be two bytes long
  // The first byte specifies the port to act on
  // The second byte specifies the action to take
  // The actions are:
  // 0: Read the specified input
  // 1: Write the specified output to HIGH
  // 2: Write the specified output to LOW
  // 3: Set the specified pin to OUTPUT
  // 4: Set the specified pin to INPUT
  // 5: Set the specified pin to INPUT_PULLUP
  // if we get a valid serial message, read the request:
  if (Serial.available() >= 2) {
    // get incoming two bytes:
    Serial.readBytes(ioBytes, 2);
    //Serial.println("I received: ");
    //Serial.println(ioBytes[0], DEC);
    //Serial.println(ioBytes[1], DEC);
    // Extract the specified port
    ioPort = (int) ioBytes[0];

    // Hijack ioport corresponding to feeder
    if (ioPort == FEEDER_IOPORT){
      case 0:
        Serial.write(true); // not sure what to do here
        break;
      case 1:
        // Start feeding
        step_counter = STEPS_PER_CYCLE;
        digitalWrite(LED_PIN,HIGH);
        digitalWrite(EN_PIN, LOW); //activate driver
        break;
      case 2:
        // STOP FEEDING
        step_counter = -1;
        digitalWrite(LED_PIN,LOW);
        digitalWrite(EN_PIN, HIGH); //de-activate driver
        break;
    }
    else {
      // Switch case on the specified action
      switch ((int) ioBytes[1]) {
        case 0: // Read an input
          Serial.write(digitalRead(ioPort));
          break;
        case 1: // Write an output to HIGH
          digitalWrite(ioPort, HIGH);       
          break;
        case 2: // Write an output to LOW
          digitalWrite(ioPort, LOW);        
          break;
        case 3: // Set a pin to OUTPUT
          pinMode(ioPort, OUTPUT);
          digitalWrite(ioPort, LOW);
          break;
        case 4: // Set a pin to INPUT
          pinMode(ioPort, INPUT);
          break;
        case 5: // Set a pin to INPUT_PULLUP
          pinMode(ioPort, INPUT_PULLUP);
          break;
      }
    }    
  }
  // if there are steps to do, do them
  if (step_counter > 0){
    digitalWrite(STEP_PIN, !digitalRead(STEP_PIN));
    step_counter--;
  }
  else{
      digitalWrite(EN_PIN, HIGH); //de-activate driver
  }
  //delay(10); // Should probably move to a non-delay based spacing.
}
