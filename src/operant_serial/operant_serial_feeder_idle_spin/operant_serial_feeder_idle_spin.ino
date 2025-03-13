
unsigned long baudRate = 115200; // 9600 seems common though it can probably be increased significantly if needed.
char ioBytes[2];
int ioPort = 0;


// Feeder variables
const int LED_PIN = 11;
const int EN_PIN = 6;
const int STEP_PIN = 7;
const int DIR_PIN = 2;
const int FEEDER_IOPORT=10; // what chan is sent for feeder

// button for manual feeds
const int FEED_BUTTON_PIN=3;

// time settings
const int switch_dur = 10;
int dir_switch=10;
int fake_step_counter = -1;
long nextFakeStep = -1;

int delay_time = 2; // msec
long nextStep = -1;
int feed_step_counter = -1;
const int msMaxFeederDelay = 300; //msec
long delayedFeederStartTime = -1;
bool bFeederStarted = 0;
long msLastPress = 0;
const int STEPS_PER_CYCLE = 400; // one revolutions
// NEMA 17 standard motor: 1.8 deg = 200 steps per cycle native 16x microstepping = 3200 steps per rotation
// 400 should be 1/8th the circle, 460 was used for auger feeder
const int MS_DELAY_TIME = 2; // ideal time between steps

// IR Sensor PIN
const int IR_SENSOR_PIN = 5;

// Digital Pin Settings
const int DIG1_PIN = 53; // TTL
bool DIG1_ENABLED=true;
unsigned long DIG1_NEXT = 0;
const int TTL_PULSE_TIME = 500; // msec
const int TTL_IPI = 10000; // 10 sec

const int DIG2_PIN = 51;
bool DIG2_ENABLED=true;
const int DIG2_COPY_PIN = 4; // PECKPORT

const int DIG3_PIN = 49;
bool DIG3_ENABLED=true;
const int DIG3_COPY_PIN = IR_SENSOR_PIN; // IR_SENSOR_PIN

//const int feed
void setup()
{
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
  pinMode(FEED_BUTTON_PIN,INPUT_PULLUP);
  // start serial port at the specified baud rate
  Serial.begin(baudRate);
  while (!Serial) {
    ; // wait for serial port to connect. Needed for Leonardo only
  }
  randomSeed(analogRead(0));
  delay(500);
  Serial.println("Initialized!");
  nextStep = millis();
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
          //Start feeding after some randomized delay
          delayedFeederStartTime = millis() + random(msMaxFeederDelay); // turn on LED with some delay less than maxFeederDelay
          break;
        case 2:
          // STOP FEEDING
          bFeederStarted=false;
          feed_step_counter = -1;
          delayedFeederStartTime = -1;
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
  // BUTTON HANDLING
  if (!digitalRead(FEED_BUTTON_PIN)){
    // can only press button once per second
    if (millis() - msLastPress > 1000){
      msLastPress = millis();
      // Start feeding 
      if (delayedFeederStartTime < 0 & !bFeederStarted){
        delayedFeederStartTime=millis();
      }
      else if (bFeederStarted){
        // STOP FEEDING
        feed_step_counter = -1;
        delayedFeederStartTime = -1;
        bFeederStarted = false;
        digitalWrite(LED_PIN,LOW);
        digitalWrite(EN_PIN, HIGH); //de-activate driver
      }
    }
  }


  // FEEDER HANDLING
  if (delayedFeederStartTime > 0){
    if ( millis() > delayedFeederStartTime){
      digitalWrite(LED_PIN,HIGH);
      delayedFeederStartTime = -1;
      // Start feeding
      feed_step_counter = STEPS_PER_CYCLE;
      //digitalWrite(LED_PIN,HIGH);
      bFeederStarted=true;
      digitalWrite(EN_PIN, LOW); //activate driver
      digitalWrite(DIR_PIN, LOW); // correct Direction
      nextStep = millis() + delay_time;
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
  else{
    // if there are fake steps to do
    if(fake_step_counter > 0){
      if (millis() > nextFakeStep){
        //digitalWrite(DIR_PIN, !digitalRead(DIR_PIN));
        if (dir_switch <= 0){
          digitalWrite(DIR_PIN, !digitalRead(DIR_PIN));
          dir_switch = switch_dur;
        }
        else{
          dir_switch--;
        }
        digitalWrite(STEP_PIN, !digitalRead(STEP_PIN));
        nextFakeStep = millis() + delay_time;
      }
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
