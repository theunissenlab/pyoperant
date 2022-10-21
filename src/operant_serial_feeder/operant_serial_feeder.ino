
unsigned long baudRate = 115200; // 9600 seems common though it can probably be increased significantly if needed.
char ioBytes[2];
int ioPort = 0;


// Feeder variables
const int LED_PIN = 11;
const int EN_PIN = 6;
const int STEP_PIN = 7;
const int DIR_PIN = 2;
const int FEEDER_IOPORT=10; // what chan is sent for feeder

// time settings
int delay_time = 2; // msec
long nextStep = -1;
int feed_step_counter = -1;
const int STEPS_PER_CYCLE = 200; // one revolutions
const int MS_DELAY_TIME = 2; // ideal time between steps

// Digital Pin Settings
const int DIG1_PIN = 53; // TTL
bool DIG1_ENABLED=true;
unsigned long DIG1_NEXT = 0;
const int TTL_PULSE_TIME = 500; // msec
const int TTL_IPI = 10000; // 10 sec

const int DIG2_PIN = 51;
bool DIG2_ENABLED=true;
const int DIG2_COPY_PIN = 4;

const int DIG3_PIN = 49;
bool DIG3_ENABLED=true;
const int DIG3_COPY_PIN = 10;

//const int feed
void setup()
{
  

   // myTime = millis();
  //set pin modes
  pinMode(EN_PIN, OUTPUT);
  digitalWrite(EN_PIN, HIGH); //deactivate driver (LOW active)
  pinMode(DIR_PIN, OUTPUT);
  digitalWrite(DIR_PIN, LOW); //LOW or HIGH
  pinMode(STEP_PIN, OUTPUT);
  digitalWrite(STEP_PIN, LOW);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW); //LOW or HIGH
  pinMode(DIG1_PIN, OUTPUT);
  digitalWrite(DIG1_PIN,LOW);
  pinMode(DIG2_PIN, OUTPUT);
  digitalWrite(DIG2_PIN,LOW);
  pinMode(DIG3_PIN, OUTPUT);
  digitalWrite(DIG3_PIN,LOW);
  

  digitalWrite(EN_PIN, HIGH); //de-activate driver
  // start serial port at the specified baud rate
  Serial.begin(baudRate);
  while (!Serial) {
    ; // wait for serial port to connect. Needed for Leonardo only
  }
  Serial.println("Initialized!");
}

void loop()
{ 
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
    // Extract the specified port
    ioPort = (int) ioBytes[0];

    // Hijack ioport corresponding to feeder
    // This is for the stepper motor Feeder
    if (ioPort == FEEDER_IOPORT){
      switch ((int) ioBytes[1]) {
        case 0:
          Serial.write(true); // not sure what to do here
          break;
        case 1:
          // Start feeding
          feed_step_counter = STEPS_PER_CYCLE;
          digitalWrite(LED_PIN,HIGH);
          digitalWrite(EN_PIN, LOW); //activate driver
          nextStep = millis() + delay_time;
          break;
        case 2:
          // STOP FEEDING
          feed_step_counter = -1;
          digitalWrite(LED_PIN,LOW);
          digitalWrite(EN_PIN, HIGH); //de-activate driver
          break;
      }
    } // end stepper motor feeder code
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
          if( ioPort != DIG1_PIN){ // Ignore DIG1_PIN
            pinMode(ioPort, OUTPUT);
            digitalWrite(ioPort, LOW);
          }
          break;
        case 4: // Set a pin to INPUT
          if( ioPort != DIG1_PIN){ // Ignore DIG1_PIN
            pinMode(ioPort, INPUT);
          }
          break;
        case 5: // Set a pin to INPUT_PULLUP
          if( ioPort != DIG1_PIN){ // Ignore DIG1_PIN
            pinMode(ioPort, INPUT_PULLUP);
          }
          break;
      }
    }    
  }
  // if there are steps to do, do them
  if (feed_step_counter > 0){
    if (millis() > nextStep){
      digitalWrite(STEP_PIN, !digitalRead(STEP_PIN));
      feed_step_counter--;
      nextStep = millis() + delay_time;
    }
  }
  if(DIG1_ENABLED){
    if (millis() > DIG1_NEXT){
      int val = digitalRead(DIG1_PIN);
      digitalWrite(DIG1_PIN, !val);
      if (val > 0){
        DIG1_NEXT = millis() + TTL_IPI - TTL_PULSE_TIME;
      }
      else{
        DIG1_NEXT =  millis() + TTL_PULSE_TIME;
      }
    }
  }

  if(DIG2_ENABLED){
    digitalWrite(DIG2_PIN, digitalRead(DIG2_COPY_PIN));
  }

  if(DIG3_ENABLED){
    digitalWrite(DIG3_PIN, digitalRead(DIG3_COPY_PIN));
  }

  //digitalWrite(STEP_PIN, !digitalRead(STEP_PIN));
  //delay(2);
  //else{
  //  Serial.print("HIGH");
  //    digitalWrite(EN_PIN, HIGH); //de-activate driver
  //}
  //delay(10); // Should probably move to a non-delay based spacing.
}
